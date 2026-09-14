#!/usr/bin/env python3
"""kumi size labels (pull_request_target: opened, synchronize, reopened).

Buckets a PR by lines changed (additions + deletions), read directly from
the webhook's own pull_request object — no diff to fetch, no checkout of PR
content needed for the calculation. Thresholds are the standard
Kubernetes/Prow `size` plugin defaults, reused as-is.

Removes every size/* label the PR currently carries, then adds the one
computed bucket, so a `synchronize` push that shrinks or grows a PR across a
boundary doesn't leave stale labels behind.

Standard library only.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _github import add_labels, remove_label, report_if_error  # noqa: E402

THRESHOLDS = (
    (10, "size/XS"),
    (30, "size/S"),
    (100, "size/M"),
    (500, "size/L"),
    (1000, "size/XL"),
)


def bucket_for(lines_changed):
    for limit, label in THRESHOLDS:
        if lines_changed < limit:
            return label
    return "size/XXL"


def load_event():
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        return json.load(f)


def main():
    try:
        event = load_event()
        pr = event["pull_request"]
        repo = os.environ["GITHUB_REPOSITORY"]
        number = pr["number"]

        lines_changed = pr["additions"] + pr["deletions"]
        label = bucket_for(lines_changed)

        existing_size_labels = [
            lbl["name"] for lbl in pr.get("labels", []) if lbl["name"].startswith("size/")
        ]
        for existing in existing_size_labels:
            if existing != label:
                status, _ = remove_label(repo, number, existing)
                report_if_error(f"remove_label({existing})", status, ignore=(404,))
        if label not in existing_size_labels:
            status, _ = add_labels(repo, number, [label])
            report_if_error(f"add_labels({label})", status)
        return 0
    except Exception as e:
        print(f"size-label: skipping, {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
