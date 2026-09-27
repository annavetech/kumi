#!/usr/bin/env python3
"""kumi override-rules hook (SessionStart).
Reads the project's overrides.json, if any, and injects its rules as house rules for the session."""

import json
import sys

import kumi_state


def read_payload():
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def main():
    # Whatever throws, this hook must still exit 0 rather than crash the session.
    try:
        payload = read_payload()
        cfg = kumi_state.load()
        project = kumi_state.project_dir(payload)
        kumi = kumi_state.state_dir(project, cfg)

        overrides = kumi_state.load_overrides(kumi, cfg)
        lines = []
        for key, texts in overrides.items():
            who = "every specialist" if key == "all" else key
            for text in texts:
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
