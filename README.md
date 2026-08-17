# labelforge

> A general-purpose annotation platform for the lab, built on [Label Studio](https://labelstud.io/) — deployment, per-task labeling configs, automation scripts, and a validation webhook.

## Why Label Studio instead of building our own

The lab needs one annotation platform that serves **many different task types** — benchmark task submission is just one of them. Building bespoke intake tooling per task (xlsx forms, custom web forms) does not scale. Label Studio is the de-facto open-source standard and covers the generic platform concerns out of the box:

- multi-user projects, roles, task assignment and progress tracking,
- a configurable labeling UI (XML templates — no frontend code for new task types),
- import/export in standard formats, REST API + Python SDK,
- webhooks for reacting to submissions in real time,
- ML backends for pre-annotation when a task benefits from it.

So the strategy is: **deploy stock Label Studio, customize only through its supported extension points** (labeling configs, SDK automation, webhooks, ML backends). No fork, no patched frontend — upgrades stay painless.

## Architecture

```
                        ┌──────────────────────────────┐
   annotators ────────▶ │  Label Studio (Docker)       │
   (browser)            │  ├─ project per task type    │
                        │  ├─ labeling config (XML)    │
                        │  └─ PostgreSQL               │
                        └──────┬───────────────┬───────┘
                               │ webhook       │ export (REST)
                               ▼               ▼
                  ┌────────────────────┐   ┌─────────────────────────┐
                  │ webhook-validator  │   │ automation/ exporters   │
                  │ instant field-level│   │ one converter per down- │
                  │ feedback on submit │   │ stream pipeline (xlsx…) │
                  └────────────────────┘   └─────────────────────────┘
```

- **labelforge (this repo)**: platform deployment + per-task customization. Generic; every lab task type lives here as a labeling config plus (optionally) automation.

### Repository boundary (deliberate)

The platform is generic; the science is not. This repo holds what it takes to put the annotation platform in front of people: the Docker deployment, one labeling-config XML per task type, and scripts that talk to the Label Studio API. It contains no analysis and no research results — each study keeps its assignments, judgments, and statistics in its own repository, so a study stays reproducible from its own repo even if the platform changes. Rule of thumb: **a new study or task type adds a labeling config here; everything that ends up in a paper lives in the study's repo.**

## Repository layout

```
deploy/            docker-compose deployment (Label Studio + PostgreSQL, pinned)
configs/           one labeling config XML per task type
automation/        Python scripts against the Label Studio API
services/
  webhook-validator/  FastAPI webhook: validates benchmark submissions on save
docs/              deployment and customization guides, annotator one-pager,
                   development roadmap
```

## Quickstart

```bash
cp .env.example .env        # then edit the secrets
docker compose --env-file .env -f deploy/docker-compose.yml up -d
# open http://localhost:8080, create the admin account (see DEPLOYMENT.md —
# signup is invite-only by default), generate an API token
```

Create a project for a task type:

```bash
pip install -r automation/requirements.txt
export LABEL_STUDIO_URL=http://localhost:8080 LABEL_STUDIO_API_KEY=<token>
python automation/create_project.py --title "Benchmark task intake" --config configs/benchmark-task.xml --stub-tasks 50
python automation/register_webhook.py --project <id>   # instant validation on save
```

Export benchmark submissions to the canonical intake xlsx:

```bash
python automation/export_to_intake_xlsx.py --project <id> -o submissions.xlsx
```

Multi-annotator studies (one project per annotator, progress monitoring,
lossless export of every judgment) are the next build step — see
[docs/ROADMAP.md](docs/ROADMAP.md).

## Documentation

| Document | What it covers |
|---|---|
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | First deployment, owner-account bootstrap, API tokens (incl. the legacy-token pitfall), backups, upgrades, webhook validator ops, security notes |
| [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md) | The four extension layers: labeling configs (form-style vs item-style, validation, `visibleWhen`), REST automation, webhooks, ML backends — plus the benchmark pipeline and the dual-annotation study pattern |
| [docs/ANNOTATOR_QUICKSTART.md](docs/ANNOTATOR_QUICKSTART.md) | One-page annotator handout **template** — log in, open your project, label an item, report a problem. Each study ships a filled copy with its own screenshots |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Build plan, written to be implemented by hand: house rules for `automation/` scripts, then M1–M5 (dual-annotation export, multi-project provisioning, progress monitoring, onboarding, dry-run gate) and M6–M12 for running a shared instance (identity in exports, adjudication, automated backups, health alerts, remote access, wider field support, CI) |

## Data safety

Annotation data never enters this repository: `.gitignore` blocks `data/` (Label Studio media + PostgreSQL volumes), `exports/`, all spreadsheet formats, and `.env` (secrets). The repo holds only configuration and code.

## License

[MIT](LICENSE)
