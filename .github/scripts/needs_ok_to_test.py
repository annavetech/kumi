#!/usr/bin/env python3
"""kumi needs-ok-to-test label (pull_request_target: opened).
Adds the label when a PR's author lacks write access; a maintainer's /ok-to-test removes it."""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _github import add_labels, is_authorized, report_if_error  # noqa: E402


def load_event():
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        return json.load(f)


def main():
    try:
        event = load_event()
        repo = os.environ["GITHUB_REPOSITORY"]
        number = event["pull_request"]["number"]
        author = event["pull_request"]["user"]["login"]

        if not is_authorized(repo, author):
            status, _ = add_labels(repo, number, ["needs-ok-to-test"])
            report_if_error("add_labels(needs-ok-to-test)", status)
        return 0
    except Exception as e:
        print(f"needs-ok-to-test: skipping, {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
