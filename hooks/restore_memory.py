#!/usr/bin/env python3
"""kumi memory restore hook (SessionStart).

Runs at the start of a session and surfaces the project's recent kumi memory
(the last few captured entries and the current handoff) as additional context,
so a new session resumes where the previous one left off instead of starting
cold. This is the read side of the memory loop; capture_memory.py is the write
side.

It emits at most a bounded amount of text so it never floods the session, reads
file names from config/runtime.json (via kumi_state), always exits 0, and never
raises. Standard library only.

Exit code: always 0.

Complexity: reads the tail of the memory log and the handoff once each; entry
splitting is linear in the text read, which is itself capped.
"""

import json
import os
import sys

import kumi_state

# Cap on how much memory we inject, so a long history never floods a new session.
MAX_CONTEXT_CHARS = 4000


def read_payload():
    # Hook input is JSON on stdin; tolerate empty or malformed input.
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def emit(context):
    """Print the SessionStart additionalContext payload and exit cleanly."""
    if context:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": context,
                    }
                }
            )
        )


def main():
    # Single outer boundary: whatever throws, however unexpected, this hook
    # must still exit 0 rather than crash the session it's watching.
    try:
        payload = read_payload()
        cfg = kumi_state.load()
        project = kumi_state.project_dir(payload)
        kumi = kumi_state.state_dir(project, cfg)
        if not os.path.isdir(kumi):
            return 0  # kumi not in use here

        pieces = []

        # Recent memory entries (tail of the append-only log).
        log_path = os.path.join(kumi, cfg["dirs"]["memory"], cfg["memory"]["log"])
        if os.path.isfile(log_path):
            try:
                with open(log_path, encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                text = ""
            # Entries in the log start with a "## <timestamp>" heading. Split
            # on it, take the last few, and drop the file's own "# kumi
            # memory" header.
            entries = text.split("\n## ")
            n = int(cfg["memory"].get("restore_entries", 3))
            recent = entries[-n:] if len(entries) > 1 else []
            recent = [e for e in recent if e.strip() and not e.startswith("# kumi memory")]
            if recent:
                pieces.append(
                    "Recent kumi memory from prior sessions (most recent last):\n\n## "
                    + "\n## ".join(recent)
                )

        # Current handoff, if a task was mid-flight.
        handoff_path = os.path.join(kumi, cfg["files"]["handoff"])
        if os.path.isfile(handoff_path):
            try:
                with open(handoff_path, encoding="utf-8") as f:
                    handoff = f.read().strip()
            except OSError:
                handoff = ""
            if handoff:
                pieces.append("Current handoff (work in progress):\n\n" + handoff)

        if not pieces:
            return 0

        context = "\n\n---\n\n".join(pieces)
        if len(context) > MAX_CONTEXT_CHARS:
            context = context[:MAX_CONTEXT_CHARS] + "\n\n[truncated]"
        emit(context)
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
