#!/usr/bin/env python3
"""kumi chat-ops (issue_comment: created, restricted to PR comments).
Handles /lgtm, /approve, /hold, /unhold, /ok-to-test; only /ok-to-test excludes the PR's author."""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _github import (  # noqa: E402
    add_labels,
    get_pull_request,
    is_authorized,
    post_comment,
    remove_label,
    report_if_error,
    set_commit_status,
)
from merge_gate import decide_state  # noqa: E402


def load_event():
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        return json.load(f)


def parse_command(body):
    """Return the recognized command if the first non-blank line is exactly one, else None."""
    if not isinstance(body, str):
        return None
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        return stripped if stripped in COMMANDS else None
    return None


def refresh_merge_gate_status(repo, pr_number):
    """Recompute and post the merge-gate status against the PR's current head, fetched live."""
    status, pr = get_pull_request(repo, pr_number)
    if not (200 <= status < 300) or not isinstance(pr, dict):
        report_if_error("get_pull_request(refresh_merge_gate_status)", status, pr)
        return
    labels = {label["name"] for label in pr["labels"]}
    sha = pr["head"]["sha"]
    state, description = decide_state(labels)
    status, body = set_commit_status(repo, sha, state, description)
    report_if_error("set_commit_status(refresh_merge_gate_status)", status, body)


def handle_lgtm(repo, pr_number, actor):
    if not is_authorized(repo, actor):
        status, body = post_comment(repo, pr_number, "`/lgtm` can only be run by a maintainer.")
        report_if_error("post_comment(/lgtm rejection)", status, body)
        return
    status, body = add_labels(repo, pr_number, ["lgtm"])
    report_if_error("add_labels(lgtm)", status, body)
    if 200 <= status < 300:
        refresh_merge_gate_status(repo, pr_number)


def handle_approve(repo, pr_number, actor):
    if not is_authorized(repo, actor):
        status, body = post_comment(repo, pr_number, "`/approve` can only be run by a maintainer.")
        report_if_error("post_comment(/approve rejection)", status, body)
        return
    status, body = add_labels(repo, pr_number, ["approved"])
    report_if_error("add_labels(approved)", status, body)
    if 200 <= status < 300:
        refresh_merge_gate_status(repo, pr_number)


def handle_hold(repo, pr_number, actor, author):
    if not (is_authorized(repo, actor) or actor == author):
        status, body = post_comment(
            repo, pr_number, "`/hold` can only be run by a maintainer or the PR's own author."
        )
        report_if_error("post_comment(/hold rejection)", status, body)
        return
    status, body = add_labels(repo, pr_number, ["do-not-merge/hold"])
    report_if_error("add_labels(do-not-merge/hold)", status, body)
    if 200 <= status < 300:
        refresh_merge_gate_status(repo, pr_number)


def handle_unhold(repo, pr_number, actor, author):
    if not (is_authorized(repo, actor) or actor == author):
        status, body = post_comment(
            repo, pr_number, "`/unhold` can only be run by a maintainer or the PR's own author."
        )
        report_if_error("post_comment(/unhold rejection)", status, body)
        return
    status, body = remove_label(repo, pr_number, "do-not-merge/hold")
    report_if_error("remove_label(do-not-merge/hold)", status, body, ignore=(404,))
    if 200 <= status < 300 or status == 404:
        refresh_merge_gate_status(repo, pr_number)


def handle_ok_to_test(repo, pr_number, actor, author):
    # No "or actor == author" fallback: the PR's own author must never authorize its own CI run.
    if not is_authorized(repo, actor):
        status, body = post_comment(
            repo, pr_number, "`/ok-to-test` can only be run by a maintainer."
        )
        report_if_error("post_comment(/ok-to-test rejection)", status, body)
        return
    status, body = remove_label(repo, pr_number, "needs-ok-to-test")
    report_if_error("remove_label(needs-ok-to-test)", status, body, ignore=(404,))
    status, body = add_labels(repo, pr_number, ["ok-to-test"])
    report_if_error("add_labels(ok-to-test)", status, body)


COMMANDS = {
    "/lgtm": handle_lgtm,
    "/approve": handle_approve,
    "/hold": handle_hold,
    "/unhold": handle_unhold,
    "/ok-to-test": handle_ok_to_test,
}


def main():
    try:
        event = load_event()
        command = parse_command(event["comment"]["body"])
        if command is None:
            return 0

        repo = os.environ["GITHUB_REPOSITORY"]
        pr_number = event["issue"]["number"]
        actor = event["comment"]["user"]["login"]
        author = event["issue"]["user"]["login"]

        handler = COMMANDS[command]
        if command in ("/hold", "/unhold", "/ok-to-test"):
            handler(repo, pr_number, actor, author)
        else:
            handler(repo, pr_number, actor)
        return 0
    except Exception as e:
        print(f"chat-ops: skipping, {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
