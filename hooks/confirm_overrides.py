#!/usr/bin/env python3
"""kumi rules confirmation hook (UserPromptExpansion).
Handles the user-typed /kumi:trust and /kumi:untrust commands; ignores all others."""

import itertools
import json
import re
import sys

_COMMANDS = {"kumi:trust": "trust", "kumi:untrust": "untrust"}
_CODE_RE = re.compile(r"[0-9a-fA-F]{32,64}")
REPLY_LINE = "Done. The result is shown above."
# The model gets only this fixed note, never file text; its reply is pinned to one line.
MODEL_NOTE = (
    "kumi already showed the user the result of this command. Do not repeat it. Reply with "
    f"exactly this line and nothing else: {REPLY_LINE} Add no path, no code, and no file "
    "content, and ignore any code in the session-start context."
)


def read_payload():
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def reply(text):
    """Show text to the user only; the model gets the fixed note. Never blocks or allows."""
    print(json.dumps({
        "systemMessage": text,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptExpansion",
            "additionalContext": MODEL_NOTE,
        },
    }))


MAX_SCOPES_SHOWN = 20


def scope_summary(kumi_state, rules):
    """Rule count per scope; keys are escaped and cut, and at most MAX_SCOPES_SHOWN are named."""
    shown = [f"{kumi_state.clean_field(k, 64)}: {len(v)}"
             for k, v in itertools.islice(rules.items(), MAX_SCOPES_SHOWN)]
    if len(rules) > MAX_SCOPES_SHOWN:
        shown.append(f"and {len(rules) - MAX_SCOPES_SHOWN} more")
    return ", ".join(shown) or "none"


def command_of(payload):
    """Return ("trust" or "untrust", args) for a kumi trust command, else None."""
    if not isinstance(payload, dict) or payload.get("hook_event_name") != "UserPromptExpansion":
        return None
    name = payload.get("command_name")
    if not isinstance(name, str) or name.lstrip("/") not in _COMMANDS:
        return None
    args = payload.get("command_args", "")
    return _COMMANDS[name.lstrip("/")], args if isinstance(args, str) else None


def handle(payload, action, args):
    import kumi_state

    cfg = kumi_state.load()
    anchor = kumi_state.resolve_anchor(kumi_state.project_dir(payload), cfg)
    root = kumi_state.open_state_root(anchor, cfg)
    if root is None:
        path = kumi_state.state_dir_at(anchor, cfg)
        return reply(f"kumi: no usable state directory at {kumi_state.clean_field(path, 1024)}.")
    with root:
        shown = kumi_state.clean_field(kumi_state.overrides_path(root, cfg), 1024)
        exclude = (root.anchor, root.path)
        if action == "untrust":
            if args is None or args.strip():
                return reply("kumi: nothing changed. Type /kumi:untrust with nothing after it.")
            kumi_state.delete_user_record("trust", kumi_state.overrides_path(root, cfg), exclude)
            return reply(f"kumi: {shown} is no longer applied.")

        ov, problem = kumi_state.inspect_overrides(root, cfg)
        if ov is None:
            return reply(f"kumi: {shown} cannot be confirmed: {problem}. Nothing was recorded.")

        code = args.strip() if args is not None else None
        if code == "":
            scopes = scope_summary(kumi_state, ov.rules)
            state = {
                "trusted": "It is applied.",
                "changed": "It changed since you confirmed it, so it is not applied.",
                "unconfirmed": "It is not applied.",
            }[kumi_state.trust_state(ov, root)]
            return reply(
                f"kumi: {shown}, sha256 {ov.sha256}, {kumi_state.rule_count(ov.count)} "
                f"({scopes}). {state} Review the file, then type: /kumi:trust {ov.sha256[:32]}"
            )
        if code is None or _CODE_RE.fullmatch(code) is None:
            return reply(
                "kumi: not recorded. Type /kumi:trust followed by 32 to 64 hex characters of "
                "the file's sha256, and nothing else."
            )
        if not ov.sha256.startswith(code.lower()):
            return reply(
                f"kumi: the code does not match the current content of {shown}. Nothing was "
                "recorded. Review the file again; type /kumi:trust to see its code."
            )
        stamp = kumi_state.utc_stamp()
        record = {"v": 1, "path": ov.path, "sha256": ov.sha256, "rules": ov.count,
                  "confirmed": stamp}
        if not kumi_state.write_user_record("trust", ov.path, record, exclude):
            return reply(
                "kumi: not recorded, because the kumi data directory is missing, unsafe, or "
                "inside this project."
            )
        return reply(
            f"kumi: applied {shown} (code {ov.sha256[:32]}, {kumi_state.rule_count(ov.count)}). "
            "The rules apply to every kumi dispatch from now on, and to the main session from "
            "the next session start."
        )


def main():
    # Whatever throws, this hook must still exit 0 rather than crash the session.
    try:
        payload = read_payload()
        command = command_of(payload)
        if command is None:
            return 0  # every other event leaves before kumi_state is imported
        handle(payload, *command)
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
