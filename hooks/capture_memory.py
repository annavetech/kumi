#!/usr/bin/env python3
"""kumi memory capture hook (Stop, SubagentStop).
Appends a snapshot of kumi state to an append-only log; restore_memory.py reads it back."""

import contextlib
import datetime
import hashlib
import json
import os
import random
import re
import sys
import time

import kumi_state

# Same strict shape restore_memory.py splits on; used here only to count entries.
ENTRY_RE = re.compile(r"\n## \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\n")

DEFAULT_ROTATE_ENTRIES = 250


def resolve_rotate_entries(cfg):
    """Return a valid rotation threshold; a bad or non-positive value falls back to the default."""
    raw = cfg["memory"].get("rotate_entries", DEFAULT_ROTATE_ENTRIES)
    try:
        threshold = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_ROTATE_ENTRIES
    return threshold if threshold > 0 else DEFAULT_ROTATE_ENTRIES


@contextlib.contextmanager
def _locked(memory_dir, timeout=2.0, stale_after=30.0):
    """Exclusive lock via atomic file creation (portable to POSIX and Windows), so two
    Stop/SubagentStop hooks racing never clobber or interleave each other's writes."""
    lock_path = os.path.join(memory_dir, ".lock")
    token = f"{os.getpid()}-{random.getrandbits(32)}"
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                f.write(token)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock_path) > stale_after:
                    os.remove(lock_path)  # abandoned by a crashed hook; safe to reclaim
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for lock: {lock_path}") from None
            time.sleep(0.02)
    try:
        yield
    finally:
        try:
            # Only remove the lock if it still holds this process's token: a slow holder
            # past stale_after may have already had it reclaimed by someone else.
            with open(lock_path, encoding="utf-8") as f:
                owner = f.read()
            if owner == token:
                os.remove(lock_path)
        except OSError:
            pass


def read_payload():
    # Empty or malformed input is tolerated: this hook must never fail an agent's run.
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def main():
    # Whatever throws, this hook must still exit 0 rather than crash the run.
    try:
        payload = read_payload()
        if payload.get("stop_hook_active"):
            return 0  # don't re-enter from a stop a stop hook itself triggered

        cfg = kumi_state.load()
        project = kumi_state.project_dir(payload)
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

        # Paths are relative to the state dir so the log reads the same everywhere.
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

        # Fingerprint the current state to skip logging when nothing has changed.
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
        threshold = resolve_rotate_entries(cfg)

        # Rotation and the append share one lock; a failure partway through can drop this entry.
        try:
            with _locked(memory_dir):
                # Once appending would reach the threshold, archive the log and start fresh.
                # Archive first, then remove the active log, so a crash mid-rotation loses nothing.
                if os.path.isfile(log_path):
                    with open(log_path, encoding="utf-8") as f:
                        current_log = f.read()
                    existing = len(ENTRY_RE.findall(current_log))
                    if existing > 0 and existing + 1 >= threshold:
                        rotation_date = datetime.date.today().isoformat()
                        archive_path = os.path.join(memory_dir, f"log.{rotation_date}.md")
                        archived_already = False
                        if os.path.isfile(archive_path):
                            with open(archive_path, encoding="utf-8") as f:
                                archived_already = f.read().endswith(current_log)
                        # If a prior remove failed after archiving, the archive already has
                        # this content; skip the write so a retry can't duplicate it.
                        if not archived_already:
                            archive_mode = "a" if os.path.isfile(archive_path) else "w"
                            with open(archive_path, archive_mode, encoding="utf-8") as f:
                                f.write(current_log)
                        os.remove(log_path)

                first = not os.path.isfile(log_path)
                with open(log_path, "a", encoding="utf-8") as f:
                    if first:
                        f.write(
                            "# kumi memory\n\n"
                            "Append-only record of finished work, captured "
                            "automatically when an agent stops. Nothing here is "
                            "overwritten.\n"
                        )
                    f.write("".join(parts))
                with open(sig_path, "w", encoding="utf-8") as f:
                    f.write(signature)
        except OSError:
            return 0

        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
