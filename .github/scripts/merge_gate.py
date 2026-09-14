#!/usr/bin/env python3
"""kumi merge gate (pull_request: opened, synchronize, reopened, labeled, unlabeled).

The solo-maintainer alternative to a native required review (see
.kumi/decisions/kai/repo-automation.md §0.5): this is the actual
merge-blocking signal, computed from the PR's own label list, which the
/lgtm, /approve, /hold, and /unhold chat commands (chat_commands.py) set.

PASS (exit 0) iff both "lgtm" and "approved" are present and no label starts
with "do-not-merge/". Reads only github.event.pull_request.labels from the
event payload already delivered with a plain `pull_request` webhook — no API
call, no elevated token, no checkout of untrusted fork content required.

Fails closed: any exception while reading or parsing the event payload exits
1 with a clear message, never a silent 0 that would pass a PR this script
actually failed to evaluate. This is the opposite failure mode from
chat_commands.py/auto_assign.py, which swallow errors on purpose because a
bug there must never block someone's PR; a bug here must never merge one.

Standard library only.
"""

import json
import os
import sys


def main():
    try:
        with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
            event = json.load(f)
        labels = {label["name"] for label in event["pull_request"]["labels"]}
    except Exception as e:
        print(f"merge-gate: FAIL, could not read the event payload: {e}")
        return 1

    missing = [name for name in ("lgtm", "approved") if name not in labels]
    holds = sorted(name for name in labels if name.startswith("do-not-merge/"))

    if not missing and not holds:
        print("merge-gate: PASS")
        return 0

    if missing:
        print(f"missing: {', '.join(missing)}")
    for hold in holds:
        print(f"blocked by: {hold}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
