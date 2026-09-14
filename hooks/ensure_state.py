#!/usr/bin/env python3
"""kumi state-directory bootstrap hook (UserPromptSubmit, PreToolUse,
UserPromptExpansion).

Every other kumi hook stays silent unless a .kumi directory already exists,
but nothing ever created that directory: a project where kumi is called for
the first time produced no logs, memory, or metrics. This hook creates the
state directory the moment kumi is actually called: a `/kumi:` slash command
typed by the user (UserPromptSubmit), a kumi skill invoked by name
(UserPromptExpansion, on `command_name`), or a kumi subagent (matched on
tool_name "Agent" or the older "Task" name, via PreToolUse). A PreToolUse
"Skill" tool_name is also matched as a defensive fallback, though the current
hooks docs do not list it as a real PreToolUse tool name. Anything else is
left alone, so hooks stay silent in a project where kumi was never called.

When the state directory lands inside a git project (that is, KUMI_STATE_DIR
has not redirected it elsewhere), its relative path is also added to
`.git/info/exclude`, once, so kumi's state never needs the project's own
.gitignore to change. .gitignore itself is never touched.

Must never print to stdout: UserPromptSubmit's and UserPromptExpansion's
stdout are both injected into the session as additional context, and this
hook has nothing to say there. main() has a single outer try/except boundary
so no exception, however unexpected, can ever escape it. Always exits 0,
never raises. Standard library only.

Exit code: always 0.

Complexity: O(1) per call; the exclude file, when touched, is read and
written once, linear in its own (small) size.
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


def is_kumi_call(payload):
    """Return True if this event is a call into kumi.

    A kumi call is a `/kumi:` slash prompt, a kumi skill (typed directly, via
    UserPromptExpansion's `command_name`, or invoked as a PreToolUse tool
    call), or a kumi subagent. Missing or malformed fields mean no, never an
    error.
    """
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
        # Docs show command_name without a leading slash (e.g. "example-skill"
        # for a typed "/example-skill"), but strip one if present just in case.
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
    """Add the state dir's relative path to .git/info/exclude, once.

    Only runs when the state dir is inside the project and the project is a
    git work tree with a real .git directory (not the file a worktree or
    submodule uses there). Never touches .gitignore. Any failure along the
    way is skipped silently: this is a courtesy, not a requirement.
    """
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

        # errors="surrogateescape" so a pre-existing exclude file with stray
        # non-UTF-8 bytes is read without raising instead of crashing the
        # hook. Only appended to below, never rewritten, so those bytes are
        # never touched or corrupted regardless of how they decoded.
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
    # Single outer boundary: whatever throws, however unexpected, this hook
    # must still exit 0 rather than crash the session it's watching.
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
