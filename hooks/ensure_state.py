#!/usr/bin/env python3
"""kumi state-directory bootstrap hook (UserPromptSubmit, PreToolUse, UserPromptExpansion).
Creates and enables the .kumi state directory the moment kumi is called. Never prints to stdout."""

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


# Tools whose 1.3.0 log target was always a file path; Grep, Glob and LS could log a pattern.
_PATH_ONLY_TOOLS = frozenset(("Read", "Write", "Edit", "MultiEdit", "NotebookEdit"))
_MAX_OLD_LINE = 4096


def _git_dir_for(anchor):
    """The dir whose info/exclude git reads: .git itself, or a worktree's common dir."""
    dot_git = os.path.join(anchor, ".git")
    if os.path.islink(dot_git):
        return None  # a linked .git is never followed
    if os.path.isdir(dot_git):
        return dot_git
    if not os.path.isfile(dot_git):
        return None
    with open(dot_git, encoding="utf-8", errors="surrogateescape") as f:
        line = f.readline(4096).strip()
    if not line.startswith("gitdir:"):
        return None
    git_dir = os.path.realpath(os.path.join(anchor, line[len("gitdir:"):].strip()))
    commondir = os.path.join(git_dir, "commondir")
    if os.path.isfile(commondir):
        with open(commondir, encoding="utf-8", errors="surrogateescape") as f:
            git_dir = os.path.realpath(os.path.join(git_dir, f.readline(4096).strip()))
    # Only a real git dir: a .git file pointing anywhere else is skipped.
    if os.path.isfile(os.path.join(git_dir, "HEAD")) and os.path.isdir(
        os.path.join(git_dir, "objects")
    ):
        return git_dir
    return None


def _open_info_dir(git_dir):
    """Open <git_dir>/info, creating only info/, never following a link."""
    parent, name = os.path.split(git_dir)
    base = kumi_state.open_dir(parent)
    try:
        git = kumi_state.open_dir_in_state(base, [name])
    finally:
        kumi_state.close_handle(base)
    if git is None:
        return None
    try:
        return kumi_state.open_dir_in_state(git, ["info"], create=True, mode=0o755)
    finally:
        kumi_state.close_handle(git)


def add_git_exclude(project, kumi):
    """Add the state dir's relative path to info/exclude, once. Never touches .gitignore."""
    try:
        project_abs = os.path.abspath(project)
        kumi_abs = os.path.abspath(kumi)
        rel = os.path.relpath(kumi_abs, project_abs)
        if rel.startswith("..") or os.path.isabs(rel):
            return  # KUMI_STATE_DIR moved state outside the project

        git_dir = _git_dir_for(project_abs)
        if git_dir is None:
            return  # not a git work tree, or a .git that points at no git dir

        entry = rel.replace(os.sep, "/") + "/"
        info = _open_info_dir(git_dir)
        if info is None:
            return
        try:
            fd = kumi_state.open_at(
                info, "exclude", os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o644
            )
        finally:
            kumi_state.close_handle(info)
        if fd is None:
            return
        # surrogateescape so a pre-existing non-UTF-8 exclude file doesn't crash this.
        with os.fdopen(fd, "r+", encoding="utf-8", errors="surrogateescape") as f:
            existing = f.read()
            if entry in existing.splitlines():
                return  # already listed
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(entry + "\n")
    except OSError:
        return


def _old_lines(fin):
    """Yield (line, complete) with each read bounded; the rest of an over-long line is skipped."""
    while True:
        line = fin.readline(_MAX_OLD_LINE)
        if not line:
            return
        complete = len(line) < _MAX_OLD_LINE or line.endswith(b"\n")
        if not complete:
            while True:
                more = fin.readline(_MAX_OLD_LINE)
                if not more or more.endswith(b"\n"):
                    break
        yield line, complete


def clean_activity_log(root, cfg):
    """Once per newly enabled state dir: keep a 1.3.0 target only where it was always a path."""
    logs = cfg["dirs"]["logs"]
    name = cfg["logs"]["activity"]
    src = kumi_state.open_in_state(root.handle, [logs, name], os.O_RDONLY)
    if src is None:
        return
    tmp = name + ".tmp"
    dst = kumi_state.open_in_state(root.handle, [logs, tmp], os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    if dst is None:
        os.close(src)
        return
    with os.fdopen(src, "rb") as fin, os.fdopen(dst, "wb") as fout:
        for line, complete in _old_lines(fin):
            fields = line.rstrip(b"\r\n").split(b"\t", 3)
            tool = fields[2].decode("utf-8", "replace") if len(fields) > 2 else ""
            if complete and len(fields) == 4 and tool in _PATH_ONLY_TOOLS:
                fout.write(line if line.endswith(b"\n") else line + b"\n")
                continue
            head = (fields + [b"-", b"-", b"-"])[:3]
            fout.write(b"\t".join(head + [b"-"]) + b"\n")
    kumi_state.replace_in_state(root.handle, [logs, tmp], [logs, name])


def main():
    # Whatever throws, this hook must still exit 0 rather than crash the session.
    try:
        payload = read_payload()
        if not is_kumi_call(payload):
            return 0

        cfg = kumi_state.load()
        project = kumi_state.project_dir(payload)  # malformed cwd falls back to os.getcwd()
        anchor = kumi_state.resolve_anchor(project, cfg)
        kumi = kumi_state.state_dir_at(anchor, cfg)

        root = kumi_state.open_state_root(anchor, cfg, create=True)
        if root is None:
            return 0  # a symlinked state dir is refused: no enable, no writes
        with root:
            add_git_exclude(anchor, kumi)
            if not kumi_state.is_enabled(root.path, anchor):
                if kumi_state.enable(root.path, anchor):
                    clean_activity_log(root, cfg)
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
