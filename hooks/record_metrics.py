#!/usr/bin/env python3
"""kumi metrics hook (Stop, SubagentStop).
Records token usage and duration for a finished run, only in a state dir kumi was called in."""

import json
import os
import sys

import kumi_state


def read_payload():
    # An empty or malformed payload should never take the hook down.
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def scan_transcript(path):
    """Return (token_totals, first_ts, last_ts, agent_name) from a transcript, skipping bad rows."""
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    first_ts = last_ts = None
    agent = None
    try:
        with open(path, encoding="utf-8") as f:
            # One JSON record per line; skip anything we don't recognize.
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except ValueError:
                    continue
                ts = rec.get("timestamp")
                if isinstance(ts, str):
                    first_ts = ts if first_ts is None else min(first_ts, ts)
                    last_ts = ts if last_ts is None else max(last_ts, ts)
                agent = agent or rec.get("subagent_type") or rec.get("agent")
                usage = _find_usage(rec)
                if usage:
                    for key in totals:
                        val = usage.get(key)
                        if isinstance(val, int):
                            totals[key] += val
    except OSError:
        pass
    return totals, first_ts, last_ts, agent


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


def resolve_agent_name(payload, transcript_agent):
    """Return the specialist name from "agent_type" stripped of "kumi:", else transcript_agent."""
    agent_type = payload.get("agent_type")
    if isinstance(agent_type, str) and agent_type.strip():
        name = agent_type.strip()
        if name.startswith("kumi:"):
            name = name[len("kumi:") :]
        if name:
            return name
    return transcript_agent or "unknown"


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
        payload = read_payload()
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
    # The transcript is the only place the token counts live.
    transcript = payload.get("transcript_path")
    if not isinstance(transcript, str) or not os.path.isfile(transcript):
        return

    totals, first_ts, last_ts, agent = scan_transcript(transcript)
    is_subagent = payload.get("hook_event_name") == "SubagentStop"

    record = {
        "when": last_ts,
        "session": (payload.get("session_id") or "")[:8],
        "tokens": totals,
        "duration_seconds": duration_seconds(first_ts, last_ts),
    }
    # Per-agent attribution only makes sense for a subagent's own transcript.
    if is_subagent:
        record["agent"] = resolve_agent_name(payload, agent)

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
