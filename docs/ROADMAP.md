# Development Roadmap

What the platform needs next, in build order, written to be **implemented by
hand**: each milestone states why it exists, the interface it should expose,
the decisions worth getting right the first time, the traps, and a "done when"
you can actually check.

**Where this stands today.** The repository ships the deployment (`deploy/`)
and the labeling configs (`configs/`). There is no Python in it. A study can
already run end to end through the Label Studio UI — create project, paste
config, import a JSON file, label, export — and for a *single* project that is
genuinely enough; do not build automation to avoid a UI click. Each milestone
below buys back something the UI makes either impossible (exporting *both*
judgments per item) or unreliable at scale (ten annotators, ten manual
imports, one wrong batch). Code lands in `automation/` and `services/`, which
M0 and M15 create.

The scope rule comes first: this repo only gains **generic** capability.
Anything study-specific — the labeling config, who judges what, the judgments
themselves, agreement and adjudication statistics — lives in the study's own
repository (see README § "Repository boundary" and CUSTOMIZATION.md
§ "Verification / dual-annotation studies"). The driver for M1–M5 is the first
dual-annotation verification study going live on this deployment; the
milestones are written so any later study of the same shape reuses them as-is.
M6+ is what multi-person operation needs once that first study has run.

## House rules for anything in `automation/`

Learn these once and every milestone below gets shorter. Nothing implements
them yet, so they are not a description — they are the precedent M0 sets and
every later script copies. That cuts both ways: a shortcut taken in the first
script is inherited by all of them.

- **One concern per script, `ls_api.py` for the plumbing.** Credentials come
  from `LABEL_STUDIO_URL` / `LABEL_STUDIO_API_KEY` only — never a flag, never a
  file. New shared helpers (project listing, user lookup) belong in `ls_api.py`
  so the next script inherits them.
- **Plain REST, not the Python SDK.** The REST API is stable across releases;
  the SDK churns. Put every response through one checker that raises with the
  response **body** attached — Label Studio puts the field-level reason there,
  and without it every failure looks like an opaque 400.
- **Idempotent, or it will be re-run and duplicate something.** Look for what
  you are about to create; if it is already there, skip it and say which
  existing thing it matched. A provisioning run that dies halfway must be safe
  to repeat — and it will die halfway eventually.
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

## M0 — the automation foundation (`automation/`)

**Why.** M1, M2 and M3 each assume two things that do not exist: a module that
knows how to talk to the instance, and a way to create a project from a
committed config without pasting XML into a browser. Build them once, first.
The alternative — letting whichever milestone gets written first grow its own
plumbing — produces a module shaped by a single caller, which the second caller
then works around instead of extending.

**Interface.**

```bash
python automation/create_project.py --title "Benchmark task intake" \
    --config configs/benchmark-task.xml --stub-tasks 50
```

`ls_api.py` is the shared plumbing and holds four things, no more: credentials
and base URL from the environment, `get`/`post` wrapped in the body-preserving
error check, the `result`-list flattener, and a project lister that copes with
pagination.

**Decisions worth getting right.**

- **The flattener is the load-bearing part**, not the HTTP. It turns an
  annotation's `result` list into `{field_name: value}` for TextArea (`text`,
  joined), Choices (`choices[0]`) and Number (`number`) — the three families
  the committed configs use. Every exporter downstream depends on it, so it is
  a pure function over dicts and it gets a fixture test on day one (M11 widens
  it, M12 puts it in CI).
- **Project listing is paginated on some releases and a bare list on others.**
  Discover that once, hide it in the helper, and no later milestone rediscovers
  it. M2 and M13 both need it.
- **`--stub-tasks N` belongs here**, because form-style configs are unusable
  without it: the annotator is the data source, so the project needs N identical
  `{"data": {"brief": "…"}}` stubs to have N submission slots.
- **Idempotent by title**, per the house rules — re-running must report the
  existing project's id, not create a second one with the same name.
- Keep `requirements.txt` to what is actually imported (`requests`, and
  `openpyxl` once M1 writes xlsx). A dependency added speculatively is one
  nobody can later justify removing.

**Done when:** one command creates a project from a file in `configs/` and
prints its id; re-running the same command creates nothing and says which
project it matched; and the flattener has a fixture test that runs without an
instance.

## M1 — dual-annotation export (`automation/export_annotations.py`)

**Why.** The UI's own export, and any converter written for form-style intake,
gives you the **latest** non-cancelled annotation per task — correct for
benchmark submissions, wrong for dual annotation, where the second judgment is
the entire point. Without this exporter a verification study cannot get its
data out of the platform at all, which makes it the one milestone that blocks
the study rather than merely slowing it.

Depends on M0 for the flattener and the HTTP plumbing.

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
- **Use M0's project lister** rather than calling the endpoint directly; it
  already absorbs the difference between releases that paginate the response
  and releases that return a bare list.
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
endpoint — plus any service M15 adds later — alerting somewhere a human reads
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

M0's flattener understands TextArea, Choices and Number — the three families
the committed configs use. The first config that adds Labels, Rating or
Taxonomy will export silently empty columns unless the helper is extended
first. Extend it in the same style, add a fixture test per family, and
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

M0 and M2 make creation idempotent *by project title* — which protects the
project but says nothing about what is inside it. Import the same batch twice and every item exists twice. That is not
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
  import into 2,000 requests. Task listing is paginated and varies across
  releases exactly as project listing does, so it belongs beside M0's project
  lister rather than inline here.
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

### M14 — the study-side repository the boundary depends on

**Why.** The repository boundary is stated in three places (README
§ "Repository boundary", CUSTOMIZATION.md § dual-annotation studies, and the
standing non-goals below) and every milestone above defers something to "the
study repo". No such repo has ever existed. That is not a documentation gap —
it means **the boundary has never been exercised**, and the first real study
will improvise assignment, blinding and agreement code under deadline. Whatever
it improvises becomes the lab's de-facto standard.

Four phases, and the first is worth doing before M1 rather than after.

**Phase 1 — write the contract (a document, half a day).** The boundary is
currently three scattered assertions. Turn it into one page that answers two
questions: what lives on each side, and *what crosses*. Only two artefacts
cross, which is the point worth making:

| Direction | Artefact |
|---|---|
| platform → study | M1's export — one row per annotation |
| study → platform | M2's manifest, a labeling config, batch files |

**Phase 2 — version the export schema (small, after M1).** The platform side of
the seam is that export, and today its column set is whatever the code happens
to emit. A study's statistics bind to those columns; then M6 adds `--emails` or
M11 widens the flattener, the columns shift, and the study's numbers are wrong
without anything failing. Declare the schema, give it a version, and have the
exporter stamp the version into the file it writes. M12 is where it gets locked
by a test.

**Phase 3 — the study template (the actually missing artefact).** A separate
repository, four directories, nothing clever:

- `batches/` — the seeded script that decides who judges what (stratification,
  pair rotation), writing one task file per annotator
- `blinding/` — the item-id-keyed map of everything the annotator must not see,
  joined back only at analysis time and **never** present in a task file
- `analysis/` — agreement, adjudication rates, timing, computed from the
  platform export
- `projects.json` + a README naming the commands in order

**Phase 4 — run the seam end to end (fold into M5).** M5 is currently a
platform-side dry run. Extend it across the boundary: the study repo generates
batches → M2 provisions → two people label → M1 exports → the study repo
produces an agreement number. Until that has happened once, the boundary is a
claim.

**Decisions worth getting right.**

- **The template is a repository you copy, not a generator.** A study repo is
  created once in its life; a cookiecutter would be a second thing to maintain
  for no recurring benefit.
- **The study repo must not import platform code.** This is the only rule here
  that will actually be broken, and it will be broken for a good reason — some
  helper in `ls_api.py` does exactly what the analysis script needs. The moment
  it does, the study stops being reproducible from its own repo, which is the
  entire purpose of the split. The study consumes *exported files*, nothing
  else. Worth a one-line CI grep in the template.
- **Do not fork this repository to create a study repo.** A fork arrives with
  `automation/` already in it, and the rule above dies on day one — not by
  anyone's decision, just by proximity.
- **Provisioning is generic, assignment is not.** M2 reads a manifest and
  creates projects; *deciding what goes in each batch* is the study's. M2 is
  already scoped this way — phase 1 writes it down so it stays that way.
- **The platform emits numeric ids, always.** Pseudonymisation
  (`annotator_1`) is a study-side mapping (M6).

**Done when:** a new study can be started from the template's README alone —
generate batches, provision, label, export, produce an agreement number — with
no change to this repository, and with no line in the study repo importing from
it.

### M15 — a validation webhook, if a task type earns one

**Why.** Label Studio can POST every submission to a service as it is saved,
which is the only way to give an annotator feedback *at save time* rather than
at analysis time. A FastAPI service under `services/`, wired into the compose
stack and registered per project on `ANNOTATION_CREATED` / `ANNOTATION_UPDATED`.

The honest case for deferring it: **layer 1 already prevents most of what it
would catch.** With `required="true"` and enum `<Choices>` on every field, a
submission made through the UI cannot carry an empty required field or an
invalid enum. A validator's remaining value is real but narrow — catching what
arrives through the API bypassing the form, and cross-field rules a config
cannot express (this field must be empty *unless* that one is set).

Traps, from a prototype that worked:

- **Label Studio rejects bare single-label hostnames in webhook URLs.** A
  container reachable as `validator` will not register; Django's URL validation
  refuses it. Give it a dotted compose alias — `validator.internal` — and
  register that. This costs an afternoon to rediscover.
- **Expect the log to read `clean` almost always.** That is layer 1 working, not
  the webhook failing. Anyone judging the service by how much it catches will
  conclude wrongly that it is broken.
- **Shallow rules only.** Deep validation belongs downstream; a second copy of
  it in the webhook is the copy that drifts.

**Done when:** a deliberately malformed submission POSTed through the API
produces a logged issue list naming every violated rule, and a normal UI
submission produces one clean line.

### M16 — benchmark intake converter

**Why.** `configs/benchmark-task.xml` exists to replace an xlsx intake form,
and its field names are the intake sheet's column names 1:1 — so the converter
is a pass-through with no renaming, and today that pass-through is done by hand
in a spreadsheet after a UI export. One command, one project id, one file:

```bash
python automation/export_to_intake_xlsx.py --project <id> -o submissions.xlsx
```

Form-style intake is the one place **latest-wins is correct** — one submission
fills one stub, and a re-opened task should contribute its final state, not
both. That is the opposite of M1's rule, and the two exporters must not share
that logic however similar they look. Skip tasks with no annotation and report
the count.

**Done when:** one command turns a benchmark project into a sheet the intake
pipeline accepts unedited.

## Ordering

**M0 comes first and blocks M1, M2, M3 and M13** — all four assume its
plumbing. Two things need no code and can run alongside it from day one: M4
(deployment work) and M14 phase 1 (the boundary contract), and the latter is
worth finishing before M1 fixes an export layout by accident.

Then M1 and M3 are independent of each other; M2 must precede the first study's
import; M4 precedes its kickoff session; M5 gates production labeling and is
also where M14 phase 4 exercises the boundary for the first time.

After the first study: M8 and M9 before the instance carries anyone else's
work, M10 as soon as an annotator is off-network, M6/M7 when the first study
reaches analysis, M11 when a new task type needs it, M13 as soon as a study
imports in waves rather than in one batch, M12 whenever you want the earlier
milestones to stay correct.

M15 and M16 are genuine but unblocking — M16 when hand-shaping the intake sheet
starts to grate, M15 only if a task type turns out to need a rule its labeling
config cannot express.

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
