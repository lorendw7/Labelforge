# Development Roadmap

What the platform needs next, in build order. The scope rule comes first:
this repo only gains **generic** capability. Anything study-specific — the
labeling config, who judges what, the judgments themselves, agreement and
adjudication statistics — lives in the study's own repository (see README
§ "Repository boundary" and CUSTOMIZATION.md § "Verification /
dual-annotation studies"). The driver for M1–M5 is the first
dual-annotation verification study going live on this deployment; the
milestones are written so any later study of the same shape reuses them
as-is.

## M1 — dual-annotation export (`automation/`)

`export_to_intake_xlsx.py` flattens the **latest** non-cancelled annotation
per task — correct for form-style intake, wrong for dual annotation
(CUSTOMIZATION.md layer 2 already flags this). Add a generic exporter that:

- takes a list of project ids,
- emits one row per (task, non-cancelled annotation) — *all* annotations,
  never latest-wins,
- flattens result fields via `ls_api.annotation_fields()`,
- carries the columns downstream stats need: task id, the task's `data`
  fields passed through, `completed_by`, created/updated timestamps, and
  `lead_time` (seconds per judgment — Label Studio provides it for free
  and verification studies depend on it; it must survive export non-null).

Conversion into a study's canonical schema stays in the study repo; this
exporter just gets everything out losslessly.

*Done when:* on a test project with two annotations on each of N tasks,
the output has 2N rows and `lead_time` is non-null on every row.

## M2 — multi-project provisioning

One project per annotator is the community-edition substitute for per-user
assignment, and doubles as blinding (CUSTOMIZATION.md). Make standing up a
study one documented step: N projects from one labeling config, each
importing that annotator's pre-computed batch. Either a documented loop
over `create_project.py` + bulk import, or a small `provision_study.py`
reading a manifest (`title, config path, tasks file` per project). Must
accept a config path **outside** this repo — studies may keep their XML
private and pass it at creation time.

*Done when:* one documented command sequence produces N populated projects
with nothing left manual except account invites.

## M3 — progress monitoring

`automation/progress.py`: per-project counts (tasks, completed, remaining)
against an optional quota, printed as a table — so a study lead can spot a
lagging annotator early. Monitoring only: neither this script's output nor
the dashboard ever feeds a study's reported numbers; those come from the
study's own scripts over exported data.

*Done when:* one command prints done-vs-quota for a list of project ids.

## M4 — annotator onboarding (deployment work, not code)

The bar: a new annotator needs a browser and an invite link, nothing else.

- Lab-server deployment per DEPLOYMENT.md, one stable URL reachable by all
  annotators (VPN if off-network).
- Accounts via **Organization → Add people**; signup stays closed; every
  annotator logs in once *before* the study's kickoff session, so login
  problems die ahead of it.
- A generic one-page **annotator quickstart** template in `docs/` (log in
  → open your project → read the item → answer → submit; where to flag a
  problem). Each study ships its own filled copy — with screenshots of its
  actual form — inside its guideline packet, and walks through it live at
  kickoff.
- Nightly backup cron (DEPLOYMENT.md) enabled for the whole production
  window, dumps copied off the machine.

*Done when:* a new annotator gets from invite link to a first submitted
test annotation with no help beyond the one-pager.

## M5 — end-to-end dry run (gate)

Before any study's real batch: ~10 dummy tasks through the full chain —
provision (M2) → two people label in the UI → export (M1) → the study's
own convert + statistics scripts. Run once, end to end. This is where
schema drift, a missing `lead_time`, or a permissions surprise surfaces —
not in week two of production.

## Ordering

M1 and M3 are independent and can start any time. M2 must precede the
first study's import; M4 precedes its kickoff session; M5 gates production
labeling.

## Non-goals (standing)

- No fork, no patched frontend — stock pinned image only (README).
- No ML backends or pre-annotation on verification-style projects
  (CUSTOMIZATION.md layer 4).
- No study identifiers in committed configs or docs; studies pass their
  labeling config at project-creation time.
- No analysis code in this repo: agreement, adjudication, and timing
  statistics belong to the study repository.
