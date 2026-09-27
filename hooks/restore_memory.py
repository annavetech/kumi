#!/usr/bin/env python3
"""kumi memory restore hook (SessionStart).
Surfaces the project's recent kumi memory and current handoff as additional context."""

import json
import os
import re
import sys

import kumi_state

# Cap on the combined context we inject, so a long history never floods a new session.
MAX_CONTEXT_CHARS = 4000

# The handoff is the higher-priority piece and is shown in full even past the combined
# cap above; this is the ceiling only for a truly runaway handoff file.
MAX_HANDOFF_CHARS = 20000

HANDOFF_POINTER = (
    "\n\n[handoff continues; read .kumi/handoff.md directly, it is longer than shown here]"
)

# Real entries always start with "## YYYY-MM-DD HH:MM:SS" (written by capture_memory.py).
# A body heading such as "## Scope" inside a pasted-in handoff never matches this exact shape.
ENTRY_RE = re.compile(r"\n## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\n")

DEFAULT_RESTORE_ENTRIES = 3


def resolve_restore_entries(cfg):
    """Return a valid entry count: 0 means none, bad or negative falls back to the default."""
    raw = cfg["memory"].get("restore_entries", DEFAULT_RESTORE_ENTRIES)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_RESTORE_ENTRIES
    return DEFAULT_RESTORE_ENTRIES if n < 0 else n


def parse_entries(text):
    """Split log text into (stamp, body) pairs, one per real timestamped entry, file order."""
    matches = list(ENTRY_RE.finditer(text))
    entries = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        entries.append((m.group(1), text[start:end]))
    return entries


def read_payload():
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
    # Whatever throws, this hook must still exit 0 rather than crash the session.
    try:
        payload = read_payload()
        cfg = kumi_state.load()
        project = kumi_state.project_dir(payload)
        kumi = kumi_state.state_dir(project, cfg)
        if not os.path.isdir(kumi):
            return 0  # kumi not in use here

        # Recent memory entries (tail of the append-only log).
        entries = []
        log_path = os.path.join(kumi, cfg["dirs"]["memory"], cfg["memory"]["log"])
        if os.path.isfile(log_path):
            try:
                with open(log_path, encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                text = ""
            n = resolve_restore_entries(cfg)
            entries = parse_entries(text)[-n:] if n > 0 else []

        # Current handoff, if a task was mid-flight.
        handoff = ""
        handoff_path = os.path.join(kumi, cfg["files"]["handoff"])
        if os.path.isfile(handoff_path):
            try:
                with open(handoff_path, encoding="utf-8") as f:
                    handoff = f.read().strip()
            except OSError:
                handoff = ""

        handoff_piece = ""
        if handoff:
            if len(handoff) > MAX_HANDOFF_CHARS:
                handoff = handoff[:MAX_HANDOFF_CHARS] + HANDOFF_POINTER
            handoff_piece = "Current handoff (work in progress):\n\n" + handoff

        # The handoff never gets cut for the memory budget; memory fills what's left,
        # whole entries only, most recent first, so an entry is never emitted mid-body.
        separator = "\n\n---\n\n"
        memory_header = "Recent kumi memory from prior sessions (most recent last):\n\n"
        budget = MAX_CONTEXT_CHARS - len(handoff_piece)
        if handoff_piece and entries:
            budget -= len(separator)
        if entries:
            budget -= len(memory_header)

        kept = []
        for stamp, body in reversed(entries):
            entry_text = f"## {stamp}\n{body}"
            piece_len = len(entry_text) + (1 if kept else 0)  # +1 for the join newline
            if piece_len > budget:
                break
            kept.insert(0, entry_text)
            budget -= piece_len

        memory_piece = ""
        if kept:
            memory_piece = memory_header + "\n".join(kept)

        pieces = [p for p in (memory_piece, handoff_piece) if p]
        if not pieces:
            return 0

        emit(separator.join(pieces))
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
