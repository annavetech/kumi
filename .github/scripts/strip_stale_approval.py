#!/usr/bin/env python3
"""kumi strip-stale-approval (merge-gate.yml, pull_request_target: synchronize only).
Removes the lgtm/approved labels from a PR with a new commit, and posts the corrected status."""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _github import remove_label, report_if_error, set_commit_status  # noqa: E402
from merge_gate import decide_state  # noqa: E402


def strip_and_report(repo, pr_number, sha, labels):
    """Remove lgtm/approved from labels, leave hold untouched, post the result; True on success."""
    remaining = set(labels)
    for label in ("lgtm", "approved"):
        if label not in remaining:
            continue
        status, body = remove_label(repo, pr_number, label)
        if not (200 <= status < 300) and status != 404:
            report_if_error(f"remove_label({label})", status, body)
            print(f"strip-stale-approval: FAIL, could not remove {label}")
            return False
        remaining.discard(label)

    state, description = decide_state(remaining)
    status, body = set_commit_status(repo, sha, state, description)
    if not (200 <= status < 300):
        report_if_error("set_commit_status(strip-stale-approval)", status, body)
        print("strip-stale-approval: FAIL, could not post the commit status")
        return False

    print(f"strip-stale-approval: {state}, {description}")
    return True


def main():
    if "GITHUB_TOKEN" not in os.environ:
        print("strip-stale-approval: FAIL, GITHUB_TOKEN is not set")
        return 1

    try:
        with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
            event = json.load(f)
        pull_request = event["pull_request"]
        pr_number = pull_request["number"]
        sha = pull_request["head"]["sha"]
        labels = {label["name"] for label in pull_request["labels"]}
        repo = os.environ["GITHUB_REPOSITORY"]
    except Exception as e:
        print(f"strip-stale-approval: FAIL, could not read the event payload: {e}")
        return 1

    if not strip_and_report(repo, pr_number, sha, labels):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
