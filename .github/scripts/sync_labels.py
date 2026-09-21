#!/usr/bin/env python3
"""kumi label sync (push to main on .github/labels.json, or workflow_dispatch).
Makes the repo's real label set match .github/labels.json exactly: creates, updates, and deletes."""

import json
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _github import github_request  # noqa: E402

LABELS_PATH = os.path.join(os.path.dirname(HERE), "labels.json")
PAGE_SIZE = 100


def list_existing_labels(repo):
    """Return {name: {color, description}} for every label in repo, paginating to the last page."""
    existing = {}
    page = 1
    while True:
        status, response = github_request(
            "GET", f"/repos/{repo}/labels?per_page={PAGE_SIZE}&page={page}"
        )
        if status != 200 or not isinstance(response, list):
            raise RuntimeError(f"failed to list labels: status={status} body={response}")
        for label in response:
            existing[label["name"]] = {
                "color": label["color"],
                "description": label.get("description") or "",
            }
        if len(response) < PAGE_SIZE:
            break
        page += 1
    return existing


def load_desired():
    with open(LABELS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {
        label["name"]: {"color": label["color"], "description": label.get("description") or ""}
        for label in data["labels"]
    }


def main():
    try:
        repo = os.environ["GITHUB_REPOSITORY"]
        existing = list_existing_labels(repo)
        desired = load_desired()
    except Exception as e:
        print(f"sync-labels: FAIL, could not load label sets: {e}")
        return 1

    failures = 0

    for name, spec in desired.items():
        if name not in existing:
            status, _ = github_request(
                "POST",
                f"/repos/{repo}/labels",
                {"name": name, "color": spec["color"], "description": spec["description"]},
            )
            if status != 201:
                print(f"FAIL create {name}: status={status}")
                failures += 1
            else:
                print(f"created {name}")
        elif existing[name] != spec:
            quoted = urllib.parse.quote(name, safe="")
            status, _ = github_request(
                "PATCH",
                f"/repos/{repo}/labels/{quoted}",
                {"new_name": name, "color": spec["color"], "description": spec["description"]},
            )
            if status != 200:
                print(f"FAIL update {name}: status={status}")
                failures += 1
            else:
                print(f"updated {name}")

    for name in existing:
        if name not in desired:
            quoted = urllib.parse.quote(name, safe="")
            status, _ = github_request("DELETE", f"/repos/{repo}/labels/{quoted}")
            if status not in (204, 404):
                print(f"FAIL delete {name}: status={status}")
                failures += 1
            else:
                print(f"deleted {name}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
