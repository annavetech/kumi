#!/usr/bin/env python3
"""kumi merge gate (pull_request_target: opened, synchronize, reopened, labeled, unlabeled).
Computes the `merge-gate` status from the PR's own labels. Fails closed: errors post no status."""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _github import report_if_error, set_commit_status  # noqa: E402

MAX_DESCRIPTION_LENGTH = 140  # GitHub's own limit on a commit status description


def decide_state(labels):
    """Return (state, description); state is "pending" or "success", never "failure"."""
    holds = sorted(name for name in labels if name.startswith("do-not-merge/"))
    if holds:
        description = f"Blocked by {', '.join(holds)}"
    else:
        missing = sorted(name for name in ("lgtm", "approved") if name not in labels)
        if missing:
            plural = "s" if len(missing) > 1 else ""
            description = f"Needs {', '.join(missing)} label{plural}"
        else:
            return "success", "lgtm and approved; not held"

    if len(description) > MAX_DESCRIPTION_LENGTH:
        description = description[: MAX_DESCRIPTION_LENGTH - 3] + "..."
    return "pending", description


def main():
    if "GITHUB_TOKEN" not in os.environ:
        print("merge-gate: FAIL, GITHUB_TOKEN is not set")
        return 1

    try:
        with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
            event = json.load(f)
        pull_request = event["pull_request"]
        labels = {label["name"] for label in pull_request["labels"]}
        sha = pull_request["head"]["sha"]
        repo = os.environ["GITHUB_REPOSITORY"]
    except Exception as e:
        print(f"merge-gate: FAIL, could not read the event payload: {e}")
        return 1

    state, description = decide_state(labels)

    status, body = set_commit_status(repo, sha, state, description)
    if not (200 <= status < 300):
        report_if_error("set_commit_status(merge-gate)", status, body)
        print(f"merge-gate: FAIL, could not post the commit status (status {status})")
        return 1

    print(f"merge-gate: {state}: {description}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
