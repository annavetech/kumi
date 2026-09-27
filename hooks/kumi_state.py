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

_MAX_ANCESTOR_LEVELS = 50


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


def resolve_anchor(project, cfg):
    """Walk upward (bounded, symlinks resolved) to the nearest `.git`; a `.kumi` at or below it
    wins, one above it never does. Falls back to project if neither is found."""
    current = os.path.realpath(project)
    git_root = None
    for _ in range(_MAX_ANCESTOR_LEVELS):
        if os.path.isdir(os.path.join(current, cfg["state_dir"])):
            return current
        if os.path.exists(os.path.join(current, ".git")):
            git_root = current
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return git_root if git_root is not None else project


def state_dir_at(anchor, cfg):
    """Join the state dir (or KUMI_STATE_DIR override) onto an already-resolved anchor."""
    override = os.environ.get("KUMI_STATE_DIR")
    if override:
        override = os.path.expanduser(override)
        return override if os.path.isabs(override) else os.path.join(anchor, override)
    return os.path.join(anchor, cfg["state_dir"])


def state_dir(project, cfg):
    """Return the base state directory; KUMI_STATE_DIR overrides the config's `state_dir`."""
    return state_dir_at(resolve_anchor(project, cfg), cfg)


def _rule_text(item):
    """Accept either a {'rule': '...'} object or a plain string."""
    if isinstance(item, dict):
        return str(item.get("rule", "")).strip()
    if isinstance(item, str):
        return item.strip()
    return ""


_MAX_OVERRIDES_BYTES = 65536  # a project's rule file has no reason to exceed 64 KiB


def load_overrides(kumi, cfg):
    """Read overrides.json from the state dir, if present, into {scope: [rule_text, ...]}.
    Skips "_comment" and any non-list scope; missing, oversized, or malformed file returns {}."""
    path = os.path.join(kumi, cfg["files"]["overrides"])
    if not os.path.isfile(path):
        return {}
    try:
        if os.path.getsize(path) > _MAX_OVERRIDES_BYTES:
            return {}
    except OSError:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    result = {}
    for key, items in data.items():
        if key == "_comment" or not isinstance(items, list):
            continue
        texts = [t for t in (_rule_text(item) for item in items) if t]
        if texts:
            result[key] = texts
    return result
