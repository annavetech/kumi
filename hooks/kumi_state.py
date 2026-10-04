"""Shared state-layout helper for the kumi hooks.
Resolves state paths, user records, and no-follow file access inside the state dir."""

import collections
import hashlib
import json
import os
import random
import stat
import time
import unicodedata

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
    "memory": {"log": "log.md", "signature": ".last", "rotate_entries": 250, "keep_archives": 3},
    "logs": {"activity": "activity.log"},
    "metrics": {"sessions": "sessions.jsonl", "agents": "agents.jsonl"},
}

_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "runtime.json",
)

_MAX_ANCESTOR_LEVELS = 50

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)  # a FIFO must be refused, not block the hook
_HAS_DIR_FD = bool(
    _NOFOLLOW
    and _DIRECTORY
    and os.open in os.supports_dir_fd
    and os.mkdir in os.supports_dir_fd
    and os.unlink in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
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


# ---- user records, kept outside every project ----------------------------------------------

_RECORD_KINDS = {"trust": "path", "projects": "state_dir"}
_MAX_RECORD_BYTES = 4096


def user_state_dir():
    """$CLAUDE_PLUGIN_DATA if absolute, else ${XDG_STATE_HOME:-~/.local/state}/kumi, else None."""
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if data and os.path.isabs(data):
        return data
    xdg = os.environ.get("XDG_STATE_HOME")
    base = xdg if xdg and os.path.isabs(xdg) else os.path.expanduser("~/.local/state")
    return os.path.join(base, "kumi") if os.path.isabs(base) else None


def _is_inside(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def record_key(real_path):
    return hashlib.sha256(real_path.encode("utf-8", "surrogateescape")).hexdigest()[:32]


def _kind_dir(kind, exclude, create):
    """Open the user record dir for `kind`; None if unusable, inside `exclude`, or unsafe."""
    base = user_state_dir()
    if kind not in _RECORD_KINDS or base is None:
        return None
    base = os.path.realpath(base)
    if any(_is_inside(base, os.path.realpath(e)) for e in exclude if e):
        return None
    path = os.path.join(base, kind)
    try:
        if create:
            os.makedirs(base, 0o700, exist_ok=True)
            try:
                os.mkdir(path, 0o700)
            except FileExistsError:
                pass
        if not _HAS_DIR_FD:
            return path if os.path.isdir(path) and not os.path.islink(path) else None
        fd = os.open(path, os.O_RDONLY | _DIRECTORY | _NOFOLLOW)
    except OSError:
        return None
    st = os.fstat(fd)
    if st.st_uid != os.geteuid() or st.st_mode & 0o022:
        os.close(fd)
        return None
    return fd


def read_user_record(kind, real_path, exclude=()):
    """Return the record for real_path, or None on any doubt (fail closed)."""
    handle = _kind_dir(kind, exclude, create=False)
    if handle is None:
        return None
    try:
        fd = open_at(handle, record_key(real_path) + ".json", os.O_RDONLY)
        if fd is None:
            return None
        try:
            st = os.fstat(fd)
            if _HAS_DIR_FD and st.st_uid != os.geteuid():
                return None
            if st.st_size > _MAX_RECORD_BYTES:
                return None
            raw = os.read(fd, _MAX_RECORD_BYTES + 1)
        finally:
            os.close(fd)
        record = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):
        return None
    finally:
        close_handle(handle)
    if not isinstance(record, dict) or record.get("v") != 1:
        return None
    if record.get(_RECORD_KINDS[kind]) != real_path:
        return None
    return record


def write_user_record(kind, real_path, record, exclude=()):
    """Write record atomically (temp file, then replace); return True on success."""
    handle = _kind_dir(kind, exclude, create=True)
    if handle is None:
        return False
    name = record_key(real_path) + ".json"
    tmp = f".{name}.{os.getpid()}.{random.getrandbits(32):08x}.tmp"
    try:
        fd = open_at(handle, tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        if fd is None:
            return False
        try:
            os.write(fd, json.dumps(record).encode("utf-8"))
        finally:
            os.close(fd)
        try:
            replace_at(handle, tmp, handle, name)
        except OSError:
            _unlink_quiet(handle, tmp)
            return False
        return True
    except OSError:
        return False
    finally:
        close_handle(handle)


def delete_user_record(kind, real_path, exclude=()):
    """Remove the record for real_path; True if one was removed."""
    handle = _kind_dir(kind, exclude, create=False)
    if handle is None:
        return False
    try:
        unlink_at(handle, record_key(real_path) + ".json")
        return True
    except OSError:
        return False
    finally:
        close_handle(handle)


def is_enabled(state_path, anchor=None):
    """True if the user enabled this state dir by calling kumi in the project."""
    real = os.path.realpath(state_path)
    return read_user_record("projects", real, (anchor, real)) is not None


def utc_stamp():
    """ISO 8601 UTC time, written so it also runs on Python 3.9."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def enable(state_path, anchor=None):
    real = os.path.realpath(state_path)
    stamp = utc_stamp()
    record = {"v": 1, "state_dir": real, "enabled": stamp}
    return write_user_record("projects", real, record, (anchor, real))


# ---- anchor resolution ----------------------------------------------------------------------


def resolve_anchor(project, cfg):
    """Nearest level with `.git`; without git, the nearest enabled ancestor state dir, else
    the project itself. A `.kumi` the user never enabled is never used."""
    start = current = os.path.realpath(project)
    enabled = None
    for _ in range(_MAX_ANCESTOR_LEVELS):
        if os.path.exists(os.path.join(current, ".git")):
            return current
        if enabled is None:
            candidate = state_dir_at(current, cfg)
            if os.path.isdir(candidate) and is_enabled(candidate, current):
                enabled = current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return enabled if enabled is not None else start


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


# ---- no-follow access inside the state dir ---------------------------------------------------
# A handle is a directory fd, or a checked path where dir_fd is unsupported (Windows).


class StateRoot:
    """An opened state dir: `handle` for access, `path` (its real path) and `anchor` for text."""

    __slots__ = ("handle", "path", "anchor")

    def __init__(self, handle, path, anchor):
        self.handle, self.path, self.anchor = handle, path, anchor

    def close(self):
        close_handle(self.handle)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def close_handle(handle):
    if isinstance(handle, int):
        try:
            os.close(handle)
        except OSError:
            pass


def _check_not_link(handle, name):
    """Fallback only: refuse a symlinked component (a check-then-open race remains)."""
    if os.path.islink(os.path.join(handle, name)):
        raise OSError(40, "symbolic link refused", name)


def open_at(handle, name, flags, mode=0o600):
    """Open name under handle without following a link; refuse anything not a regular file."""
    if isinstance(handle, int):
        fd = os.open(name, flags | _NOFOLLOW | _NONBLOCK, mode, dir_fd=handle)
    else:
        _check_not_link(handle, name)
        fd = os.open(os.path.join(handle, name), flags | _NONBLOCK, mode)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        return None
    return fd


def _open_dir_at(handle, name, create, mode=0o700):
    if isinstance(handle, int):
        try:
            return os.open(name, os.O_RDONLY | _DIRECTORY | _NOFOLLOW, dir_fd=handle)
        except FileNotFoundError:
            if not create:
                raise
            os.mkdir(name, mode, dir_fd=handle)
            return os.open(name, os.O_RDONLY | _DIRECTORY | _NOFOLLOW, dir_fd=handle)
    path = os.path.join(handle, name)
    _check_not_link(handle, name)
    if create and not os.path.exists(path):
        os.mkdir(path, mode)
    if not os.path.isdir(path):
        raise NotADirectoryError(path)
    return path


def unlink_at(handle, name):
    if isinstance(handle, int):
        os.unlink(name, dir_fd=handle)
    else:
        _check_not_link(handle, name)
        os.unlink(os.path.join(handle, name))


def _unlink_quiet(handle, name):
    try:
        unlink_at(handle, name)
    except OSError:
        pass


def replace_at(src_handle, src, dst_handle, dst):
    if isinstance(src_handle, int):
        os.replace(src, dst, src_dir_fd=src_handle, dst_dir_fd=dst_handle)
    else:
        _check_not_link(dst_handle, dst)
        os.replace(os.path.join(src_handle, src), os.path.join(dst_handle, dst))


def _components(rel):
    return [p for p in os.path.normpath(rel).split(os.sep) if p and p != "."]


def open_dir(path):
    """Handle for an already-resolved directory path; the caller closes it."""
    if not _HAS_DIR_FD:
        if not os.path.isdir(path):
            raise NotADirectoryError(path)
        return path
    return os.open(path, os.O_RDONLY | _DIRECTORY)


def open_state_root(anchor, cfg, create=False):
    """Open the state dir without following a link in any component below the anchor."""
    override = os.environ.get("KUMI_STATE_DIR")
    override = os.path.expanduser(override) if override else ""
    try:
        if override and os.path.isabs(override):
            real = os.path.realpath(override)  # the user chose this path, links included
            if create:
                os.makedirs(real, exist_ok=True)
            if not _HAS_DIR_FD:
                return StateRoot(real, real, anchor) if os.path.isdir(real) else None
            return StateRoot(os.open(real, os.O_RDONLY | _DIRECTORY), real, anchor)
        anchor = os.path.realpath(anchor)
        parts = _components(override or cfg["state_dir"])
        if not parts:
            return None
        handle = anchor if not _HAS_DIR_FD else os.open(anchor, os.O_RDONLY | _DIRECTORY)
        for name in parts:
            try:
                nxt = _open_dir_at(handle, name, create)
            finally:
                close_handle(handle)
            handle = nxt
        return StateRoot(handle, os.path.normpath(os.path.join(anchor, *parts)), anchor)
    except OSError:
        return None


def open_dir_in_state(handle, parts, create=False, mode=0o700):
    """Walk parts as directories (no links); return a handle, or None. Caller closes it."""
    current = handle
    owned = False
    try:
        for name in parts:
            nxt = _open_dir_at(current, name, create, mode)
            if owned:
                close_handle(current)
            current, owned = nxt, True
    except OSError:
        if owned:
            close_handle(current)
        return None
    if not owned and isinstance(handle, int):
        return os.dup(handle)
    return current


def open_in_state(handle, parts, flags, create_dirs=False, mode=0o600):
    """Open the file at parts below handle, no link followed anywhere; fd or None."""
    parent = open_dir_in_state(handle, parts[:-1], create_dirs)
    if parent is None:
        return None
    try:
        return open_at(parent, parts[-1], flags, mode)
    except OSError:
        return None
    finally:
        close_handle(parent)


def unlink_in_state(handle, parts):
    parent = open_dir_in_state(handle, parts[:-1])
    if parent is None:
        return False
    try:
        unlink_at(parent, parts[-1])
        return True
    except OSError:
        return False
    finally:
        close_handle(parent)


def replace_in_state(handle, src_parts, dst_parts):
    src = open_dir_in_state(handle, src_parts[:-1])
    dst = open_dir_in_state(handle, dst_parts[:-1])
    try:
        if src is None or dst is None:
            return False
        replace_at(src, src_parts[-1], dst, dst_parts[-1])
        return True
    except OSError:
        return False
    finally:
        close_handle(src)
        close_handle(dst)


def read_state_text(handle, parts, limit):
    """Read at most limit bytes of a regular file under handle, decoded as UTF-8."""
    fd = open_in_state(handle, parts, os.O_RDONLY)
    if fd is None:
        return None
    try:
        return _read_up_to(fd, limit).decode("utf-8", errors="replace")
    except OSError:
        return None
    finally:
        os.close(fd)


def _read_up_to(fd, limit):
    chunks, left = [], limit
    while left > 0:
        chunk = os.read(fd, min(left, 65536))
        if not chunk:
            break
        chunks.append(chunk)
        left -= len(chunk)
    return b"".join(chunks)


def is_regular_in_state(handle, parts):
    """lstat only: True if parts names a regular file, no link followed on the way."""
    parent = open_dir_in_state(handle, parts[:-1])
    if parent is None:
        return False
    try:
        if isinstance(parent, int):
            st = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        else:
            st = os.lstat(os.path.join(parent, parts[-1]))
        return stat.S_ISREG(st.st_mode)
    except OSError:
        return False
    finally:
        close_handle(parent)


def lstat_at(handle, name):
    """stat of name under handle without following a link; None if it does not exist."""
    try:
        if isinstance(handle, int):
            return os.stat(name, dir_fd=handle, follow_symlinks=False)
        return os.lstat(os.path.join(handle, name))
    except FileNotFoundError:
        return None


def list_dir(handle):
    """Return (name, is_dir, is_file) for each entry, links reported as neither."""
    with os.scandir(handle) as it:
        return [
            (e.name, e.is_dir(follow_symlinks=False), e.is_file(follow_symlinks=False))
            for e in it
            if not e.is_symlink()
        ]


# ---- field cleaning ---------------------------------------------------------------------------

_NAMED_ESCAPES = {"\t": "\\t", "\r": "\\r", "\n": "\\n"}
_UNSAFE_CATEGORIES = frozenset(("Cc", "Cf", "Zl", "Zp", "Cs"))  # Cs: lone surrogates


def clean_field(text, limit):
    """Cut to limit chars, then write control, format, and line/paragraph separators as escapes."""
    text = str(text)[:limit]
    if text.isprintable():
        return text
    out = []
    for ch in text:
        if unicodedata.category(ch) not in _UNSAFE_CATEGORIES:
            out.append(ch)
        elif ch in _NAMED_ESCAPES:
            out.append(_NAMED_ESCAPES[ch])
        else:
            code = ord(ch)
            out.append(
                f"\\x{code:02x}" if code < 0x100
                else f"\\u{code:04x}" if code < 0x10000 else f"\\U{code:08x}"
            )
    return "".join(out)


# ---- overrides --------------------------------------------------------------------------------

_MAX_OVERRIDES_BYTES = 65536  # a project's rule file has no reason to exceed 64 KiB

Overrides = collections.namedtuple("Overrides", "path sha256 rules count")


def _rule_text(item):
    """Accept either a {'rule': '...'} object or a plain string."""
    if isinstance(item, dict):
        return str(item.get("rule", "")).strip()
    if isinstance(item, str):
        return item.strip()
    return ""


def rule_count(n):
    return "1 rule" if n == 1 else f"{n} rules"


def overrides_path(root, cfg):
    return os.path.join(root.path, cfg["files"]["overrides"])


def inspect_overrides(root, cfg):
    """Return (Overrides, None), or (None, reason) for a missing or unusable file."""
    name = cfg["files"]["overrides"]
    try:
        fd = open_in_state(root.handle, [name], os.O_RDONLY)
    except OSError:
        fd = None
    if fd is None:
        if is_regular_in_state(root.handle, [name]):
            return None, "it could not be read"
        exists = os.path.lexists(overrides_path(root, cfg))
        return None, "it is not a regular file" if exists else "there is no such file"
    try:
        raw = _read_up_to(fd, _MAX_OVERRIDES_BYTES + 1)
    except OSError:
        return None, "it could not be read"
    finally:
        os.close(fd)
    if len(raw) > _MAX_OVERRIDES_BYTES:
        return None, "it is larger than 64 KiB"
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        return None, "it is not valid JSON"
    if not isinstance(data, dict):
        return None, "it is not a JSON object"
    rules = {}
    for key, items in data.items():
        if key == "_comment" or not isinstance(items, list):
            continue
        texts = [t for t in (_rule_text(item) for item in items) if t]
        if texts:
            rules[key] = texts
    count = sum(len(v) for v in rules.values())
    digest = hashlib.sha256(raw).hexdigest()
    return Overrides(overrides_path(root, cfg), digest, rules, count), None


def read_overrides(root, cfg):
    """No-follow read of overrides.json into an Overrides tuple; None if missing or unusable."""
    return inspect_overrides(root, cfg)[0]


def trust_state(ov, root):
    """"trusted" if the user confirmed these exact bytes, "changed" if other bytes, else
    "unconfirmed"."""
    record = read_user_record("trust", ov.path, (root.anchor, root.path))
    if record is None:
        return "unconfirmed"
    return "trusted" if record.get("sha256") == ov.sha256 else "changed"


def load_trusted_overrides(root, cfg):
    """The rules if the user confirmed the current file, else {}."""
    ov = read_overrides(root, cfg)
    if ov is None or trust_state(ov, root) != "trusted":
        return {}
    return ov.rules
