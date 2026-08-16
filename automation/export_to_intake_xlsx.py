"""Export benchmark submissions from Label Studio into the canonical intake xlsx.

Label Studio JSON export -> canonical intake spreadsheet. Deep QA of the
spreadsheet is the consumer's concern, downstream of this export.

Example:
  python export_to_intake_xlsx.py --project 3 -o submissions.xlsx
"""

from __future__ import annotations

import argparse

import openpyxl

from ls_api import annotation_fields, get

# Canonical intake xlsx headers, in order.
COLUMNS = [
    ("title", "Title"),
    ("domain", "Domain"),
    ("difficulty", "Difficulty"),
    ("estimated_minutes", "Estimated minutes"),
    ("instruction", "Instruction"),
    ("answer", "Answer"),
    ("grading_method", "Grading method"),
    ("data_files", "Data files"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True, help="Label Studio project id")
    ap.add_argument("-o", "--out", default="submissions.xlsx")
    args = ap.parse_args()

    tasks = get(f"/api/projects/{args.project}/export", exportType="JSON").json()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "submissions"
    ws.append([header for _, header in COLUMNS])
    exported = skipped = 0
    for task in tasks:
        annotations = [a for a in task.get("annotations", []) if not a.get("was_cancelled")]
        if not annotations:
            skipped += 1
            continue
        latest = max(annotations, key=lambda a: a.get("updated_at") or "")
        fields = annotation_fields(latest)
        ws.append([fields.get(key) for key, _ in COLUMNS])
        exported += 1

    wb.save(args.out)
    print(f"exported {exported} submissions to {args.out} ({skipped} tasks without annotations skipped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
