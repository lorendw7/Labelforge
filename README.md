# labelforge

> A general-purpose annotation platform for the lab, built on [Label Studio](https://labelstud.io/) — a pinned deployment, one labeling config per task type, and the build plan for everything above them.

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
   annotators ────────▶ │  Label Studio (Docker)       │   ← this repo deploys
   (browser)            │  ├─ project per task type    │     and configures this
                        │  ├─ labeling config (XML)    │
                        │  └─ PostgreSQL               │
                        └──────────────┬───────────────┘
                                       │ export (UI or REST)
                                       ▼
                          ┌──────────────────────────┐
                          │  the study's own repo    │   ← never this repo
                          │  assignments, judgments, │
                          │  agreement, results      │
                          └──────────────────────────┘
```

- **labelforge (this repo)**: platform deployment + per-task customization. Generic; every lab task type lives here as a labeling config.

**What is built today:** the deployment and the labeling configs. The automation layer (provisioning, exporters, progress) and the validation webhook are designed but not written — they are milestones in [docs/ROADMAP.md](docs/ROADMAP.md), not directories. Until they exist, everything is done through the Label Studio UI, which is enough to run a study end to end.

### Repository boundary (deliberate)

The platform is generic; the science is not. This repo holds what it takes to put the annotation platform in front of people: the Docker deployment, one labeling-config XML per task type, and (once built) scripts that talk to the Label Studio API. It contains no analysis and no research results — each study keeps its assignments, judgments, and statistics in its own repository, so a study stays reproducible from its own repo even if the platform changes. Rule of thumb: **a new study or task type adds a labeling config here; everything that ends up in a paper lives in the study's repo.**

## Repository layout

```
deploy/            docker-compose deployment (Label Studio + PostgreSQL, pinned)
configs/           one labeling config XML per task type
docs/              deployment and customization guides, annotator one-pager,
                   development roadmap
```

`automation/` and `services/` appear throughout the roadmap as the places code
will land. They do not exist yet; the first milestone creates the former.

## Quickstart

```bash
cp .env.example .env        # then edit the secrets
docker compose --env-file .env -f deploy/docker-compose.yml up -d
# open http://localhost:8080, create the admin account (see DEPLOYMENT.md —
# signup is invite-only by default), generate an API token
```

Create a project for a task type, entirely in the UI:

1. **Projects → Create**, name it after the study and the annotator.
2. **Settings → Labeling Interface → Code**, paste the contents of the task
   type's file from `configs/`, save.
3. **Import**, and drop in a JSON file of tasks.

A task file is a list of objects with a `data` key, and the keys inside `data`
must match the `$variables` the labeling config references — that is the whole
contract:

```json
[
  {"data": {"text": "The new library cut our build time to forty seconds."}},
  {"data": {"text": "The release notes were missing and the migration failed."}}
]
```

For the form-style config (`benchmark-task.xml`) the only variable is `$brief`,
so N identical stub tasks give N submission slots:

```json
[
  {"data": {"brief": "Submit one benchmark task using the fields below."}},
  {"data": {"brief": "Submit one benchmark task using the fields below."}}
]
```

Export from **Export** in the project, as JSON or CSV.

The UI covers one project comfortably. What it does not cover — provisioning
one project per annotator, exporting *every* judgment rather than the latest,
watching progress across a study — is what the automation layer is for, and
that is the build plan in [docs/ROADMAP.md](docs/ROADMAP.md).

## Documentation

| Document | What it covers |
|---|---|
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | First deployment, owner-account bootstrap, API tokens (incl. the legacy-token pitfall), backups, upgrades, webhook validator ops, security notes |
| [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md) | The four extension layers: labeling configs (form-style vs item-style, validation, `visibleWhen`), REST automation, webhooks, ML backends — plus the benchmark pipeline and the dual-annotation study pattern |
| [docs/ANNOTATOR_QUICKSTART.md](docs/ANNOTATOR_QUICKSTART.md) | One-page annotator handout **template** — log in, open your project, label an item, report a problem. Each study ships a filled copy with its own screenshots |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Build plan, written to be implemented by hand: house rules for automation code, M0 (the foundation everything else assumes), M1–M5 to get one dual-annotation study through the door, M6–M13 for running a shared instance, M14 for the study-side repository the boundary depends on, M15–M16 for the pieces nothing is blocked on |

## Data safety

Annotation data never enters this repository: `.gitignore` blocks `data/` (Label Studio media + PostgreSQL volumes), `exports/`, all spreadsheet formats, and `.env` (secrets). The repo holds only configuration, documentation and (once built) code.

## License

[MIT](LICENSE)
