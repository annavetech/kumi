#!/usr/bin/env python3
"""kumi memory capture hook (Stop, SubagentStop).

Runs when an agent finishes and appends a snapshot of the project's kumi state
to an append-only memory log, so a finished task's context survives into later
sessions. Capture is driven by the runtime, not by any specialist remembering to
save, so it is guaranteed rather than best-effort. Its counterpart is
restore_memory.py, which reads this log back at the start of a new session.

File names come from config/runtime.json (via kumi_state), so nothing here is
hardcoded. The hook always exits 0 and never raises: a memory hook must never
block or fail the agent it serves. Standard library only.

Exit code: always 0.

Complexity: reads the handoff once and walks the decisions tree once (linear in
the number of state files); a content hash guards against re-logging unchanged
state, so repeated stops do no extra work.
"""

import datetime
import hashlib
import json
import os
import sys

import kumi_state


def read_payload():
    # The hook payload arrives as JSON on stdin. Empty or malformed input is
    # tolerated: this hook must never be the reason an agent fails.
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def main():
    payload = read_payload()
    if payload.get("stop_hook_active"):
        return 0  # don't re-enter from a stop a stop hook itself triggered

    cfg = kumi_state.load()
    project = payload.get("cwd") or os.getcwd()
    kumi = kumi_state.state_dir(project, cfg)
    if not os.path.isdir(kumi):
        return 0  # kumi not in use in this project

    handoff_path = os.path.join(kumi, cfg["files"]["handoff"])
    handoff = ""
    if os.path.isfile(handoff_path):
        try:
            with open(handoff_path, encoding="utf-8") as f:
                handoff = f.read()
        except OSError:
            handoff = ""

    # Collect every decision file the roles wrote. Store paths relative to the
    # state dir so the log reads the same no matter where the project lives.
    decisions = []
    decisions_dir = os.path.join(kumi, cfg["dirs"]["decisions"])
    if os.path.isdir(decisions_dir):
        for root, _dirs, files in os.walk(decisions_dir):
            for name in files:
                if name.endswith(".md"):
                    decisions.append(
                        os.path.relpath(os.path.join(root, name), kumi)
                    )
    decisions.sort()

    if not handoff.strip() and not decisions:
        return 0  # nothing worth remembering yet

    memory_dir = os.path.join(kumi, cfg["dirs"]["memory"])
    try:
        os.makedirs(memory_dir, exist_ok=True)
    except OSError:
        return 0

    # Fingerprint the current state. If it matches the last capture, the project
    # hasn't changed since the previous stop, so there is nothing new to log.
    signature = hashlib.sha256(
        "\n".join([handoff] + decisions).encode("utf-8")
    ).hexdigest()
    sig_path = os.path.join(memory_dir, cfg["memory"]["signature"])
    try:
        if os.path.isfile(sig_path):
            with open(sig_path, encoding="utf-8") as f:
                if f.read().strip() == signature:
                    return 0  # state unchanged since last capture
    except OSError:
        pass

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [f"\n## {stamp}\n"]
    if decisions:
        parts.append("\nDecisions on record:\n")
        parts.extend(f"- {rel}\n" for rel in decisions)
    if handoff.strip():
        parts.append("\nHandoff at completion:\n\n```\n")
        parts.append(handoff.rstrip() + "\n```\n")

    log_path = os.path.join(memory_dir, cfg["memory"]["log"])
    try:
        first = not os.path.isfile(log_path)
        with open(log_path, "a", encoding="utf-8") as f:
            if first:
                f.write(
                    "# kumi memory\n\n"
                    "Append-only record of finished work, captured automatically "
                    "when an agent stops. Nothing here is overwritten.\n"
                )
            f.write("".join(parts))
        with open(sig_path, "w", encoding="utf-8") as f:
            f.write(signature)
    except OSError:
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
