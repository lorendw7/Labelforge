"""Create a Label Studio project from a labeling config.

Example:
  python create_project.py --title "Benchmark task intake" \
      --config ../configs/benchmark-task.xml --stub-tasks 50
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ls_api import post

STUB = "Submit one benchmark task using the fields below."


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--title", required=True)
    ap.add_argument("--config", required=True, help="labeling config XML file")
    ap.add_argument(
        "--stub-tasks",
        type=int,
        default=0,
        help="import N stub tasks (for form-style projects where each submission fills one task)",
    )
    args = ap.parse_args()

    label_config = Path(args.config).read_text(encoding="utf-8")
    project = post("/api/projects", {"title": args.title, "label_config": label_config}).json()
    print(f"created project {project['id']}: {project['title']}")

    if args.stub_tasks:
        tasks = [{"data": {"brief": STUB}} for _ in range(args.stub_tasks)]
        post(f"/api/projects/{project['id']}/import", tasks)
        print(f"imported {args.stub_tasks} stub tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
