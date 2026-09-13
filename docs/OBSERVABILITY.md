# Logging and metrics

kumi can show you what the team did in a project and what it cost. Two hooks handle this, writing into the `.kumi` directory that is created the first time kumi is called in a project (a `/kumi:` command, a kumi skill, or a kumi subagent). In a project where kumi was never called, both stay silent and write nothing.

## Activity log

A `PostToolUse` hook (`hooks/log_activity.py`) appends one line per tool action to `.kumi/logs/activity.log`:

```
2026-09-13 12:32:49	abc12345	Edit	/path/to/file.go
```

Each line has the time, a short session id, the tool, and a short target (the file, command, or query it acted on). This is the record of what happened, in order.

A note on attribution. When a specialist runs as a **skill**, it runs inside the main session, and the runtime does not tell a hook which skill is active. So the activity log is session-level, not per-skill. When a specialist runs as a **subagent**, its work is separated, and the metrics below attribute token and time usage to it by name.

## Metrics

A hook on `Stop` and `SubagentStop` (`hooks/record_metrics.py`) reads the finished run's transcript and records its token and time usage.

- On `Stop` it records the whole session to `.kumi/metrics/sessions.jsonl`.
- On `SubagentStop` it records that single subagent run to `.kumi/metrics/agents.jsonl`, tagged with the agent name when the transcript exposes it.

Each record is one line in the file (JSONL). Expanded for readability, a record looks like:

```json
{
  "when": "2026-09-13T10:00:30Z",
  "session": "abc12345",
  "tokens": {
    "input_tokens": 300,
    "output_tokens": 130,
    "cache_read_input_tokens": 10,
    "cache_creation_input_tokens": 0
  },
  "duration_seconds": 30,
  "agent": "jaan"
}
```

Per-agent token and time metrics are possible only for subagents, because a subagent has its own transcript to measure and a skill does not. This is why kumi ships each specialist both ways: run it as a skill for a quick call, or as a subagent when you want its work measured on its own.

The token numbers and timestamps are read defensively. Transcript shapes vary between versions, so any usage fields and timestamps found are summed and bracketed, and anything missing is left out rather than guessed.

## It never gets in the way

Both hooks always exit cleanly and never raise, even on malformed input. An observability hook that could fail the agent it is watching would not be worth having. Before the first kumi call in a project creates the `.kumi` directory, both hooks find nothing to write into and do nothing.

## Where the file names come from

The paths and file names (`logs/activity.log`, `metrics/sessions.jsonl`, `metrics/agents.jsonl`) are defined in `config/runtime.json`. Change them there and the hooks follow, with no code edit.
