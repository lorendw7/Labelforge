"""Register the webhook validator on a Label Studio project.

Idempotent: skips registration if the URL is already hooked to the project.
The URL must be reachable *from the Label Studio container* — with the
compose deployment that is http://validator.internal:8090/webhook (the default;
a dotted alias because Label Studio rejects bare hostnames as invalid URLs).

Example:
  python register_webhook.py --project 3
  python register_webhook.py --project 3 --url http://lab-server:8090/webhook
"""

from __future__ import annotations

import argparse

from ls_api import get, post

ACTIONS = ["ANNOTATION_CREATED", "ANNOTATION_UPDATED"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True, help="Label Studio project id")
    ap.add_argument("--url", default="http://validator.internal:8090/webhook")
    args = ap.parse_args()

    existing = get("/api/webhooks", project=args.project).json()
    if any(w.get("url") == args.url for w in existing):
        print(f"webhook {args.url} already registered on project {args.project}")
        return 0

    webhook = post(
        "/api/webhooks",
        {
            "project": int(args.project),
            "url": args.url,
            "send_payload": True,
            "send_for_all_actions": False,
            "actions": ACTIONS,
            "is_active": True,
        },
    ).json()
    print(f"registered webhook {webhook['id']}: {args.url} ({', '.join(ACTIONS)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
