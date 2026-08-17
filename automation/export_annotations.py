"""Export *all* annotations from Label Studio projects into one xlsx.

One row per (task, non-cancelled annotation) — never latest-wins, so
dual-annotation studies keep both judgments. Conversion into a study's
canonical schema happens in the study's own repository; this exporter just
gets everything out losslessly.

Example:
  python export_annotations.py --project 3 4 5 -o annotations.xlsx
"""

from __future__ import annotations

import argparse

import openpyxl

from ls_api import annotation_fields, get

# Metadata columns, in order, emitted before the pass-through task.data
# columns and the flattened answer fields.
META_COLUMNS = [
    "project_id",
    "task_id",
    "annotation_id",
    "completed_by",
    "created_at",
    "updated_at",
    "lead_time",
]

# Prefix for pass-through task.data keys, so a data key can never collide
# with an answer field of the same name.
DATA_PREFIX = "data."


def annotation_row(task: dict, annotation: dict, project_id: int) -> dict[str, object]:
    """Flatten one (task, annotation) pair into a single {column: value} row.

    Three sources feed one row:
      - META_COLUMNS      from `annotation` top level (+ the task and project ids)
      - DATA_PREFIX cols  from `task["data"]`, passed through unchanged
      - answer fields     from `annotation_fields(annotation)`

    `lead_time` lives on the annotation top level, not in `result` — it must
    survive to the sheet non-null.
    """
    # TODO: build and return the row dict.
    row: dict[str, object] = {
        "project_id": project_id,
        "task_id": task["id"],
        "annotation_id": annotation["id"],
        "completed_by": annotation.get("completed_by"),
        "created_at": annotation.get("created_at"),
        "updated_at": annotation.get("updated_at"),
        "lead_time": annotation.get("lead_time"),
    }

    raise NotImplementedError


def rows_from_tasks(tasks: list[dict], project_id: int) -> list[dict[str, object]]:
    """Expand an exported task list into one row per non-cancelled annotation.

    Skips annotations with `was_cancelled` true, and tasks left with none.
    Pure: no HTTP, so it can be tested against a JSON fixture.
    """
    # TODO: iterate tasks -> annotations, filter, call annotation_row.

    raise NotImplementedError


def columns(rows: list[dict[str, object]]) -> list[str]:
    """Derive the sheet header from the rows.

    The set of task.data keys and answer fields is not known ahead of time —
    it depends on the labeling config and on what was imported. Order must be
    stable across runs and rows may be sparse (an optional field one annotator
    left blank).
    """
    # TODO: return META_COLUMNS + data columns + answer-field columns.
    raise NotImplementedError


def write_xlsx(rows: list[dict[str, object]], header: list[str], out: str) -> None:
    """Write the rows to `out`, one sheet, `header` as the first line.

    Read each row *through* `header` so a missing key becomes an empty cell
    rather than shifting the remaining values left.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "annotations"
    # TODO: append the header, then one line per row.
    wb.save(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--project",
        required=True,
        nargs="+",
        type=int,
        help="one or more Label Studio project ids",
    )
    ap.add_argument("-o", "--out", default="annotations.xlsx")
    args = ap.parse_args()

    # TODO: for each project id, GET /api/projects/{id}/export?exportType=JSON
    # (see export_to_intake_xlsx.py), collect rows, then derive the header and
    # write the sheet. Report exported rows and skipped tasks like the other
    # exporter does.
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
