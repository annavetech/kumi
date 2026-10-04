# Memory

kumi remembers finished work so a new session does not start cold. The important idea is that memory is handled by the runtime, not by an agent remembering to save. Asking a specialist to "write a memory file when you're done" is unreliable, because a model skips that under load, especially at the end of a long task. So kumi makes it structural.

Memory is a loop with two hooks: one writes state when a session ends, the other says at the next session start that saved state exists.

## Capturing state when an agent stops

A hook (`hooks/capture_memory.py`) fires on every `Stop` and `SubagentStop`, which is every time an agent finishes. It snapshots the current handoff and the list of decision files into an append-only log at `.kumi/memory/log.md`, under a timestamp. It writes only into a state directory the user has enabled by calling kumi in the project. Because the runtime runs the hook every time, this does not depend on the model remembering anything. Even if the next session overwrites the working handoff, the earlier one stays in the log, within the retention limits below.

The content itself comes from the specialists as they work. Each role writes its decisions to `.kumi/decisions/<role>/<feature-slug>.md` and the coordinator keeps `.kumi/handoff.md` current. That is the Handoff step in every skill, so it happens as part of the work. The hook then guarantees whatever they wrote is saved.

## Saved state at the start of a session

A second hook (`hooks/restore_memory.py`) fires on `SessionStart`. It reads no file content. If the state directory holds a handoff or a memory log, it says so in fixed text, and tells the model that this is project data that may have come with the repository. When the user asks to resume earlier work, the handoff is read then, as information to report, not as instructions.

## What gets written

```
.kumi/
  handoff.md                      current role-to-role context (working state)
  decisions/<role>/<slug>.md      each role's decisions (working state)
  memory/
    log.md                        append-only history, one timestamped entry per capture
    .last                         change signature, so unchanged state is not re-logged
```

`.kumi/memory/log.md` is append-only. Each entry starts with a `## YYYY-MM-DD HH:MM:SS` heading, lists the decision files present (at most 200 names of up to 200 characters each, then a count of the rest), and holds the first 4,000 characters of the handoff as it stood when the agent stopped. The handoff is written as a block quote, so no handoff line can look like an entry heading. A longer handoff ends with a note giving its full length.

Once the log is about to reach the configured entry threshold (`memory.rotate_entries` in `config/runtime.json`, default 250), capture rotates it: `log.md` is renamed in one step to a new archive, `memory/log.<date>-<HHMMSS>.md` (with `-1`, `-2` added if that name is taken), and a fresh `log.md` starts with the new entry. After a rotation only the newest dated archives are kept (`memory.keep_archives`, default 3; 0 keeps none). In the worst case, with 200 long decision names and a full 4,000-character handoff in every entry, an entry is under 50,000 characters, so the active log stays under about 12.5 million characters. Each archive is one former active log, so a project's memory stays under about 50 million characters with the default of three archives. Entries with few decision files and a short handoff are a few thousand characters.

## Why it is reliable

- The runtime fires it, not the model. `Stop`, `SubagentStop`, and `SessionStart` are runtime events, so the hooks run whether or not any instruction was followed.
- It never blocks or fails. Every hook is guarded and always exits 0. A memory system must never break the agent it serves.
- It does not spam. Capture writes only when the state changed since last time, tracked by a hash in `.kumi/memory/.last`.
- It is off unless used. The `.kumi/` directory is created the first time kumi is called in a project (`hooks/ensure_state.py`, on a `/kumi:` command, a kumi skill, or a kumi subagent, via `UserPromptSubmit`, `UserPromptExpansion`, or `PreToolUse`). That call also records, outside the project in the plugin's data directory, that the state directory is enabled. Until then, capture writes nothing, even into a `.kumi/` that came with a repository.

## The honest limit

The hooks guarantee that whatever state exists is captured, and that a new session is told it exists. They do not invent content. The meaning of a memory, what was decided and why, is written by the specialist during the Handoff step. If a single-role task never writes any shared state, there is nothing to capture. The safety net covers state that exists; it does not manufacture state that does not.

## Requirements

The hooks run `python3`, so Python 3.9 or later must be on `PATH`. They use only the standard library. The file names come from `config/runtime.json`, so you can rename or relocate them in one place.
