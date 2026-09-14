#!/usr/bin/env python3
"""kumi needs-ok-to-test label (pull_request_target: opened).

The visible half of §14's two-layer hold on outside contributors' CI: the
real gate is the native repo setting (Settings -> Actions -> General ->
Fork pull request workflows -> "Require approval for all outside
collaborators"), applied by Anna, not by this script. This script only adds
the needs-ok-to-test label when the PR's author does not already have write
access, so the PR list shows which PRs are waiting. A maintainer's /ok-to-test
comment (chat_commands.py) removes it.

Standard library only.
"""

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
