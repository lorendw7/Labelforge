# Lab Deployment Guide

## Prerequisites

- A lab server with Docker Engine + Docker Compose v2 (Linux recommended; 2 CPU / 4 GB RAM is enough to start).
- A hostname or fixed IP annotators can reach, e.g. `http://lab-server:8080`.

A repurposed desktop machine qualifies — see [When the "server" is a desktop machine](#when-the-server-is-a-desktop-machine) for the two defaults to change first.

**Running it on your own machine** (Windows/macOS with Docker Desktop) uses the identical commands with the default `LABEL_STUDIO_HOST=http://localhost:8080` — the recommended way to iterate on labeling configs and automation scripts before touching the instance annotators depend on. See [A local instance on your own machine](#a-local-instance-on-your-own-machine).

## First deployment

```bash
git clone <this-repo> && cd labelforge
cp .env.example .env
# edit .env: set POSTGRES_PASSWORD, set LABEL_STUDIO_HOST to the URL annotators will use
docker compose --env-file .env -f deploy/docker-compose.yml up -d
```

### When the "server" is a desktop machine

A spare desktop under someone's desk works fine, but two of its defaults break an instance annotators depend on.

**It suspends when idle.** A desktop Ubuntu install sleeps after a while with nobody at the keyboard, and a sleeping machine is indistinguishable from a down one. Disable the sleep targets, and turn off automatic suspend in **Settings → Power** as well (the GNOME setting and the systemd targets are separate switches):

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

**Its IP moves.** `LABEL_STUDIO_HOST` is baked into invite links and annotators' bookmarks, so a DHCP lease change silently breaks both. Give the machine a DHCP reservation or a static address before handing the URL out. Find the current one with `hostname -I`.

Also confirm Docker itself starts at boot — the containers are `restart: unless-stopped`, which only helps if the daemon is up:

```bash
sudo systemctl enable --now docker
```

### A local instance on your own machine

A second instance on a laptop or personal desktop needs no configuration changes at all: `.env.example` already defaults `LABEL_STUDIO_HOST` to `http://localhost:8080`, so the commands above run unmodified on Windows and macOS with Docker Desktop. Four things are worth knowing before you start.

**It is an empty database, not a copy of the lab.** Projects, tasks and annotations live in `data/postgres`, which git never carries — a local instance starts with nothing in it, and work done locally stays local. To develop against real data, restore a dump from the lab (see [Data locations & backup](#data-locations--backup)); a `git pull` will never bring it.

**Invite links are useless locally.** `LABEL_STUDIO_HOST=http://localhost:8080` resolves only on the machine running it, so any link the instance hands out points nowhere for anyone else. Treat a local instance as single-user; multi-annotator studies belong on the shared deployment.

**Leave the `data/postgres` bind mount alone on Windows.** Postgres refuses a data directory it cannot `chmod` to 0700, which is the usual reason a bind-mounted database fails on a Windows host — and the usual reaction is to swap the mount for a named volume. Don't: Docker Desktop's current file sharing handles it, and `postgres:15-alpine` initialises `../data/postgres` cleanly and comes up healthy. Keeping the bind mount is what makes `data/` mean the same thing on every machine, so the backup commands in this guide work unchanged.

**Docker Desktop has to be running before the containers can be.** `restart: unless-stopped` brings the stack back after a reboot, but only once the daemon is up, and Docker Desktop does not start itself unless you enable **Settings → General → Start Docker Desktop when you sign in to your computer**. Without that, every reboot silently leaves the stack down.

Then bootstrap the owner account as below. Finally, note that the `automation/` scripts read `LABEL_STUDIO_URL` and `LABEL_STUDIO_API_KEY` from the environment and never load `.env` themselves, so export them into the session before running one. In PowerShell:

```powershell
$env:LABEL_STUDIO_URL = "http://localhost:8080"
$env:LABEL_STUDIO_API_KEY = "<legacy token>"
```

### Bootstrapping the first (owner) account

The first account to register becomes the instance owner, but signup is invite-only by default (`LABEL_STUDIO_DISABLE_SIGNUP_WITHOUT_LINK=true`) — so on a fresh deployment nobody can create that first account. The symptom is confusing rather than obvious: `/user/signup` still renders a normal form — the GET is never gated — and submitting it returns 403, because the check demands an invite token matching an organization that does not exist yet. Open signup briefly instead:

1. In `.env`, set `LABEL_STUDIO_DISABLE_SIGNUP_WITHOUT_LINK=false`, then `docker compose --env-file .env -f deploy/docker-compose.yml up -d app` (recreates only the app container).
2. Open `LABEL_STUDIO_HOST` in a browser and sign up — this account is the owner.
3. Set the flag back to `true` and run the same `up -d app` command. Existing accounts are unaffected; the flag only gates new self-service signups.

Then:

1. **Account & Settings → Access Token** — generate the API token used by `automation/` scripts. The scripts authenticate with `Authorization: Token …`, which requires a **legacy token** (a 40-character hex string), and a fresh instance has legacy tokens turned off — enable them under **Organization → API Tokens Settings** first. Do not substitute the long `eyJ…` JWT personal access token offered by default: it is a *refresh* token, rejected with 401 under both `Token` and `Bearer` until it is exchanged at `/api/token/refresh` for a short-lived access token. Every automation script failing with 401 on a token you just copied is this, not a typo.
2. Invite annotators via **Organization → Add people** (invite link) — no need to reopen signup.
3. Create projects per task type — see [CUSTOMIZATION.md](CUSTOMIZATION.md).

## Onboarding annotators

The bar to hold: **a new annotator needs a browser and an invite link, nothing else.** What that takes on the deployment side:

1. **One stable URL everyone can reach.** `LABEL_STUDIO_HOST` is what lands in invite links and bookmarks, so fix the address before handing it out (see the desktop-machine notes above). If annotators are off-network, they reach it over the lab VPN — test that from an actual off-network machine, not from the server.
2. **Accounts by invite only.** **Organization → Add people** generates the invite link; signup stays closed (`LABEL_STUDIO_DISABLE_SIGNUP_WITHOUT_LINK=true`). Never reopen public signup to add people.
3. **Everyone logs in once *before* the kickoff session.** This is the single highest-value step: password resets, VPN gaps and "I see no projects" all surface here, days ahead of labeling, instead of eating the first hour of a session with everyone waiting.
4. **Give them the one-pager, not the tool.** Copy [ANNOTATOR_QUICKSTART.md](ANNOTATOR_QUICKSTART.md) into the study's guideline packet, fill in its placeholders, add screenshots of that study's actual form, and walk through it live at kickoff.
5. **Turn the nightly backup on for the whole production window** (next section), and copy the dumps off the machine. Annotation time is the one thing a restore cannot recreate.

Note on roles: the community edition has no per-user task assignment. A study that needs "these items for this person" gives each annotator their own project — see [CUSTOMIZATION.md § Verification / dual-annotation studies](CUSTOMIZATION.md#verification--dual-annotation-studies), and [ROADMAP.md](ROADMAP.md) M2 for the provisioning script that will make standing those projects up one command. Members are organization-wide, so anyone with an account can open any project; blinding comes from what you import, never from permissions.

## Administering the instance remotely

Only the first deployment needs someone at the machine's own keyboard. Everything after — updates, logs, backups — is done over SSH. On the server:

```bash
sudo apt-get install -y openssh-server && sudo systemctl enable --now ssh
sudo ufw allow 22/tcp    # if ufw is active; without this the connection times out
```

From a workstation on the same network, `ssh <user>@<server-ip>`. Give it an alias in `~/.ssh/config` so the address lives in one place:

```text
Host labelforge
    HostName <server-ip>
    User <user>
```

Two things that bite here:

- **`docker` group membership only applies to a fresh login.** After `usermod -aG docker <user>`, an already-open session (and every new SSH session started before logging out) still gets `permission denied ... /var/run/docker.sock`. Disconnect and reconnect once. Don't paper over it with `sudo docker` — that leaves `data/` owned by root and breaks the backups later.
- **Off-network access needs a VPN, not an open port.** A campus network won't give you port forwarding, and the instance should not be on the public internet anyway (see Security notes). The lab VPN, or a mesh VPN like Tailscale/ZeroTier on the server plus each annotator's machine, keeps the deployment unchanged — only `LABEL_STUDIO_HOST` changes, to whatever address everyone will actually use.

## Updating the deployment

Labeling configs, automation scripts and compose changes all ship through git, so an update is a pull and a restart:

```bash
cd <repo> && git pull
docker compose --env-file .env -f deploy/docker-compose.yml up -d
```

`up -d` recreates only the containers whose configuration actually changed, and `.env` and `data/` are gitignored — a pull never touches secrets or annotations. After editing `.env` alone, `up -d app` is enough; it recreates just the app container, which costs the ~1 minute Label Studio needs to boot (a browser hitting it during that window sees a connection reset — wait, don't re-run the command).

Version bumps of the Label Studio image itself are deliberate and go through the repo the same way — see [Upgrades](#upgrades) below.

## Data locations & backup

Everything lives under `./data/` (gitignored, never committed):

| Path | Contents |
|---|---|
| `data/postgres/` | all projects, tasks, annotations, users |
| `data/label-studio/` | uploaded files / media |

Back up with a nightly cron job:

```bash
docker compose --env-file .env -f deploy/docker-compose.yml exec db pg_dump -U labelstudio labelstudio | gzip > backups/ls-$(date +%F).sql.gz
tar czf backups/media-$(date +%F).tgz data/label-studio
```

`backups/` is gitignored (a dump *is* the annotation database — it must never reach GitHub), but treat that as the last line of defense: copy backups off the machine, don't let the repo directory be their only home.

(Every `docker compose` subcommand — `ps`, `logs`, `exec`, … — needs `--env-file .env`, because the compose file interpolates required variables from it and the file lives at the repo root, not next to `docker-compose.yml`.)

Restore = start a fresh stack, `psql` the dump back in, untar media.

## Upgrades

The image is pinned (`heartexlabs/label-studio:1.23.0`) so upgrades are deliberate:

1. Take a backup (above).
2. Bump the tag in `deploy/docker-compose.yml`, commit.
3. `docker compose --env-file .env -f deploy/docker-compose.yml up -d` — migrations run automatically on start.

## Webhook validator (optional, benchmark projects)

The validator ships as a compose service (`validator`) and starts with the stack. Register it on a benchmark project via the API (idempotent — re-running skips an already-registered URL; it subscribes to `ANNOTATION_CREATED` / `ANNOTATION_UPDATED` only):

```bash
python automation/register_webhook.py --project <id>
```

The default URL `http://validator.internal:8090/webhook` works because Label Studio reaches the validator over the compose network. The dotted alias (declared in `deploy/docker-compose.yml`) is deliberate: Label Studio's URL validation rejects bare container hostnames like `validator`. Health check from the host: `curl http://localhost:8090/healthz`. Validation results appear in `docker compose --env-file .env -f deploy/docker-compose.yml logs -f validator`.

To run it standalone instead (e.g. local development):

```bash
cd services/webhook-validator
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8090
# then register with --url http://<host>:8090/webhook
```

## Security notes

- Keep the instance on the lab network / VPN; if it must be public, put nginx or Caddy with TLS in front of port 8080.
- `.env` holds the only secrets; it is gitignored — never commit it.
- The API token grants full account access; store it like a password (env var, not in scripts).
