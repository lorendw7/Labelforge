"""Thin helpers over the Label Studio REST API.

Uses plain REST (stable across releases) instead of the SDK to avoid
version churn. Credentials come from the environment:
  LABEL_STUDIO_URL      e.g. http://localhost:8080
  LABEL_STUDIO_API_KEY  personal access token from Account & Settings
"""

from __future__ import annotations

import os

import requests


def base_url() -> str:
    return os.environ["LABEL_STUDIO_URL"].rstrip("/")


def headers() -> dict[str, str]:
    return {"Authorization": f"Token {os.environ['LABEL_STUDIO_API_KEY']}"}


def _check(r: requests.Response) -> requests.Response:
    """raise_for_status, but include the response body — Label Studio puts
    the actual field-level error details there."""
    if not r.ok:
        raise requests.HTTPError(
            f"{r.status_code} {r.reason} for {r.url}: {r.text[:2000]}", response=r
        )
    return r


def get(path: str, **params) -> requests.Response:
    return _check(requests.get(f"{base_url()}{path}", headers=headers(), params=params, timeout=60))


def post(path: str, payload: object) -> requests.Response:
    return _check(requests.post(f"{base_url()}{path}", headers=headers(), json=payload, timeout=60))


def annotation_fields(annotation: dict) -> dict[str, object]:
    """Flatten a Label Studio annotation result into {field_name: value}.

    TextArea -> str, Choices -> str (single choice), Number -> float.
    """
    fields: dict[str, object] = {}
    for item in annotation.get("result", []):
        name = item.get("from_name")
        value = item.get("value", {})
        if "text" in value:
            fields[name] = "\n".join(value["text"])
        elif "choices" in value:
            fields[name] = value["choices"][0] if value["choices"] else None
        elif "number" in value:
            fields[name] = value["number"]
    return fields
