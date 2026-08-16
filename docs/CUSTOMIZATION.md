# Customization Guide

The platform is customized only through Label Studio's supported extension points — never by forking it (the deployed image stays stock `heartexlabs/label-studio`, pinned in `deploy/docker-compose.yml`). Four layers, in order of preference:

| Layer | When to use | Where it lives here |
|---|---|---|
| 1. Labeling config (XML) | New task type, new form fields, different UI | `configs/*.xml` |
| 2. REST automation | Project setup, bulk import, export into downstream pipelines | `automation/` |
| 3. Webhooks | React to submissions in real time (validation, notifications) | `services/webhook-validator/` |
| 4. ML backend | Model-assisted pre-annotation for a task type | (add under `services/` when needed) |

Start at layer 1 and only move down when the layer above can't do the job. Most "customization" is just an XML file.

## Layer 1 — labeling configs

A labeling config is one `<View>` XML document that defines a task type's entire UI. The two committed configs are the worked examples, one per project shape:

- **Item-style** (`text-classification.xml`): one task per datum. The task JSON's `data` object provides variables — `{"data": {"text": "..."}}` renders through `<Text name="text" value="$text"/>` — and control tags attach to it via `toName`.
- **Form-style** (`benchmark-task.xml`): the annotator *is* the data source. Import N identical stub tasks (`create_project.py --stub-tasks N`); each submission fills one stub. Everything is a control tag; the only `data` field is a one-line brief.

Rules that keep configs working:

- Every control tag needs a unique `name` and a `toName` pointing at a display tag. The `name` becomes the field name in exports — snake_case, English, chosen to match the downstream schema (the benchmark config's names are the intake-xlsx column names 1:1, which is what keeps the export converter trivial).
- **Push validation into the config.** `required="true"`, `<Number min="1" max="6000">`, `<Choices>` enums, `maxSubmissions="1"` on TextAreas — every rule enforced at input time is a dirty-data class that can no longer occur. The xlsx-era failure modes (free-text numbers, invalid enums, wrong headers) died here, not in a validator.
- **Conditional questions** use `visibleWhen`: wrap the follow-up in `<View visibleWhen="choice-selected" whenTagName="verdict" whenChoiceValue="incorrect">…</View>` so it only appears for the answers that need it.
- Start every config with a comment stating the expected task JSON (see both committed files) — it is the config's import contract.

Workflow for a new task type:

1. Copy the closest committed config (or start from a built-in template: Projects → New → Browse Templates, then take the XML) into `configs/<task-type>.xml`.
2. Iterate in the UI: project Settings → Labeling Interface shows a live preview with sample data. When it behaves, save the XML back to the file and commit — **the file in `configs/` is the source of truth**, not whatever a project happens to contain.
3. Create the real project from the file:
   ```bash
   python automation/create_project.py --title "My task" --config configs/<task-type>.xml [--stub-tasks 50]
   ```
4. Import tasks (UI, or `POST /api/projects/<id>/import` for bulk), annotate, export.

**Changing a config after annotation has started is a migration, not an edit.** Renaming or deleting a control tag orphans the existing results silently. Export first; prefer adding new fields over renaming; if a rename is unavoidable, treat pre- and post-change exports as two schema versions in the converter.

## Layer 2 — REST automation

`automation/ls_api.py` is the shared plumbing: plain REST rather than the Python SDK (the REST API is stable across releases; the SDK churns), credentials strictly from `LABEL_STUDIO_URL` / `LABEL_STUDIO_API_KEY`, and error responses surfaced with their bodies (Label Studio puts field-level details there — without this, every failure is an opaque 400).

Its `annotation_fields()` flattens an annotation's `result` list into `{field_name: value}` and understands the three control-tag families the committed configs use — TextArea (`text`, joined), Choices (`choices[0]`), Number (`number`). **If a new config introduces another control tag (Labels, Rating, Taxonomy…), extend `annotation_fields()` in the same style first**; every converter downstream gets the support for free.

Downstream converters follow the `export_to_intake_xlsx.py` pattern: fetch the project's JSON export, flatten each task's **latest non-cancelled annotation** (tasks without annotations are skipped and counted), write the exact format the consumer expects (for benchmark tasks, the canonical intake xlsx). One converter per downstream pipeline, in `automation/`, no shared state beyond `ls_api.py`. Note the one-annotation-per-task assumption: it fits form-style intake, but a dual-annotation study exports *all* annotations per item — its converter must not reuse this latest-wins logic.

## Layer 3 — webhooks

For per-submission side effects — instant shallow validation, notifications. The shipped example is `services/webhook-validator/` (FastAPI, wired into the compose stack), registered per project (idempotent; subscribes to `ANNOTATION_CREATED` / `ANNOTATION_UPDATED` only):

```bash
python automation/register_webhook.py --project <id>
```

Two things to know:

- Inside the compose network the validator is reachable as `validator.internal:8090` — the dotted alias exists because Label Studio's webhook URL validation (Django) rejects bare single-label hostnames like `validator`.
- A webhook validator re-implements only *shallow* rules for instant feedback and is intentionally **not** the source of truth — deep validation belongs downstream, in whatever pipeline consumes the export. Keep it that way for any new webhook; duplicated deep logic drifts.

## Layer 4 — ML backends

None deployed. If a task type would genuinely benefit from pre-annotation, add the backend as a service under `services/` and connect it per project (Settings → Model). Two constraints: pin the model like any other dependency, and **never attach a backend to a verification-style study** (below) — its value is that no model influenced the verdicts.

## The benchmark-task pipeline (the customized part today)

`configs/benchmark-task.xml` replaces the lab's legacy xlsx intake form for benchmark task submissions. Field names mirror the intake-xlsx columns exactly, which is what keeps the export converter trivial:

```
annotator fills form ──▶ webhook validator (instant shallow checks, logs issues)
                    └──▶ export_to_intake_xlsx.py ──▶ submissions.xlsx (canonical intake format)
```

- The **webhook validator** re-implements only the shallow field rules (required, positive minutes, grading enum) for instant feedback.
- Deep QA (data-file existence, packing, answer isolation, oracle verification) is deliberately **not** the platform's job — whatever consumes the xlsx owns deep validation; the platform's job ends at a clean export.

## Verification / dual-annotation studies (pattern)

Some studies do not create labels from scratch — they show an annotator a machine-generated candidate next to its source text and collect a verdict, with each item judged independently by two people and disagreements adjudicated. The community edition has no per-user task assignment and no agreement metrics, so the pattern keeps those concerns *outside* Label Studio and uses it strictly for presentation and collection:

1. **Assignment is computed upstream.** A committed, seeded script decides who judges what (stratification, pair rotation). Import each annotator's batch into a **separate project per annotator** — this is the community-edition substitute for per-user assignment, and it doubles as blinding: annotators cannot see each other's work.
2. **Blinded fields never enter the task JSON.** Anything the annotator must not see (e.g. which model produced a candidate) stays in an upstream mapping file keyed by item id and is joined back at analysis time. If it isn't in the task, no UI setting can leak it.
3. **Conditional follow-ups** (e.g. an error-type question that only appears after a negative verdict) use `visibleWhen` as described under layer 1.
4. **No ML backends, no pre-annotation** on these projects.
5. **Export → canonical CSV → downstream stats.** Export per project, convert into one canonical judgments file (item id, annotator, verdict, timestamps, versions), and compute agreement/adjudication numbers in committed downstream scripts. Dashboard numbers are monitoring, not results.

The dividing line to keep: Label Studio is presentation and collection only. Everything that ends up in a paper — assignment, agreement, adjudication rates — lives in the study's own committed scripts, so the study is reproducible from its repo alone even if the platform changes.

## Upgrades

The image is pinned (`heartexlabs/label-studio:1.23.0`). Upgrading is a deliberate act: back up `data/` (see `DEPLOYMENT.md`), bump the tag, `docker compose up -d`, then re-check each committed config in the labeling-interface preview — tag behavior occasionally changes between minor versions. Never run `:latest`.

## Conventions

- One XML file per task type in `configs/`, English field names, snake_case, a header comment stating the expected task JSON.
- `configs/` is the source of truth for project UIs; the UI preview is a scratchpad.
- Scripts read credentials from `LABEL_STUDIO_URL` / `LABEL_STUDIO_API_KEY` env vars only.
- No annotation data in this repo — exports go to gitignored paths (`exports/`, `*.xlsx`); `data/` (Label Studio media + PostgreSQL) is gitignored and backed up out of band.
