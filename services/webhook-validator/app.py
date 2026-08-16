"""Instant field-level validation for benchmark submissions.

Register this service as a webhook in the Label Studio project settings
(Webhooks -> ANNOTATION_CREATED / ANNOTATION_UPDATED, URL http://<host>:8090/webhook).
On every save it re-checks the submission against the intake field rules
and logs an issue list per annotation, so obviously broken submissions are
caught the moment they are made instead of at export time.

This is the fast, shallow gate. Deep verification (data files, packing,
oracle runs) is the concern of whatever consumes the exported xlsx.

Run:  uvicorn app:app --host 0.0.0.0 --port 8090
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("webhook-validator")

app = FastAPI(title="labelforge webhook validator")

REQUIRED = ("title", "domain", "difficulty", "estimated_minutes", "instruction", "answer", "grading_method")
GRADING_METHODS = {"deterministic", "llm-judge"}


def flatten(result: list[dict]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for item in result:
        value = item.get("value", {})
        if "text" in value:
            fields[item["from_name"]] = "\n".join(value["text"])
        elif "choices" in value:
            fields[item["from_name"]] = value["choices"][0] if value["choices"] else None
        elif "number" in value:
            fields[item["from_name"]] = value["number"]
    return fields


def validate(fields: dict[str, object]) -> list[str]:
    issues = []
    for key in REQUIRED:
        value = fields.get(key)
        if value is None or not str(value).strip():
            issues.append(f"required field '{key}' is empty")
    minutes = fields.get("estimated_minutes")
    if minutes is not None:
        try:
            if float(minutes) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            issues.append(f"estimated_minutes must be a positive number, got {minutes!r}")
    grading = fields.get("grading_method")
    if grading is not None and grading not in GRADING_METHODS:
        issues.append(f"grading_method must be one of {sorted(GRADING_METHODS)}, got {grading!r}")
    return issues


@app.post("/webhook")
async def webhook(request: Request) -> dict[str, object]:
    payload = await request.json()
    action = payload.get("action")
    if action not in {"ANNOTATION_CREATED", "ANNOTATION_UPDATED"}:
        return {"ok": True, "skipped": action}

    annotation = payload.get("annotation", {})
    task_id = payload.get("task", {}).get("id")
    issues = validate(flatten(annotation.get("result", [])))
    if issues:
        log.warning("task %s annotation %s: %d issue(s): %s", task_id, annotation.get("id"), len(issues), "; ".join(issues))
    else:
        log.info("task %s annotation %s: clean", task_id, annotation.get("id"))
    return {"ok": True, "task": task_id, "issues": issues}


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}
