#!/usr/bin/env python3
"""kumi chat-ops (issue_comment: created, restricted to PR comments).

Recognizes one bare command per comment, on its first non-blank line:
/lgtm, /approve, /hold, /unhold, /ok-to-test. Everything else is left alone.

Authorization model (see .kumi/decisions/kai/repo-automation.md §0.5/§3):
a solo maintainer cannot review their own PR under GitHub's native rules, so
merge is gated on labels this script sets, not on a native review. /lgtm and
/approve are deliberately reachable by the PR's own author (that is the
entire point for a solo maintainer). /hold and /unhold are reachable by the
author too (holding your own WIP is normal and only blocks merge, it grants
nothing). /ok-to-test is the one command that must NEVER be reachable by the
PR's own author: it is what authorizes an untrusted PR's own CI run, so only
someone who already has write access to the repo may run it.

Never raises past main(): unexpected API errors are caught, logged to
stderr, and this exits 0 regardless — a bug here must never turn into a red,
blocking check on someone's PR (unlike the merge gate, which is supposed to
block).

Standard library only.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _github import (  # noqa: E402
    add_labels,
    add_reaction,
    is_authorized,
    post_comment,
    remove_label,
    report_if_error,
)


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


def handle_lgtm(repo, pr_number, actor, comment_id):
    if not is_authorized(repo, actor):
        status, _ = post_comment(repo, pr_number, "`/lgtm` can only be run by a maintainer.")
        report_if_error("post_comment(/lgtm rejection)", status)
        return
    status, _ = add_labels(repo, pr_number, ["lgtm"])
    report_if_error("add_labels(lgtm)", status)
    status, _ = add_reaction(repo, comment_id, "+1")
    report_if_error("add_reaction(+1)", status)


def handle_approve(repo, pr_number, actor, comment_id):
    if not is_authorized(repo, actor):
        status, _ = post_comment(repo, pr_number, "`/approve` can only be run by a maintainer.")
        report_if_error("post_comment(/approve rejection)", status)
        return
    status, _ = add_labels(repo, pr_number, ["approved"])
    report_if_error("add_labels(approved)", status)
    status, _ = add_reaction(repo, comment_id, "+1")
    report_if_error("add_reaction(+1)", status)


def handle_hold(repo, pr_number, actor, comment_id, author):
    if not (is_authorized(repo, actor) or actor == author):
        status, _ = post_comment(
            repo, pr_number, "`/hold` can only be run by a maintainer or the PR's own author."
        )
        report_if_error("post_comment(/hold rejection)", status)
        return
    status, _ = add_labels(repo, pr_number, ["do-not-merge/hold"])
    report_if_error("add_labels(do-not-merge/hold)", status)
    status, _ = add_reaction(repo, comment_id, "+1")
    report_if_error("add_reaction(+1)", status)


def handle_unhold(repo, pr_number, actor, comment_id, author):
    if not (is_authorized(repo, actor) or actor == author):
        status, _ = post_comment(
            repo, pr_number, "`/unhold` can only be run by a maintainer or the PR's own author."
        )
        report_if_error("post_comment(/unhold rejection)", status)
        return
    status, _ = remove_label(repo, pr_number, "do-not-merge/hold")
    report_if_error("remove_label(do-not-merge/hold)", status, ignore=(404,))
    status, _ = add_reaction(repo, comment_id, "+1")
    report_if_error("add_reaction(+1)", status)


def handle_ok_to_test(repo, pr_number, actor, comment_id, author):
    # Deliberately excludes the "or actor == author" fallback that /hold and
    # /unhold use above: an untrusted PR's own author must never be able to
    # authorize its own CI run. This is the whole safety property of §13/§14.
    if not is_authorized(repo, actor):
        status, _ = post_comment(repo, pr_number, "`/ok-to-test` can only be run by a maintainer.")
        report_if_error("post_comment(/ok-to-test rejection)", status)
        return
    status, _ = remove_label(repo, pr_number, "needs-ok-to-test")
    report_if_error("remove_label(needs-ok-to-test)", status, ignore=(404,))
    status, _ = add_labels(repo, pr_number, ["ok-to-test"])
    report_if_error("add_labels(ok-to-test)", status)
    status, _ = add_reaction(repo, comment_id, "+1")
    report_if_error("add_reaction(+1)", status)


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
        comment_id = event["comment"]["id"]
        author = event["issue"]["user"]["login"]

        handler = COMMANDS[command]
        if command in ("/hold", "/unhold", "/ok-to-test"):
            handler(repo, pr_number, actor, comment_id, author)
        else:
            handler(repo, pr_number, actor, comment_id)
        return 0
    except Exception as e:
        print(f"chat-ops: skipping, {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
