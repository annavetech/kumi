# Memory

kumi remembers finished work so a new session does not start cold. The important idea is that memory is handled by the runtime, not by an agent remembering to save. Asking a specialist to "write a memory file when you're done" is unreliable, because a model skips that under load, especially at the end of a long task. So kumi makes it structural.

Memory is a loop with two hooks: one writes state when a session ends, the other reads it back when a session starts.

## Capturing state when an agent stops

A hook (`hooks/capture_memory.py`) fires on every `Stop` and `SubagentStop`, which is every time an agent finishes. It snapshots the current handoff and the list of decision files into an append-only log at `.kumi/memory/log.md`, under a timestamp. Because the runtime runs the hook every time, this does not depend on the model remembering anything. Even if the next session overwrites the working handoff, the history is kept.

The content itself comes from the specialists as they work. Each role writes its decisions to `.kumi/decisions/<role>/<feature-slug>.md` and the coordinator keeps `.kumi/handoff.md` current. That is the Handoff step in every skill, so it happens as part of the work. The hook then guarantees whatever they wrote is saved.

## Restoring state at the start of a session

A second hook (`hooks/restore_memory.py`) fires on `SessionStart`. It reads the most recent memory entries and the current handoff and passes them into the new session as context. So the session resumes with what the last one decided and where it left off, instead of a blank slate.

The restored context is capped in size so it never floods the session. It shows the recent entries and the current handoff, not the entire history.

## What gets written

```
.kumi/
  handoff.md                      current role-to-role context (working state)
  decisions/<role>/<slug>.md      each role's decisions (working state)
  memory/
    log.md                        append-only history, one timestamped entry per capture
    .last                         change signature, so unchanged state is not re-logged
```

`.kumi/memory/log.md` is append-only. Nothing is overwritten. Each entry lists the decisions on record and the handoff as it stood when the agent stopped.

## Why it is reliable

- The runtime fires it, not the model. `Stop`, `SubagentStop`, and `SessionStart` are runtime events, so the hooks run whether or not any instruction was followed.
- It never blocks or fails. Every hook is guarded and always exits 0. A memory system must never break the agent it serves.
- It does not spam. Capture writes only when the state changed since last time, tracked by a hash in `.kumi/memory/.last`.
- It is off unless used. If a project has no `.kumi/` directory, both hooks do nothing.

## The honest limit

The hooks guarantee that whatever state exists is captured and restored. They do not invent content. The meaning of a memory, what was decided and why, is written by the specialist during the Handoff step. If a single-role task never writes any shared state, there is nothing to capture. The safety net covers state that exists; it does not manufacture state that does not.

## Requirements

The hooks run `python3`, so Python 3 must be on `PATH`. They use only the standard library. The file names come from `config/runtime.json`, so you can rename or relocate them in one place.
