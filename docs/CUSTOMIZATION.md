# Customization Guide

The platform is customized only through Label Studio's supported extension points — never by forking it (the deployed image stays stock `heartexlabs/label-studio`, pinned in `deploy/docker-compose.yml`). Four layers, in order of preference:

| Layer | When to use | Status |
|---|---|---|
| 1. Labeling config (XML) | New task type, new form fields, different UI | **Built** — `configs/*.xml` |
| 2. REST automation | Project setup, bulk import, export into downstream pipelines | Planned — ROADMAP M0-M3 |
| 3. Webhooks | React to submissions in real time (validation, notifications) | Planned — ROADMAP M15 |
| 4. ML backend | Model-assisted pre-annotation for a task type | Not planned; add under `services/` if a task type ever justifies it |

Start at layer 1 and only move down when the layer above can't do the job. Most "customization" is just an XML file — which is why layer 1 is the only layer built so far, and why a study can run end to end through the UI without the rest.

## Layer 1 — labeling configs

A labeling config is one `<View>` XML document that defines a task type's entire UI. The two committed configs are the worked examples, one per project shape:

- **Item-style** (`text-classification.xml`): one task per datum. The task JSON's `data` object provides variables — `{"data": {"text": "..."}}` renders through `<Text name="text" value="$text"/>` — and control tags attach to it via `toName`.
- **Form-style** (`benchmark-task.xml`): the annotator *is* the data source. Import N identical stub tasks — a JSON list of N copies of `{"data": {"brief": "…"}}` — and each submission fills one stub. Everything is a control tag; the only `data` field is a one-line brief.

Rules that keep configs working:

- Every control tag needs a unique `name` and a `toName` pointing at a display tag. The `name` becomes the field name in exports — snake_case, English, chosen to match the downstream schema (the benchmark config's names are the intake-xlsx column names 1:1, which is what keeps the export converter trivial).
- **Push validation into the config.** `required="true"`, `<Number min="1" max="6000">`, `<Choices>` enums, `maxSubmissions="1"` on TextAreas — every rule enforced at input time is a dirty-data class that can no longer occur. The xlsx-era failure modes (free-text numbers, invalid enums, wrong headers) died here, not in a validator.
- **Conditional questions** use `visibleWhen`: wrap the follow-up in `<View visibleWhen="choice-selected" whenTagName="verdict" whenChoiceValue="incorrect">…</View>` so it only appears for the answers that need it.
- Start every config with a comment stating the expected task JSON (see both committed files) — it is the config's import contract.

Workflow for a new task type:

1. Copy the closest committed config (or start from a built-in template: Projects → New → Browse Templates, then take the XML) into `configs/<task-type>.xml`.
2. Iterate in the UI: project Settings → Labeling Interface shows a live preview with sample data. When it behaves, save the XML back to the file and commit — **the file in `configs/` is the source of truth**, not whatever a project happens to contain.
3. Create the real project: **Projects → Create**, then paste the file's contents into **Settings → Labeling Interface → Code**. (ROADMAP M0 replaces this step with one command; until then the paste *is* the step, and `configs/` stays the source of truth for what you paste.)
4. Import tasks — drop a JSON file on the project's **Import** page, or `POST /api/projects/<id>/import` for bulk — then annotate and export.

**Changing a config after annotation has started is a migration, not an edit.** Renaming or deleting a control tag orphans the existing results silently. Export first; prefer adding new fields over renaming; if a rename is unavoidable, treat pre- and post-change exports as two schema versions in the converter.

## Layer 2 — REST automation (planned)

Nothing is built here yet; the UI carries a single project fine. The layer earns its existence at the point where a study needs one project *per annotator* — provisioning ten of those by hand is ten chances to import the wrong batch into the wrong project.

The design is settled even though the code is not, and it is worth reading before the first script, because two of these are expensive to reverse once converters depend on them:

- **One module talks HTTP, nothing else does.** Plain REST rather than the Python SDK — the REST API is stable across releases and the SDK churns. Credentials come from `LABEL_STUDIO_URL` / `LABEL_STUDIO_API_KEY` only, never a flag and never a file. Surface error bodies: Label Studio puts the field-level reason there, and without it every failure looks like an opaque 400.
- **One shared flattener.** An annotation's `result` list becomes `{field_name: value}` in exactly one function, covering the control-tag families the configs actually use — TextArea (`text`, joined), Choices (`choices[0]`), Number (`number`). A new control tag (Labels, Rating, Taxonomy…) is then extended in one place and every converter inherits it.
- **Latest-wins is a trap outside form-style intake.** Flattening the latest non-cancelled annotation per task is right for benchmark submissions and *wrong* for dual annotation, where the second judgment is the entire point. A verification study's converter must emit one row per annotation.

Milestones with interfaces and traps: [ROADMAP.md](ROADMAP.md) M0 for the foundation, M1 for the dual-annotation exporter, M2 for provisioning, M3 for progress.

## Layer 3 — webhooks (planned)

For per-submission side effects — instant shallow validation, notifications. Not deployed; ROADMAP M15 carries the milestone. Three findings from an earlier prototype, kept here because each cost an afternoon to learn:

- **Label Studio rejects bare single-label hostnames in webhook URLs.** A service reachable inside the compose network as `validator` will not register — Django's URL validation refuses it. Give the container a dotted network alias (`validator.internal`) and register that.
- **A validator is the shallow gate, never the source of truth.** Deep validation belongs downstream, in whatever consumes the export. Duplicated deep logic drifts, and the copy living in the webhook is the one nobody remembers to update.
- **Most of what a validator would catch, layer 1 already prevents.** With `required="true"` and enum `<Choices>` on every field, a submission made *through the UI* is clean by construction; the validator's real job is catching what arrives through the API, bypassing the form. Expect its log to read `clean` almost always — that is the design working, not the webhook failing to fire.

## Layer 4 — ML backends

None deployed, and none planned. If a task type would genuinely benefit from pre-annotation, add the backend as a service under `services/` and connect it per project (Settings → Model). Two constraints: pin the model like any other dependency, and **never attach a backend to a verification-style study** (below) — its value is that no model influenced the verdicts.

## The benchmark-task pipeline

`configs/benchmark-task.xml` replaces the lab's legacy xlsx intake form for benchmark task submissions. Its field names mirror the intake-xlsx column names 1:1 — that is not cosmetic, it is what will keep the eventual converter a rename-free pass-through:

```
annotator fills form ──▶ Label Studio project ──▶ export ──▶ intake xlsx
                         (validation lives in                (converter: ROADMAP M16)
                          the config itself)
```

Today the export step is the UI's **Export → CSV**, hand-shaped into the intake sheet. The converter that makes it one command is ROADMAP M16.

- **The config is the validator.** `required="true"`, `<Number min="1" max="6000">` and enum `<Choices>` mean the xlsx-era failure modes — free-text numbers, invalid enums, wrong headers — cannot be produced through the form at all. That is why no webhook is needed to ship this task type.
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
- Scripts, when they exist, read credentials from `LABEL_STUDIO_URL` / `LABEL_STUDIO_API_KEY` env vars only — never a flag, never a file.
- No annotation data in this repo — exports go to gitignored paths (`exports/`, `*.xlsx`); `data/` (Label Studio media + PostgreSQL) is gitignored and backed up out of band.
