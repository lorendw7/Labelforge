# Lab Deployment Guide

## Prerequisites

- A lab server with Docker Engine + Docker Compose v2 (Linux recommended; 2 CPU / 4 GB RAM is enough to start).
- A hostname or fixed IP annotators can reach, e.g. `http://lab-server:8080`.

A repurposed desktop machine qualifies — see [When the "server" is a desktop machine](#when-the-server-is-a-desktop-machine) for the two defaults to change first.

**Local development** (Windows/macOS with Docker Desktop) uses the identical commands with the default `LABEL_STUDIO_HOST=http://localhost:8080` — this is the recommended way to iterate on labeling configs and automation scripts before touching the lab instance. A local `data/` directory then holds a real (throwaway) database; it is gitignored like everything runtime.

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

### Bootstrapping the first (owner) account

The first account to register becomes the instance owner, but signup is invite-only by default (`LABEL_STUDIO_DISABLE_SIGNUP_WITHOUT_LINK=true`) — so on a fresh deployment the signup page is closed and nobody can create that first account. Open it briefly:

1. In `.env`, set `LABEL_STUDIO_DISABLE_SIGNUP_WITHOUT_LINK=false`, then `docker compose --env-file .env -f deploy/docker-compose.yml up -d app` (recreates only the app container).
2. Open `LABEL_STUDIO_HOST` in a browser and sign up — this account is the owner.
3. Set the flag back to `true` and run the same `up -d app` command. Existing accounts are unaffected; the flag only gates new self-service signups.

Then:

1. **Account & Settings → Access Token** — generate the API token used by `automation/` scripts. The scripts authenticate with `Authorization: Token …`, which requires a **legacy token**; if your instance only shows a long JWT personal access token, enable legacy tokens under **Organization → API Tokens Settings** first.
2. Invite annotators via **Organization → Add people** (invite link) — no need to reopen signup.
3. Create projects per task type — see [CUSTOMIZATION.md](CUSTOMIZATION.md).

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
