#!/usr/bin/env python3
"""kumi activity log hook (PostToolUse).
Appends one line per tool action: time, session, tool, and a path for file tools only."""

import datetime
import json
import os
import sys

import kumi_state

# File tools and the input field that holds their path; every other tool logs "-".
FILE_TOOLS = {
    "Read": "file_path",
    "Write": "file_path",
    "Edit": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
    "Grep": "path",
    "Glob": "path",
    "LS": "path",
}


def read_payload():
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def target_of(tool_name, tool_input):
    """Return the cleaned path for a file tool, else "-". Never commands, URLs, or queries."""
    key = FILE_TOOLS.get(tool_name) if isinstance(tool_name, str) else None
    if key is None or not isinstance(tool_input, dict):
        return "-"
    val = tool_input.get(key)
    if isinstance(val, str) and val:
        return kumi_state.clean_field(val, 1024)
    return "-"


def main():
    # Whatever throws, this hook must still exit 0 rather than crash the tool call.
    try:
        payload = read_payload()
        if not isinstance(payload, dict):
            return 0
        cfg = kumi_state.load()
        anchor = kumi_state.resolve_anchor(kumi_state.project_dir(payload), cfg)
        root = kumi_state.open_state_root(anchor, cfg)
        if root is None:
            return 0
        with root:
            if not kumi_state.is_enabled(root.path, anchor):
                return 0  # kumi was never called in this project

            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            session = payload.get("session_id")
            session = kumi_state.clean_field(session, 8) if isinstance(session, str) else ""
            tool = payload.get("tool_name")
            tool_text = kumi_state.clean_field(tool, 128) if isinstance(tool, str) else ""
            target = target_of(tool, payload.get("tool_input"))
            line = f"{stamp}\t{session or '-'}\t{tool_text or '-'}\t{target}\n"

            fd = kumi_state.open_in_state(
                root.handle,
                [cfg["dirs"]["logs"], cfg["logs"]["activity"]],
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                create_dirs=True,
            )
            if fd is None:
                return 0
            try:
                os.write(fd, line.encode("utf-8", errors="backslashreplace"))
            finally:
                os.close(fd)
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
