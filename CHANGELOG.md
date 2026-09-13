# Changelog

All notable changes to kumi are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-09-14

- The `.kumi` state directory is now created automatically the first time kumi is called in a project (a `/kumi:` command, a kumi skill, or a kumi subagent), through a new `hooks/ensure_state.py` hook on `UserPromptSubmit`, `UserPromptExpansion`, and `PreToolUse`. Previously nothing created it, so a project's memory, logging, and metrics hooks stayed silent until someone made the directory by hand.
- The state directory is kept out of git through `.git/info/exclude`, added once and never touching the project's own `.gitignore`.
- Fixed: `capture_memory.py`, `restore_memory.py`, `log_activity.py`, `record_metrics.py`, and `apply_overrides.py` no longer crash when a hook's input has a malformed `cwd` (a non-string type, or an empty string); each now falls back to the real working directory and always exits 0.

## [1.0.0] - 2026-09-13

The first release.

- A coordinated team of 20 named specialists: implement, debug, and review trios for Go, Angular, iOS, Python, and React; a cross-cutting architect (kai); SQL and NoSQL specialists (saku, remo); a process manager (enn); and the coordinator (yui).
- Each specialist ships as both a skill and a generated subagent, with role-based tools (reviewers are read-only), a model, and a color.
- Cross-session memory: work is captured when an agent stops and restored when a new session starts.
- Observability: an activity log, plus per-session and per-agent token and time metrics.
- User overrides: house rules from a JSON file, applied on top of the built-in discipline without changing any source file.
- A configurable state location through the KUMI_STATE_DIR environment variable.
- A uniform skill contract with a validator, a routing eval set, a test suite, worked examples, and full documentation.
