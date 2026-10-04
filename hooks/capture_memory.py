#!/usr/bin/env python3
"""kumi memory capture hook (Stop, SubagentStop).
Appends a snapshot of kumi state to the memory log, with the handoff capped and block-quoted."""

import codecs
import contextlib
import datetime
import hashlib
import heapq
import json
import os
import random
import re
import stat
import sys
import time

import kumi_state

# The heading shape every entry starts with; used here only to count entries.
ENTRY_RE = re.compile(r"\n## \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\n")
# log.<date>.md (kumi 1.3.0 and earlier) and log.<date>-<HHMMSS>[-n].md.
ARCHIVE_RE = re.compile(r"^log\.(\d{4}-\d{2}-\d{2})(?:-(\d{6})(?:-(\d+))?)?\.md$")
_MAX_SAME_SECOND = 1000

DEFAULT_ROTATE_ENTRIES = 250
DEFAULT_KEEP_ARCHIVES = 3
HANDOFF_CAP_CHARS = 4000
MAX_DECISIONS_LISTED = 200
MAX_DECISION_NAME = 200  # characters per listed name, so an entry stays bounded
_MAX_DECISION_DEPTH = 8
_CHUNK = 65536
LOG_HEADER = (
    b"# kumi memory\n\n"
    b"Record of finished work, captured automatically when an agent stops. New entries are "
    b"appended; a full log moves to a dated archive, and only the newest archives are kept.\n"
)


def resolve_rotate_entries(cfg):
    """Return a valid rotation threshold; a bad or non-positive value falls back to the default."""
    raw = cfg["memory"].get("rotate_entries", DEFAULT_ROTATE_ENTRIES)
    try:
        threshold = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_ROTATE_ENTRIES
    return threshold if threshold > 0 else DEFAULT_ROTATE_ENTRIES


def resolve_keep_archives(cfg):
    """Return how many dated archives to keep: 0 keeps none, bad or negative falls back to 3."""
    raw = cfg["memory"].get("keep_archives", DEFAULT_KEEP_ARCHIVES)
    if isinstance(raw, bool):
        return DEFAULT_KEEP_ARCHIVES
    try:
        keep = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_KEEP_ARCHIVES
    return keep if keep >= 0 else DEFAULT_KEEP_ARCHIVES


def _open(dir_fd, name, flags):
    """No-follow open of one name in dir_fd; raises OSError, None if not a regular file."""
    return kumi_state.open_at(dir_fd, name, flags)


def _read_all(dir_fd, name):
    try:
        fd = _open(dir_fd, name, os.O_RDONLY)
    except OSError:
        return None
    if fd is None:
        return None
    with os.fdopen(fd, "rb") as f:
        return f.read().decode("utf-8", errors="replace")


def _write(dir_fd, name, text, flags):
    fd = _open(dir_fd, name, os.O_WRONLY | os.O_CREAT | flags)
    if fd is None:
        raise OSError("refused: " + name)
    with os.fdopen(fd, "wb") as f:
        f.write(text.encode("utf-8"))


def _mtime(dir_fd, name):
    if isinstance(dir_fd, int):
        return os.stat(name, dir_fd=dir_fd, follow_symlinks=False).st_mtime
    return os.lstat(os.path.join(dir_fd, name)).st_mtime


@contextlib.contextmanager
def _locked(dir_fd, timeout=2.0, stale_after=30.0):
    """Exclusive lock via atomic, no-follow file creation in the memory dir, so two
    Stop/SubagentStop hooks racing never clobber or interleave each other's writes."""
    token = f"{os.getpid()}-{random.getrandbits(32)}"
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = _open(dir_fd, ".lock", os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            if fd is None:
                raise TimeoutError("lock path is not a regular file")
            with os.fdopen(fd, "w") as f:
                f.write(token)
            break
        except FileExistsError:
            try:
                if time.time() - _mtime(dir_fd, ".lock") > stale_after:
                    kumi_state.unlink_at(dir_fd, ".lock")  # abandoned by a crashed hook
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError("timed out waiting for the memory lock") from None
            time.sleep(0.02)
    try:
        yield
    finally:
        try:
            # Only remove the lock if it still holds this process's token: a slow holder
            # past stale_after may have already had it reclaimed by someone else.
            if _read_all(dir_fd, ".lock") == token:
                kumi_state.unlink_at(dir_fd, ".lock")
        except OSError:
            pass


def read_payload():
    # Empty or malformed input is tolerated: this hook must never fail an agent's run.
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def read_handoff(root, cfg):
    """Return (kept text, total chars, sha256 hex, has content); hashes all, keeps the cap."""
    fd = kumi_state.open_in_state(root.handle, [cfg["files"]["handoff"]], os.O_RDONLY)
    if fd is None:
        return "", 0, "", False
    hasher = hashlib.sha256()
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    kept, total, has_content = [], 0, False
    try:
        while True:
            chunk = os.read(fd, _CHUNK)
            final = not chunk
            hasher.update(chunk)
            text = decoder.decode(chunk, final=final)
            if total < HANDOFF_CAP_CHARS:
                kept.append(text[: HANDOFF_CAP_CHARS - total])
            total += len(text)
            has_content = has_content or bool(text.strip())
            if final:
                break
    finally:
        os.close(fd)
    return "".join(kept), total, hasher.hexdigest(), has_content


def walk_decisions(root, cfg):
    """Yield cleaned "decisions/.../name.md" paths; links are skipped, depth is bounded."""
    stack = [[cfg["dirs"]["decisions"]]]
    while stack:
        prefix = stack.pop()
        # Opened on pop, so at most one directory handle is held at a time.
        handle = kumi_state.open_dir_in_state(root.handle, prefix)
        if handle is None:
            continue
        try:
            entries = kumi_state.list_dir(handle)
        except OSError:
            entries = []
        finally:
            kumi_state.close_handle(handle)
        for name, is_dir, is_file in entries:
            if is_file and name.endswith(".md"):
                rel = kumi_state.clean_field(os.path.join(*prefix, name), MAX_DECISION_NAME)
                yield rel[:MAX_DECISION_NAME]  # escapes can lengthen a name; keep the bound
            elif is_dir and len(prefix) <= _MAX_DECISION_DEPTH:
                stack.append(prefix + [name])


def decision_summary(root, cfg):
    """Return (first names sorted, total count, order-free digest) in O(cap) space."""
    count = 0
    digest = 0

    def counted():
        nonlocal count, digest
        for rel in walk_decisions(root, cfg):
            count += 1
            digest = (digest + int(hashlib.sha256(rel.encode("utf-8")).hexdigest(), 16)) % (
                1 << 256
            )
            yield rel

    first = heapq.nsmallest(MAX_DECISIONS_LISTED, counted())
    return first, count, digest


def quote(text):
    """Every line becomes a block-quote line, so handoff text can never start an entry."""
    return "".join(("> " + line if line else ">") + "\n" for line in text.splitlines())


def prune_archives(mem, keep):
    """Unlink the oldest archives (by the date, time and counter in the name) beyond keep."""
    dated = sorted(
        (m.group(1), m.group(2) or "", int(m.group(3) or 0), name)
        for name, _is_dir, is_file in kumi_state.list_dir(mem)
        if is_file and (m := ARCHIVE_RE.match(name))
    )
    for *_key, name in dated[: max(0, len(dated) - keep)]:
        try:
            kumi_state.unlink_at(mem, name)
        except OSError:
            pass


def main():
    # Whatever throws, this hook must still exit 0 rather than crash the run.
    try:
        payload = read_payload()
        if not isinstance(payload, dict) or payload.get("stop_hook_active"):
            return 0  # don't re-enter from a stop a stop hook itself triggered

        cfg = kumi_state.load()
        anchor = kumi_state.resolve_anchor(kumi_state.project_dir(payload), cfg)
        root = kumi_state.open_state_root(anchor, cfg)
        if root is None:
            return 0
        with root:
            if not kumi_state.is_enabled(root.path, anchor):
                return 0  # kumi was never called in this project
            capture(root, cfg)
        return 0
    except Exception:
        return 0


def capture(root, cfg):
    kept, total, handoff_hash, has_handoff = read_handoff(root, cfg)
    decisions, decision_count, decision_digest = decision_summary(root, cfg)
    if not has_handoff and not decision_count:
        return  # nothing worth remembering yet

    # Fingerprint the current state to skip logging when nothing has changed.
    signature = hashlib.sha256(
        f"{handoff_hash}\n{decision_count}\n{decision_digest:064x}".encode()
    ).hexdigest()

    mem = kumi_state.open_dir_in_state(root.handle, [cfg["dirs"]["memory"]], create=True)
    if mem is None:
        return
    try:
        sig_name = cfg["memory"]["signature"]
        st = kumi_state.lstat_at(mem, sig_name)
        if st is not None and not stat.S_ISREG(st.st_mode):
            return  # a .last that is a link or other non-file: capture nothing
        sig, known_count, known_size = parse_signature(
            kumi_state.read_state_text(mem, [sig_name], 256)
        )
        if sig == signature:
            return  # state unchanged since last capture

        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        parts = [f"\n## {stamp}\n"]
        if decision_count:
            parts.append("\nDecision files present:\n")
            parts.extend(f"- {rel}\n" for rel in decisions)
            if decision_count > len(decisions):
                parts.append(f"- and {decision_count - len(decisions)} more\n")
        if has_handoff:
            parts.append("\nHandoff at completion:\n\n")
            parts.append(quote(kept.rstrip()))
            if total > HANDOFF_CAP_CHARS:
                parts.append(f"> [cut: {total} characters; see the handoff file]\n")
        entry = "".join(parts).encode("utf-8", errors="backslashreplace")

        try:
            with _locked(mem):
                count, size = append_entry(mem, cfg, entry, known_count, known_size)
                _write(mem, sig_name, f"{signature} {count} {size}\n", os.O_TRUNC)
        except (OSError, TimeoutError):
            return
    finally:
        kumi_state.close_handle(mem)


def parse_signature(text):
    """Return (signature, entry count, log size) from .last; count and size None if absent."""
    fields = (text or "").split()
    sig = fields[0] if fields else None
    try:
        return sig, int(fields[1]), int(fields[2])
    except (IndexError, ValueError):
        return sig, None, None


def _read_fd(fd):
    """Read a whole file from the start through fd."""
    os.lseek(fd, 0, os.SEEK_SET)
    chunks = []
    while True:
        chunk = os.read(fd, _CHUNK)
        if not chunk:
            return b"".join(chunks).decode("utf-8", errors="replace")
        chunks.append(chunk)


def archive_name(mem):
    """A name no archive uses yet: log.<date>-<HHMMSS>.md, then -1, -2 within one second."""
    base = "log." + datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    for n in range(_MAX_SAME_SECOND):
        name = f"{base}-{n}.md" if n else f"{base}.md"
        if kumi_state.lstat_at(mem, name) is None:
            return name
    raise OSError("no free archive name")


def append_entry(mem, cfg, entry, known_count, known_size):
    """Append entry, rotating first when the log is full; return (entries, size) after.
    The log is read only when its size differs from the last capture or it must rotate."""
    log_name = cfg["memory"]["log"]
    threshold = resolve_rotate_entries(cfg)
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
    fd = _open(mem, log_name, flags)
    if fd is None:
        raise OSError("refused: " + log_name)
    try:
        size = os.fstat(fd).st_size
        count = None
        # A stored count is trusted only for the same size and a plausible value.
        if known_size == size and isinstance(known_count, int) and 0 <= known_count < threshold:
            count = known_count
        if count is None:
            count = len(ENTRY_RE.findall(_read_fd(fd))) if size else 0
        if count > 0 and count + 1 >= threshold:
            # One atomic rename moves the whole log into a new archive; nothing is copied.
            kumi_state.replace_at(mem, log_name, mem, archive_name(mem))
            prune_archives(mem, resolve_keep_archives(cfg))
            os.close(fd)
            fd = _open(mem, log_name, flags)
            if fd is None:
                raise OSError("refused: " + log_name)
            count, size = 0, os.fstat(fd).st_size
        if size == 0:
            count = 0
            os.write(fd, LOG_HEADER)
        os.write(fd, entry)
        return count + 1, os.fstat(fd).st_size
    finally:
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main())
