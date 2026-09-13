"""Shared state-layout helper for the kumi hooks.

The names of the kumi state files live in config/runtime.json, so hooks resolve
paths through this helper instead of hardcoding them. If the config is missing
or unreadable, built-in defaults are used, because a hook must never fail just
because a config file was moved. Standard library only.
"""

import json
import os

# Defaults mirror config/runtime.json; used only if the config cannot be read.
_DEFAULTS = {
    "state_dir": ".kumi",
    "files": {"status": "status.md", "handoff": "handoff.md", "overrides": "overrides.json"},
    "dirs": {
        "decisions": "decisions",
        "memory": "memory",
        "logs": "logs",
        "metrics": "metrics",
    },
    "memory": {"log": "log.md", "signature": ".last", "restore_entries": 3},
    "logs": {"activity": "activity.log"},
    "metrics": {"sessions": "sessions.jsonl", "agents": "agents.jsonl"},
}

_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "runtime.json",
)


def load():
    """Return the runtime config as a dict, falling back to defaults on error."""
    try:
        with open(_CONFIG, encoding="utf-8") as f:
            data = json.load(f)
        # Merge the file over the defaults, top level and one level down, so a
        # partial config (say only state_dir was changed) still resolves every
        # key the hooks expect.
        merged = {**_DEFAULTS, **data}
        for section in ("files", "dirs", "memory", "logs", "metrics"):
            merged[section] = {**_DEFAULTS[section], **data.get(section, {})}
        return merged
    except (OSError, ValueError):
        return dict(_DEFAULTS)


def project_dir(payload):
    """Return a usable project directory from a hook payload's "cwd" field.

    A hook payload's cwd is expected to be a non-empty string. Anything else
    (missing, None, "", or the wrong type such as an int, list, or dict) falls
    back to the process's real working directory, so callers never hand a bad
    type into os.path.join downstream.
    """
    project = payload.get("cwd") if isinstance(payload, dict) else None
    if not isinstance(project, str) or not project:
        return os.getcwd()
    return project


def state_dir(project, cfg):
    """Return the base directory kumi keeps its state in.

    By default this is the `state_dir` from the config, inside the working
    project. Setting the KUMI_STATE_DIR environment variable overrides it: an
    absolute path (with ~ allowed) is used as-is, so state can live in one place
    across projects; a relative path is taken from the project root.
    """
    override = os.environ.get("KUMI_STATE_DIR")
    if override:
        override = os.path.expanduser(override)
        return override if os.path.isabs(override) else os.path.join(project, override)
    return os.path.join(project, cfg["state_dir"])
