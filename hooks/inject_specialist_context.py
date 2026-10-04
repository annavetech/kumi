#!/usr/bin/env python3
"""kumi specialist-dispatch hook (PreToolUse, matcher Agent|Task).
Denies a brief missing a required part; else appends the rules the user confirmed to the prompt."""

import json
import re
import sys

import kumi_state

REQUIRED_BRIEF_PARTS = ["goal", "output format", "where to look", "limits"]


def read_payload():
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def specialist_name(tool_input):
    """Return the kumi: prefix stripped subagent_type, or None if this isn't a kumi dispatch."""
    subagent = tool_input.get("subagent_type") if isinstance(tool_input, dict) else None
    if not isinstance(subagent, str) or not subagent.startswith("kumi:"):
        return None
    return subagent[len("kumi:"):]


def _label_pattern(part):
    """An inline label line for `part`: an optional numbered or bullet marker, the
    label text, then a colon or a dash separator, e.g. "1. Goal:", "- Where to look -"."""
    return re.compile(
        rf"^\s*(?:\d+[.)]\s*|[-*+]\s*)?\**{re.escape(part)}\**\s*(?::|-)\s*(.*)$",
        re.IGNORECASE,
    )


def _heading_pattern(part):
    """A markdown heading line naming `part`, e.g. "## Goal"; content follows below."""
    return re.compile(rf"^\s*#{{1,6}}\s+\**{re.escape(part)}\**\s*:?\s*(.*)$", re.IGNORECASE)


_PART_PATTERNS = {
    part: (_label_pattern(part), _heading_pattern(part)) for part in REQUIRED_BRIEF_PARTS
}
_ALL_PATTERNS = [p for pair in _PART_PATTERNS.values() for p in pair]

_MIN_CONTENT_ALNUM = 2  # lets a genuine short answer ("ok", "N/A", "none") through


def _is_label_line(line):
    return any(p.match(line) for p in _ALL_PATTERNS)


def _has_real_content(text):
    """At least _MIN_CONTENT_ALNUM letters or digits, so a bare punctuation answer
    like "-", ".", or "..." does not count as content."""
    return len(re.findall(r"[A-Za-z0-9]", text)) >= _MIN_CONTENT_ALNUM


def missing_brief_parts(prompt):
    """Return the required parts (goal, output format, where to look, limits) with no
    real content after their inline label or markdown heading."""
    if not isinstance(prompt, str):
        return list(REQUIRED_BRIEF_PARTS)
    lines = prompt.splitlines()
    missing = []
    for part in REQUIRED_BRIEF_PARTS:
        label_pattern, heading_pattern = _PART_PATTERNS[part]
        matched = False
        has_content = False
        for i, line in enumerate(lines):
            m = label_pattern.match(line) or heading_pattern.match(line)
            if not m:
                continue
            matched = True
            if _has_real_content(m.group(1)):
                has_content = True
                break
            for j in range(i + 1, len(lines)):
                if not lines[j].strip():
                    continue
                has_content = not _is_label_line(lines[j]) and _has_real_content(lines[j])
                break
            break
        if not (matched and has_content):
            missing.append(part)
    return missing


def deny_incomplete_brief(missing):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "Brief is missing: " + ", ".join(missing) + ". Add a labeled section for "
                "each missing part (Goal:, Output format:, Where to look:, Limits:) and "
                "dispatch again."
            ),
        }
    }))


def specialist_rule_lines(overrides, specialist):
    """Rules scoped to "all" plus the named specialist, in the same "(who) text" shape
    apply_overrides.py uses for SessionStart context."""
    lines = []
    for key in ("all", specialist):
        for text in overrides.get(key, []):
            who = "every specialist" if key == "all" else key
            lines.append(f"- ({who}) {text}")
    return lines


def updated_input_with_rules(tool_input, lines, path):
    """Return tool_input with the project rules appended to prompt; every other field unchanged."""
    context = (
        f"Project rules the user confirmed ({path}). Follow these on top of the built-in "
        "discipline:\n\n" + "\n".join(lines)
    )
    updated = dict(tool_input)
    prompt = updated.get("prompt", "")
    updated["prompt"] = (prompt.rstrip() + "\n\n" + context) if prompt else context
    return updated


def emit_updated_input(updated_input):
    """No permissionDecision here: updatedInput alone edits the call while the
    normal permission flow still decides whether it runs."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": updated_input,
        }
    }))


def main():
    # Whatever throws, this hook must still exit 0 rather than block the dispatch.
    try:
        payload = read_payload()
        if not isinstance(payload, dict) or payload.get("tool_name") not in ("Agent", "Task"):
            return 0
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0
        specialist = specialist_name(tool_input)
        if specialist is None:
            return 0

        missing = missing_brief_parts(tool_input.get("prompt"))
        if missing:
            deny_incomplete_brief(missing)
            return 0

        cfg = kumi_state.load()
        anchor = kumi_state.resolve_anchor(kumi_state.project_dir(payload), cfg)
        root = kumi_state.open_state_root(anchor, cfg)
        if root is None:
            return 0
        with root:
            overrides = kumi_state.load_trusted_overrides(root, cfg)
            path = kumi_state.clean_field(kumi_state.overrides_path(root, cfg), 1024)
        lines = specialist_rule_lines(overrides, specialist)
        if not lines:
            return 0

        emit_updated_input(updated_input_with_rules(tool_input, lines, path))
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
