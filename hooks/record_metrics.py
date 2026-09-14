#!/usr/bin/env python3
"""kumi metrics hook (Stop, SubagentStop).

Records token usage and wall-clock duration for a finished run by parsing its
transcript. On Stop it records the whole session to metrics/sessions.jsonl; on
SubagentStop it records that single subagent run to metrics/agents.jsonl, which
is how per-agent token/time metrics become possible (a subagent has its own
transcript; a skill does not).

Token counts and timestamps are read defensively, because transcript shapes vary
across versions: any usage numbers and ISO timestamps found are summed and
bracketed, and anything missing is simply omitted. The agent name is included
when the transcript exposes it, else recorded as "unknown". Only writes when the
project uses kumi state. Always exits 0, never raises. Standard library only.

Exit code: always 0.

Complexity: one linear pass over the transcript lines; only running sums and the
min/max timestamp are kept, so memory is O(1) in the transcript length.
"""

import json
import os
import sys

import kumi_state


def read_payload():
    # Claude Code hands a hook its input as JSON on stdin. Be lenient: an empty
    # or malformed payload should never take the hook down.
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def scan_transcript(path):
    """Return (token_totals, first_ts, last_ts, agent_name) from a transcript.

    Reads the JSONL transcript line by line, summing any usage fields and
    tracking the earliest and latest timestamps. Best-effort: unknown shapes are
    skipped rather than raising.
    """
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
            # A transcript is JSONL: one record per line. The exact shape drifts
            # between Claude Code versions, so read what we recognise and skip
            # anything we don't rather than failing on a surprise line.
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except ValueError:
                    continue
                # The earliest and latest timestamps bracket the wall-clock time.
                ts = rec.get("timestamp")
                if isinstance(ts, str):
                    first_ts = ts if first_ts is None else min(first_ts, ts)
                    last_ts = ts if last_ts is None else max(last_ts, ts)
                # A subagent run names itself somewhere in its transcript; take
                # the first name we see and keep it.
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
    # Single outer boundary: whatever throws, however unexpected, this hook
    # must still exit 0 rather than crash the run it's watching.
    try:
        payload = read_payload()
        # A stop hook can fire again while it is running; bail so we don't loop.
        if payload.get("stop_hook_active"):
            return 0

        cfg = kumi_state.load()
        project = kumi_state.project_dir(payload)
        kumi = kumi_state.state_dir(project, cfg)
        # No .kumi directory means this project does not use kumi. Stay silent.
        if not os.path.isdir(kumi):
            return 0

        # The transcript is the only place the token counts live.
        transcript = payload.get("transcript_path")
        if not transcript or not os.path.isfile(transcript):
            return 0

        totals, first_ts, last_ts, agent = scan_transcript(transcript)
        event = payload.get("hook_event_name") or ""
        is_subagent = event == "SubagentStop"

        record = {
            "when": last_ts,
            "session": (payload.get("session_id") or "")[:8],
            "tokens": totals,
            "duration_seconds": duration_seconds(first_ts, last_ts),
        }
        # Per-agent attribution only makes sense for a subagent's own transcript.
        if is_subagent:
            record["agent"] = agent or "unknown"

        metrics_dir = os.path.join(kumi, cfg["dirs"]["metrics"])
        try:
            os.makedirs(metrics_dir, exist_ok=True)
        except OSError:
            return 0

        # Subagent runs and whole sessions go to separate files.
        fname = cfg["metrics"]["agents"] if is_subagent else cfg["metrics"]["sessions"]
        try:
            # Append one compact JSON record per line (JSONL).
            with open(os.path.join(metrics_dir, fname), "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except OSError:
            return 0

        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
