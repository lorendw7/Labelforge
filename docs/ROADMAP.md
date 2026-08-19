# Development Roadmap

What the platform needs next, in build order, written to be **implemented by
hand**: each milestone states why it exists, the interface it should expose,
the decisions worth getting right the first time, the traps, and a "done when"
you can actually check. No code here — code lands in `automation/`,
`services/` and `deploy/`.

The scope rule comes first: this repo only gains **generic** capability.
Anything study-specific — the labeling config, who judges what, the judgments
themselves, agreement and adjudication statistics — lives in the study's own
repository (see README § "Repository boundary" and CUSTOMIZATION.md
§ "Verification / dual-annotation studies"). The driver for M1–M5 is the first
dual-annotation verification study going live on this deployment; the
milestones are written so any later study of the same shape reuses them as-is.
M6+ is what multi-person operation needs once that first study has run.

## House rules for anything in `automation/`

Learn these once and every milestone below gets shorter. They are what the
existing four scripts already do:

- **One concern per script, `ls_api.py` for the plumbing.** Credentials come
  from `LABEL_STUDIO_URL` / `LABEL_STUDIO_API_KEY` only — never a flag, never a
  file. New shared helpers (project listing, user lookup) belong in `ls_api.py`
  so the next script inherits them.
- **Plain REST, not the Python SDK.** The REST API is stable across releases;
  the SDK churns. Keep surfacing error bodies the way `_check()` does — Label
  Studio puts the field-level reason in the body, and without it every failure
  looks like an opaque 400.
- **Idempotent, or it will be re-run and duplicate something.** `register_webhook.py`
  is the pattern: look for what you are about to create, skip and say so if it
  is there. A provisioning run that dies halfway must be safe to repeat.
- **Validate everything before mutating anything.** Read all input files, check
  all paths, then start creating. A manifest that is wrong about its tenth
  project must not leave nine projects behind.
- **Separate the pure logic from the HTTP.** Flattening, header derivation and
  table formatting should be functions that take dicts and return dicts — so
  they can be tested against a JSON fixture instead of a live instance. That is
  what makes M1's "done when" checkable without a server.
- **Print one honest summary line** (`exported N … (M skipped)`), and return a
  non-zero exit code on failure so a cron job or a shell loop notices.
- **Never write annotation data into the repo.** Exports go to gitignored paths
  (`exports/`, `*.xlsx`).

## M1 — dual-annotation export (`automation/export_annotations.py`)

**Why.** `export_to_intake_xlsx.py` flattens the **latest** non-cancelled
annotation per task — correct for form-style intake, wrong for dual annotation,
where the second judgment is the entire point (CUSTOMIZATION.md layer 2 already
flags this). Without this exporter a verification study cannot get its data out
of the platform at all.

A scaffold with docstrings and `TODO`s is committed at
`automation/export_annotations.py`; fill it in rather than starting over.

**Interface.**

```bash
python automation/export_annotations.py --project 3 4 5 -o exports/annotations.xlsx
```

**Shape of the output.** One row per (task, non-cancelled annotation) — *all*
annotations, never latest-wins. Three sources feed one row:

| Part | Columns |
|---|---|
| metadata | `project_id`, `task_id`, `annotation_id`, `completed_by`, `created_at`, `updated_at`, `lead_time` |
| task pass-through | every key of the task's `data`, prefixed `data.` |
| answer fields | `ls_api.annotation_fields()` flattened from `result` |

**Decisions worth getting right.**

- **`lead_time` must survive non-null.** It is seconds spent on that judgment,
  it lives on the annotation top level (not inside `result`), Label Studio
  gives it for free, and verification studies depend on it. If it arrives null
  in the sheet, the export is broken even though it looks fine.
- **The header cannot be hardcoded.** Answer fields depend on the labeling
  config, `data.` keys depend on what was imported. Derive the header from the
  rows, keep the order stable across runs, and put metadata first, then `data.`
  columns, then answer fields.
- **Rows are sparse.** An optional field one annotator left blank is a missing
  key. Read each row *through* the header, so a gap becomes an empty cell
  instead of shifting the rest of the row one column left — silent, and fatal
  downstream.
- **The `data.` prefix exists to stop collisions.** A task data key and an
  answer field can legitimately share a name.
- Skip annotations with `was_cancelled` true, skip and count tasks left with
  none — same reporting style as the other exporter.
- Conversion into a study's canonical schema stays in the study repo. This
  script's only job is getting everything out losslessly.

**Done when:** on a test project with two annotations on each of N tasks, the
output has 2N rows and `lead_time` is non-null on every row. Write that as a
fixture test against the pure functions (`rows_from_tasks`, `columns`) so it
re-runs without an instance (M12).

## M2 — multi-project provisioning (`automation/provision_study.py`)

**Why.** One project per annotator is the community-edition substitute for
per-user assignment, and it doubles as blinding — annotators cannot see each
other's work (CUSTOMIZATION.md). Doing that by hand for ten annotators is ten
chances to import the wrong batch into the wrong project.

**Interface.** A manifest plus one shared labeling config:

```bash
python automation/provision_study.py --manifest /path/to/study/projects.json \
    --config /path/to/study/verify.xml --dry-run
```

```json
[
  {"title": "verify — annotator A", "tasks": "batches/a.jsonl"},
  {"title": "verify — annotator B", "tasks": "batches/b.jsonl"}
]
```

Per entry: `title`, a `tasks` file (JSON list or `.jsonl` of Label Studio task
objects), optionally its own `config`, optionally `stub_tasks` for form-style
projects. A documented loop over `create_project.py` + bulk import is an
acceptable first version — the manifest is what makes it reviewable.

**Decisions worth getting right.**

- **Accept paths outside this repo.** Studies keep their labeling config and
  batches private and pass them at creation time. Resolve relative manifest
  paths against the manifest's own directory, not the working directory — that
  is the only rule a user can predict.
- **Validate first, create second** (house rules), and make `--dry-run` work
  **offline** so a manifest can be checked before there is an instance to talk
  to.
- **Idempotency by project title.** Fetch existing projects, skip titles that
  exist, say which id they matched. Titles are also what annotators see and
  what `progress.py` filters on, so a naming convention per study is worth
  agreeing on up front.
- **Import in chunks.** A single import body with thousands of tasks gets
  rejected; a few hundred per request is safe.
- **Project listing is paginated** on some releases and a bare list on others.
  Put that behind an `ls_api` helper once.
- Account invites stay manual (**Organization → Add people**) — say so in the
  final summary line, so nobody assumes provisioning finished the job.

**Done when:** one documented command sequence produces N populated projects
with nothing left manual except account invites, and re-running it creates
nothing.

## M3 — progress monitoring (`automation/progress.py`)

**Why.** A study lead needs to spot a lagging annotator in week one, not at the
deadline. Per-project counts (tasks, completed, remaining) against an optional
quota, printed as a table.

**Interface.**

```bash
python automation/progress.py --project 3 4 5
python automation/progress.py --match "verify —" --quota 120
```

`--match` filtering on the title is what makes it usable for a study with one
project per annotator; without it you read the whole instance.

**Decisions worth getting right.**

- The project detail response already carries the counts (`task_number`,
  `num_tasks_with_annotations`, `total_annotations_number`) — no need to page
  through tasks. Treat them as possibly absent on a fresh project and degrade
  visibly (`?`) rather than crashing or printing a wrong zero.
- The denominator is the quota when given, the task count otherwise. Say which
  one you used in the output.
- Keep the table formatting a pure function of the rows; it is the one piece
  worth a test, because column drift is invisible until someone screenshots it.
- **Monitoring only.** Neither this output nor the Label Studio dashboard ever
  feeds a study's reported numbers; those come from the study's own scripts over
  exported data. Put that sentence in the script's docstring too.

**Done when:** one command prints done-vs-quota for a list of project ids.

## M4 — annotator onboarding (deployment work, not code)

The bar: a new annotator needs a browser and an invite link, nothing else.

- Lab-server deployment per DEPLOYMENT.md, one stable URL reachable by all
  annotators (VPN if off-network).
- Accounts via **Organization → Add people**; signup stays closed; every
  annotator logs in once *before* the study's kickoff session, so login
  problems die ahead of it.
- The generic one-page handout template is committed at
  [ANNOTATOR_QUICKSTART.md](ANNOTATOR_QUICKSTART.md). Each study ships its own
  filled copy — placeholders replaced, screenshots of its actual form — inside
  its guideline packet, and walks through it live at kickoff.
- Nightly backup cron (DEPLOYMENT.md) enabled for the whole production window,
  dumps copied off the machine.

*Remaining:* the deployment steps themselves — see
[DEPLOYMENT.md § Onboarding annotators](DEPLOYMENT.md#onboarding-annotators).

*Done when:* a new annotator gets from invite link to a first submitted test
annotation with no help beyond the one-pager.

## M5 — end-to-end dry run (gate)

Before any study's real batch: ~10 dummy tasks through the full chain —
provision (M2) → two people label in the UI → export (M1) → the study's own
convert + statistics scripts. Run once, end to end, with two *real* accounts
rather than one person twice; that is what exercises `completed_by`. This is
where schema drift, a missing `lead_time`, or a permissions surprise surfaces —
not in week two of production.

---

## After the first study — collaboration and operations

M1–M5 get one study through the door. These are what a shared, multi-person
instance needs to stay trustworthy afterwards. Independent of each other; pick
by what hurts.

### M6 — annotator identity in exports

Annotations carry `completed_by` as a numeric user id, which means every
downstream join needs a mapping nobody has written down. Add an **opt-in** flag
to the M1 exporter (`--emails`) that resolves ids to emails via the users
endpoint and emits one extra column next to `completed_by`.

Opt-in on purpose: an export with emails in it is personal data in a
spreadsheet, so it should be a deliberate choice, and a study that publishes
per-annotator numbers usually wants pseudonyms (`annotator_1`) instead — that
mapping belongs in the study repo. Keep the id column either way; it is the
stable key.

*Done when:* the exporter can produce both forms, and the default is still
ids only.

### M7 — adjudication round support

Dual annotation produces disagreements, and someone has to settle them. The
generic half is provisioning: the study computes the disagreement set and
writes it as one more batch, then M2 imports it into an adjudication project
with its own labeling config (both judgments shown, one field for the
resolution). Verify no new script is needed — if M2's manifest already covers
it, the deliverable is a documented pattern in CUSTOMIZATION.md, not code.
Resolve that question before writing anything.

*Done when:* CUSTOMIZATION.md § dual-annotation studies has an adjudication
step someone can follow, and it demonstrably works on the M5 dry-run data.

### M8 — backups that run themselves, and a restore drill

DEPLOYMENT.md documents the `pg_dump` command; a documented command is not a
backup. Ship a small script under `deploy/` that dumps the database and media,
rotates old copies, and exits non-zero when something failed — then install it
as a cron job and **restore it once into a scratch stack**. An untested backup
is a guess, and with several annotators the data represents person-days of
work that cannot be recreated.

*Done when:* a nightly dump lands automatically, a copy leaves the machine, and
a restore has been performed at least once.

### M9 — is it up? (health check + alert)

A lab desktop that has silently stopped serving is indistinguishable from a
working one until an annotator says so. A periodic check of the app's health
endpoint plus the validator's `/healthz`, alerting somewhere a human reads
(email, chat webhook), turns a lost afternoon into a five-minute fix.

*Done when:* stopping the app container produces an alert without anyone
looking.

### M10 — reachable from wherever annotators are

Once annotators are off-network this becomes the blocking issue, not a nicety.
Two supported answers, both already sketched in DEPLOYMENT.md: the lab VPN, or
a mesh VPN on the server plus each annotator's machine. If the instance ever
must be reachable directly, it goes behind a TLS reverse proxy (nginx or Caddy)
as a compose profile — never port 8080 on the public internet.

*Done when:* an annotator on a home network reaches the same URL that goes into
invite links, over TLS or VPN.

### M11 — widen `annotation_fields()` with the configs

`ls_api.annotation_fields()` understands TextArea, Choices and Number — the
three families the committed configs use. The first config that adds Labels,
Rating or Taxonomy will export silently empty columns unless the helper is
extended first. Extend it in the same style, add a fixture test per family, and
keep it the single place that knows how a `result` item becomes a value; every
converter downstream inherits the fix.

Same spirit, cheaply: a pre-import check that a task file's `data` keys match
the `$variables` a labeling config references. Getting that wrong shows up as
blank text in front of an annotator on labeling day.

*Done when:* a config using a fourth control-tag family exports correctly, with
a test covering it.

### M12 — tests and CI

The pure functions from M1–M3 are the whole test surface: flattening, header
derivation, filtering, table rendering. Put fixtures under `automation/tests/`
(a `conftest.py` that puts `automation/` on the import path is enough), declare
the dev dependency separately from the runtime one, and run them on push with a
GitHub Actions workflow. Small surface, but it is what keeps a Label Studio
upgrade from quietly changing an export.

*Done when:* `python -m pytest automation/tests` passes locally and in CI on
every push.

### M13 — idempotent import by data key

`register_webhook.py` is idempotent, and M2 makes provisioning idempotent *by
project title* — which protects the project but says nothing about what is
inside it. Import the same batch twice and every item exists twice. That is not
a cosmetic problem: a duplicated task splits one item in two, so the pair of
independent judgments a study is counting becomes one annotator judging the same
item twice. It corrupts agreement statistics without corrupting anything you can
see in the UI. Any study that imports its corpus in waves rather than one batch,
or whose first import died halfway, meets this on an ordinary Tuesday.

The fix is a **declared identity key** on the import path (`--key item_id`):
before creating anything, sweep the project once for the existing values of that
key in each task's `data`, and skip the incoming tasks that already have one.
The sweep belongs in `ls_api.py` next to the project-listing helper, so
provisioning and any later re-import inherit the same behaviour.

**Decisions worth getting right.**

- **The key is declared, not guessed.** Studies name their identity column
  differently, and defaulting to one is how an import ends up silently
  non-idempotent. Requiring the flag is the honest interface. An incoming task
  that lacks the key is an error, not a skip — the batch and the key disagree,
  and importing it creates a task nobody can match later.
- **Duplicates inside the incoming batch are an error too**, caught before the
  first task is created — validate everything before mutating anything.
- **One paged sweep, compared in memory.** Per-task lookups turn a 2,000-item
  import into 2,000 requests. Task listing is paginated, and the response shape
  differs across releases in the same way project listing does, which is the
  argument for putting it behind an `ls_api` helper once.
- **Exact string comparison, no normalisation.** A study whose ids need
  normalising should normalise them when it writes the batch. A matcher that
  quietly folds case or trims punctuation is one nobody can predict.
- **Skip, never update or delete.** Idempotent means safe to re-run, not
  synchronised. Overwriting a task that already carries annotations is how a
  study loses judgments, and no flag on an import script should be able to do
  it. A study that genuinely needs to correct imported data does it as a new
  batch with new ids.
- Print the usual honest summary line — `imported N, skipped M already present`
  — because "nothing happened" and "everything was already there" look identical
  otherwise.

*Done when:* re-running a completed import creates nothing and reports every
task as skipped, a partly-overlapping second wave imports only the new items,
and a batch with a missing or duplicated key fails before the first task is
created.

## Ordering

M1 and M3 are independent and can start any time. M2 must precede the first
study's import; M4 precedes its kickoff session; M5 gates production labeling.
After that: M8 and M9 before the instance carries anyone else's work, M10 as
soon as an annotator is off-network, M6/M7 when the first study reaches
analysis, M11 when a new task type needs it, M13 as soon as a study imports in
waves rather than in one batch, M12 whenever you want the earlier milestones to
stay correct.

## Non-goals (standing)

- No fork, no patched frontend — stock pinned image only (README).
- No ML backends or pre-annotation on verification-style projects
  (CUSTOMIZATION.md layer 4).
- No study identifiers in committed configs or docs; studies pass their
  labeling config at project-creation time.
- No analysis code in this repo: agreement, adjudication, and timing
  statistics belong to the study repository.
- No per-user permission engineering to fake assignment — one project per
  annotator is the supported answer; blinding comes from what you import, never
  from role settings.
