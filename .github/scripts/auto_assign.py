#!/usr/bin/env python3
"""kumi auto-assign (issues: opened, pull_request_target: opened).
Assigns an issue to the maintainer and a PR to its own author. Always exits 0."""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _github import add_assignees, report_if_error  # noqa: E402


def load_event():
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        return json.load(f)


def main():
    try:
        repo = os.environ["GITHUB_REPOSITORY"]
        event_name = os.environ["GITHUB_EVENT_NAME"]
        event = load_event()

        if event_name == "issues":
            number = event["issue"]["number"]
            maintainer = os.environ["MAINTAINER_LOGIN"]
            status, _ = add_assignees(repo, number, [maintainer])
            report_if_error(f"add_assignees({maintainer})", status)
        elif event_name == "pull_request_target":
            number = event["pull_request"]["number"]
            author = event["pull_request"]["user"]["login"]
            status, _ = add_assignees(repo, number, [author])
            report_if_error(f"add_assignees({author})", status)
        return 0
    except Exception as e:
        print(f"auto-assign: skipping, {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
