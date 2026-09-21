#!/usr/bin/env python3
"""kumi activity log hook (PostToolUse).
Appends one line per tool action to the activity log. Only writes when .kumi already exists."""

import datetime
import json
import os
import sys

import kumi_state


def read_payload():
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def target_of(tool_input):
    """Pick a short, human-readable target from a tool's input."""
    if not isinstance(tool_input, dict):
        return ""
    # Different tools name their target differently; take the first field that has one.
    for key in ("file_path", "path", "command", "url", "pattern", "query"):
        val = tool_input.get(key)
        if isinstance(val, str) and val:
            return val.replace("\n", " ")[:80]
    return ""


def main():
    # Whatever throws, this hook must still exit 0 rather than crash the tool call.
    try:
        payload = read_payload()
        cfg = kumi_state.load()
        project = kumi_state.project_dir(payload)
        kumi = kumi_state.state_dir(project, cfg)
        if not os.path.isdir(kumi):
            return 0

        logs_dir = os.path.join(kumi, cfg["dirs"]["logs"])
        try:
            os.makedirs(logs_dir, exist_ok=True)
        except OSError:
            return 0

        # One tab-separated line per action: time, short session id, tool, target.
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session = (payload.get("session_id") or "-")[:8]
        tool = payload.get("tool_name") or "-"
        target = target_of(payload.get("tool_input"))
        line = f"{stamp}\t{session}\t{tool}\t{target}\n"

        try:
            with open(os.path.join(logs_dir, cfg["logs"]["activity"]), "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            return 0

        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
