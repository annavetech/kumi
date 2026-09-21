#!/usr/bin/env python3
"""kumi state-directory bootstrap hook (UserPromptSubmit, PreToolUse, UserPromptExpansion).
Creates the .kumi state directory the moment kumi is called. Must never print to stdout."""

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


def is_kumi_call(payload):
    """Return True if this event is a call into kumi; malformed fields mean no, not an error."""
    if not isinstance(payload, dict):
        return False
    event = payload.get("hook_event_name")

    if event == "UserPromptSubmit":
        prompt = payload.get("prompt")
        return isinstance(prompt, str) and prompt.lstrip().startswith("/kumi:")

    if event == "UserPromptExpansion":
        command_name = payload.get("command_name")
        if not isinstance(command_name, str):
            return False
        # command_name usually has no leading slash, but strip one if present.
        return command_name.lstrip("/").startswith("kumi:")

    if event == "PreToolUse":
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return False
        tool_name = payload.get("tool_name")
        if tool_name == "Skill":
            skill = tool_input.get("skill")
            return isinstance(skill, str) and skill.startswith("kumi:")
        if tool_name in ("Agent", "Task"):
            subagent = tool_input.get("subagent_type")
            return isinstance(subagent, str) and subagent.startswith("kumi:")
        return False

    return False


def add_git_exclude(project, kumi):
    """Add the state dir's relative path to .git/info/exclude, once. Never touches .gitignore."""
    try:
        project_abs = os.path.abspath(project)
        kumi_abs = os.path.abspath(kumi)
        rel = os.path.relpath(kumi_abs, project_abs)
        if rel.startswith("..") or os.path.isabs(rel):
            return  # KUMI_STATE_DIR moved state outside the project

        git_dir = os.path.join(project_abs, ".git")
        if not os.path.isdir(git_dir):
            return  # not a git work tree, or .git is a file (worktree/submodule)

        entry = rel.replace(os.sep, "/") + "/"
        exclude_path = os.path.join(git_dir, "info", "exclude")

        # surrogateescape so a pre-existing non-UTF-8 exclude file doesn't crash this.
        existing = ""
        if os.path.isfile(exclude_path):
            with open(exclude_path, encoding="utf-8", errors="surrogateescape") as f:
                existing = f.read()
        if entry in existing.splitlines():
            return  # already listed

        os.makedirs(os.path.dirname(exclude_path), exist_ok=True)
        with open(exclude_path, "a", encoding="utf-8", errors="surrogateescape") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(entry + "\n")
    except OSError:
        return


def main():
    # Whatever throws, this hook must still exit 0 rather than crash the session.
    try:
        payload = read_payload()
        if not is_kumi_call(payload):
            return 0

        cfg = kumi_state.load()
        project = kumi_state.project_dir(payload)  # malformed cwd falls back to os.getcwd()
        kumi = kumi_state.state_dir(project, cfg)

        os.makedirs(kumi, exist_ok=True)
        add_git_exclude(project, kumi)
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
