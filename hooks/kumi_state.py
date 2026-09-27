"""Shared state-layout helper for the kumi hooks.
Resolves state file paths from config/runtime.json, falling back to built-in defaults."""

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
    "memory": {"log": "log.md", "signature": ".last", "restore_entries": 3, "rotate_entries": 250},
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
        # Merge over defaults, top level and one level down, so a partial config resolves every key.
        merged = {**_DEFAULTS, **data}
        for section in ("files", "dirs", "memory", "logs", "metrics"):
            merged[section] = {**_DEFAULTS[section], **data.get(section, {})}
        return merged
    except (OSError, ValueError):
        return dict(_DEFAULTS)


def project_dir(payload):
    """Return payload's "cwd" if it is a non-empty string, else the real working directory."""
    project = payload.get("cwd") if isinstance(payload, dict) else None
    if not isinstance(project, str) or not project:
        return os.getcwd()
    return project


def state_dir(project, cfg):
    """Return the base state directory; KUMI_STATE_DIR overrides the config's `state_dir`."""
    override = os.environ.get("KUMI_STATE_DIR")
    if override:
        override = os.path.expanduser(override)
        return override if os.path.isabs(override) else os.path.join(project, override)
    return os.path.join(project, cfg["state_dir"])
