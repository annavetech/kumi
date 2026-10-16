#!/usr/bin/env python3
"""kumi metrics hook (Stop, SubagentStop).
Records token usage and duration for a finished run, only in a state dir kumi was called in."""

import json
import os
import sys
import time

import kumi_state

TOKEN_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)
# The transcript is written asynchronously, so its final message can land after the hook starts.
# Wait this long at most for it; with the 3 s stdin deadline this stays inside the 10 s timeout.
FINAL_WAIT_SECONDS = 3.0
POLL_SECONDS = 0.05
# A subagent's last assistant row is often this tool call, with stop_reason null.
HANDBACK_TOOL = "SubagentHandback"
INTERRUPT_TEXTS = ("[Request interrupted by user]", "[Request interrupted by user for tool use]")
LOCAL_COMMAND_TAGS = ("<command-name>", "<local-command-")


class _TranscriptScan:
    """Reads a transcript incrementally, keeping one usage per message id."""

    def __init__(self):
        self.usage_by_id = {}
        self.loose_usage = []
        self.first_ts = self.last_ts = None
        self.finished = False
        self.offset = 0
        self.tail = b""

    def feed(self, path):
        """Read rows appended since the last call; return False if the file cannot be read."""
        try:
            with open(path, "rb") as f:
                f.seek(self.offset)
                chunk = f.read()
        except OSError:
            return False
        self.offset += len(chunk)
        lines = (self.tail + chunk).split(b"\n")
        self.tail = lines.pop()
        # A last line without a newline counts once it parses as a whole record.
        if self.tail.strip() and self._row(self.tail):
            self.tail = b""
        for line in lines:
            self._row(line)
        return True

    def _row(self, raw):
        try:
            rec = json.loads(raw)
        except ValueError:
            return False
        if not isinstance(rec, dict):
            return True
        ts = rec.get("timestamp")
        if isinstance(ts, str):
            self.first_ts = ts if self.first_ts is None else min(self.first_ts, ts)
            self.last_ts = ts if self.last_ts is None else max(self.last_ts, ts)
        usage = _find_usage(rec)
        if usage:
            msg_id = _message_id(rec)
            # Streamed rows repeat the message id with partial usage; the last row is final.
            if msg_id:
                self.usage_by_id[msg_id] = usage
            else:
                self.loose_usage.append(usage)
        kind = rec.get("type")
        if kind == "assistant":
            self.finished = _is_final(rec)
        elif kind == "user":
            # An interrupt ends the run; a new prompt starts a turn whose reply is still due.
            effect = _user_row_effect(rec)
            if effect is not None:
                self.finished = effect
        return True

    def totals(self):
        totals = dict.fromkeys(TOKEN_KEYS, 0)
        for usage in list(self.usage_by_id.values()) + self.loose_usage:
            for key in TOKEN_KEYS:
                val = usage.get(key)
                if isinstance(val, int):
                    totals[key] += val
        return totals


def scan_transcript(path, wait_seconds=0.0):
    """Return (token_totals, first_ts, last_ts), waiting up to wait_seconds for a final message."""
    scan = _TranscriptScan()
    deadline = time.monotonic() + wait_seconds
    while scan.feed(path) and not scan.finished and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
    return scan.totals(), scan.first_ts, scan.last_ts


def _message_id(rec):
    msg = rec.get("message")
    msg_id = msg.get("id") if isinstance(msg, dict) else None
    return msg_id if isinstance(msg_id, str) and msg_id else None


def _is_final(rec):
    """True if an assistant row ends the run: a handback, stop_reason not tool_use, or none."""
    msg = rec.get("message")
    if not isinstance(msg, dict) or "stop_reason" not in msg:
        return True
    content = msg.get("content")
    if isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == HANDBACK_TOOL
        for b in content
    ):
        return True
    return msg.get("stop_reason") not in (None, "tool_use")


def _user_row_effect(rec):
    """Return True for an interrupt, False for a new prompt, None for rows that change nothing."""
    # isMeta rows get the same rule: hand-backs and usage-limit resets start a turn too.
    msg = rec.get("message")
    if not isinstance(msg, dict):
        return None
    content = msg.get("content")
    if isinstance(content, str):
        texts = [content]
    elif isinstance(content, list):
        blocks = [b for b in content if isinstance(b, dict)]
        if any(b.get("type") == "tool_result" for b in blocks):
            return None
        texts = [b.get("text") for b in blocks if isinstance(b.get("text"), str)]
    else:
        return None
    if any(t in INTERRUPT_TEXTS for t in texts):
        return True
    # Local commands such as /exit, and their caveat rows, never get a model reply.
    if texts and texts[0].lstrip().startswith(LOCAL_COMMAND_TAGS):
        return None
    return False


def _find_usage(rec):
    """Locate a usage dict within a transcript record, wherever it sits."""
    if not isinstance(rec, dict):
        return None
    # Usage sometimes sits at the top level, sometimes nested under "message".
    if isinstance(rec.get("usage"), dict):
        return rec["usage"]
    msg = rec.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("usage"), dict):
        return msg["usage"]
    return None


def resolve_agent_name(payload):
    """Return the specialist name from "agent_type" stripped of "kumi:", else "unknown"."""
    agent_type = payload.get("agent_type")
    if isinstance(agent_type, str) and agent_type.strip():
        name = agent_type.strip()
        if name.startswith("kumi:"):
            name = name[len("kumi:") :]
        if name:
            return name
    return "unknown"


def duration_seconds(first_ts, last_ts):
    """Return whole seconds between two ISO timestamps, or None if unavailable."""
    if not (first_ts and last_ts):
        return None
    import datetime
    try:
        # Accept a trailing Z (UTC) as well as an explicit offset.
        a = datetime.datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
        b = datetime.datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
        return max(0, int((b - a).total_seconds()))
    except ValueError:
        return None


def main():
    # Whatever throws, this hook must still exit 0 rather than crash the run.
    try:
        payload = kumi_state.read_payload()
        # A stop hook can fire again while it is running; bail so we don't loop.
        if payload.get("stop_hook_active"):
            return 0

        cfg = kumi_state.load()
        anchor = kumi_state.resolve_anchor(kumi_state.project_dir(payload), cfg)
        root = kumi_state.open_state_root(anchor, cfg)
        # No usable .kumi directory means this project does not use kumi. Stay silent.
        if root is None:
            return 0
        with root:
            if not kumi_state.is_enabled(root.path, anchor):
                return 0  # kumi was never called in this project
            record_run(payload, root, cfg)
        return 0
    except Exception:
        return 0


def record_run(payload, root, cfg):
    is_subagent = payload.get("hook_event_name") == "SubagentStop"
    # Claude Code's internal agents stop with an empty agent_type; they are not team runs.
    agent_type = payload.get("agent_type")
    if is_subagent and not (isinstance(agent_type, str) and agent_type.strip()):
        return
    # On SubagentStop, transcript_path is the main session's transcript.
    # The subagent's own transcript is agent_transcript_path.
    transcript = payload.get("agent_transcript_path" if is_subagent else "transcript_path")
    if not isinstance(transcript, str) or not os.path.isfile(transcript):
        return

    totals, first_ts, last_ts = scan_transcript(transcript, FINAL_WAIT_SECONDS)

    record = {
        "when": last_ts,
        "session": (payload.get("session_id") or "")[:8],
        "tokens": totals,
        "duration_seconds": duration_seconds(first_ts, last_ts),
    }
    # Per-agent attribution only makes sense for a subagent's own transcript.
    if is_subagent:
        record["agent"] = resolve_agent_name(payload)

    # Subagent runs and whole sessions go to separate files, appended one JSON line each.
    fname = cfg["metrics"]["agents"] if is_subagent else cfg["metrics"]["sessions"]
    fd = kumi_state.open_in_state(
        root.handle,
        [cfg["dirs"]["metrics"], fname],
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        create_dirs=True,
    )
    if fd is None:
        return
    try:
        os.write(fd, (json.dumps(record) + "\n").encode("utf-8"))
    finally:
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main())
