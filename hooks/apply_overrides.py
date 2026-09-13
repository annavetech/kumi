#!/usr/bin/env python3
"""kumi override-rules hook (SessionStart).

Lets a user add or change rules without touching any source file. If the project
has an overrides file (overrides.json in the kumi state directory), this reads it
at the start of a session and injects the rules as house rules on top of the
built-in ones. It is the same idea as a CLAUDE.md, but structured per specialist.

The file's shape is a map from "all" or a specialist's name to a list of rule
objects, each with a "rule" field:

    {
      "all": [
        { "rule": "Prefer table-driven tests." }
      ],
      "jaan": [
        { "rule": "Use the project's error-wrapping helper." }
      ]
    }

A plain string is also accepted in place of an object, so a hand-edited file is
forgiving. See config/overrides.example.json for a template. Always exits 0 and
never raises. Standard library only.

Exit code: always 0.
"""

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
    payload = read_payload()
    cfg = kumi_state.load()
    project = payload.get("cwd") or os.getcwd()
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

    # Each top-level key is either "all" (rules for the whole team) or a
    # specialist's name (rules just for that one). "_comment" is the human note
    # in the template and is skipped.
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


if __name__ == "__main__":
    sys.exit(main())
