#!/usr/bin/env python3
"""kumi override-rules hook (SessionStart).
Reads the project's overrides.json, if any, and injects its rules as house rules for the session."""

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


def rule_text(item):
    """Accept either a {'rule': '...'} object or a plain string."""
    if isinstance(item, dict):
        return str(item.get("rule", "")).strip()
    if isinstance(item, str):
        return item.strip()
    return ""


def main():
    # Whatever throws, this hook must still exit 0 rather than crash the session.
    try:
        payload = read_payload()
        cfg = kumi_state.load()
        project = kumi_state.project_dir(payload)
        kumi = kumi_state.state_dir(project, cfg)

        path = os.path.join(kumi, cfg["files"]["overrides"])
        if not os.path.isfile(path):
            return 0  # no overrides in this project

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return 0
        if not isinstance(data, dict):
            return 0

        # "_comment" is the human note in the template and is skipped.
        lines = []
        for key, items in data.items():
            if key == "_comment" or not isinstance(items, list):
                continue
            who = "every specialist" if key == "all" else key
            for item in items:
                text = rule_text(item)
                if text:
                    lines.append(f"- ({who}) {text}")

        if not lines:
            return 0

        context = (
            "House rules for this project, from .kumi/overrides.json. Follow these on "
            "top of the built-in discipline; a rule for a named specialist applies "
            "when that specialist is doing the work:\n\n" + "\n".join(lines)
        )
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
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
