#!/usr/bin/env python3
"""kumi merge gate (pull_request_target: opened, synchronize, reopened, labeled, unlabeled).

The solo-maintainer alternative to a native required review (see
.kumi/decisions/kai/repo-automation.md §0.5): this is the actual
merge-blocking signal, computed from the PR's own label list, which the
/lgtm, /approve, /hold, and /unhold chat commands (chat_commands.py) set.

Reports the result as a `merge-gate` commit status (POST
/repos/{repo}/statuses/{head_sha}) rather than the job's own exit code, the
same way Prow's tide reports a pool's merge-readiness as a status instead of
failing a check while a PR is simply waiting its turn: "lgtm" and "approved"
both present and nothing held is `success`; anything else — missing labels,
a `do-not-merge/*` hold, or both — is `pending`, never `failure`. Branch
protection requires the `merge-gate` *status* context, not this job's own
check run (named `merge-gate-status` on purpose, so the two can't be
confused).

Reads only github.event.pull_request.labels and .head.sha from the event
payload already delivered with the workflow's own trigger — no extra API
call, no elevated token, no checkout of untrusted fork content required.

Fails closed: any exception while reading or parsing the event payload exits
1 with a clear message and posts no commit status at all, never a silent
"success" for a PR this script actually failed to evaluate. A failure to
post the status itself (a bad token, a wrong `permissions:` block) also
exits 1, for the same reason: a PR that never gets any `merge-gate` status
stays "pending" in branch protection forever, which is the fail-closed
outcome we want. This is the opposite failure mode from
chat_commands.py/auto_assign.py, which swallow errors on purpose because a
bug there must never block someone's PR; a bug here must never merge one.

Standard library only.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _github import report_if_error, set_commit_status  # noqa: E402

MAX_DESCRIPTION_LENGTH = 140  # GitHub's own limit on a commit status description


def decide_state(labels):
    """Return (state, description) for the merge-gate commit status.

    state is "pending" or "success" — this function never returns "failure":
    a PR that is missing a label or held by a do-not-merge/* label is not
    broken, it is simply not ready yet, so it is reported as pending.

    A hold takes priority over missing labels in the description (a PR can
    be both unapproved and held; "blocked" is the more actionable thing to
    say first). description is truncated defensively to stay within
    GitHub's 140-character limit even if an unusual number of do-not-merge/*
    labels were ever applied at once.
    """
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

    print(f"merge-gate: {state} — {description}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
