# Changelog

All notable changes to kumi are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-09-27

- Added a plugin icon (`assets/brand/kumi-mark.svg`) to `plugin.json`.
- Removed `assets/brand/favicon.ico`.
- CI now installs the `claude` CLI from npm, pinned to an exact version by a lockfile in `.github/claude-cli/`. The pinned version is now 2.1.283, which recognises the `icon` field.
- Dependabot now opens update pull requests for the pinned `claude` CLI.
- Fixed: `restore_memory.py` could split memory entries on any level-2 heading and could silently truncate a long handoff mid-sentence.
- `capture_memory.py` now rotates `.kumi/memory/log.md` into a dated archive once it passes the configurable `memory.rotate_entries` threshold, instead of letting the log grow forever.
- Fixed: kumi called from a subdirectory could nest a new `.kumi` directory instead of anchoring to the existing one at the repository root.
- Added `config/house_rules.md`, kumi's own shared behavior rules, now baked into every generated specialist agent.
- Specialist skills now ask a specific question when something is unclear, instead of describing themselves as waiting for a go-ahead they have no channel to receive.
- Fixed: `yui`'s own instructions told it not to verify a specialist's work; it now checks that a specialist's required steps were actually run and reported.
- Added `hooks/inject_specialist_context.py`, a hook that delivers scoped project rules into a directly-dispatched specialist's prompt.
- A specialist dispatch now requires a brief with `Goal:`, `Output format:`, `Where to look:`, and `Limits:`; an incomplete brief is denied back to the coordinator.
- The five reviewer skills (`mart`, `ivo`, `tiiu`, `aki`, `ryo`) now also check every changed file, not just source, for a leaked internal path or working-state detail.
- The same five reviewer skills now also require actually running the project's own lint, test, and build commands locally, instead of a read-through opinion.
- The same five reviewer skills now also check the result against the brief, confirming every part is answered and that any completeness claim states what was searched.
- Fixed: `scripts/build_agents.py` hardcoded `model: sonnet` for every generated specialist; the model now comes from `config/runtime.json`'s `model` section, with a project-wide default and per-specialist overrides.
- Added eval cases in `evals/cases.yaml` covering direct yes/no answers, scoped approvals, multi-part requests, completeness claims, and other recorded behavior regressions.

## [1.2.0] - 2026-09-21

- Added sora, a DevOps specialist for containers, CI/CD, infrastructure as code and deploys.
- Added repository automation: code owners, auto-assign, chat commands (`/lgtm`, `/approve`, `/hold`, `/unhold`, `/ok-to-test`), a label taxonomy with sync, and security settings for outside contributors.
- Fixed: the `approved` label's description was too long for label sync to apply.
- Added the kumi logo, brand assets, and a sponsor link.
- enn's kill commands now list the target and confirm before sending a signal, instead of piping straight into `kill -9` or `pkill -f`.
- `claude plugin validate` (and `--strict`) now runs in CI, pinned to an exact, checksum-verified CLI version.
- Documented the CI scripts: the fail-open vs fail-closed split, and where `report_if_error` comes from.
- The merge gate now reports a pending commit status while waiting on labels, instead of failing the check.
- Fixed: `/lgtm` and `/approve` could not add labels or react to a comment (the chat-ops workflow was missing `pull-requests: write`), and API errors now show GitHub's own error message.
- Automation no longer posts emoji reactions or emoji summary comments on pull requests.
- `yui` now asks a clarifying question when a request is vague, and explains the plan in plain language before dispatching.
- The README now opens with a one-line call to action, followed by a short "See it work" example placed before the specialist roster.
- Added two more worked examples: asking for something in plain words, and handing over a whole feature that's already scoped across two stacks.
- The README now states which stacks kumi covers today, and that the roster can be extended.
- The specialist roster is now framed as reference material you can read later, not something you need before calling `/yui`.
- Fixed: the merge gate could deadlock after a `/lgtm` or `/approve` comment, because GitHub never re-triggers a workflow from a label change made by its own token; chat-ops now posts the `merge-gate` status itself right after it changes a label. A new commit pushed to an approved PR now strips the `lgtm` and `approved` labels and posts the corrected status itself, so re-approval always covers everything currently on the branch, not just the newest push.
- Documented `overrides.json` in `SECURITY.md`'s scope: its `rule` strings are injected verbatim as `SessionStart` context, so write access to it is the same as write access to the project.
- Eval cases can now carry `must`/`must_not` behavior assertions alongside routing, so a grader (a human today, `claude plugin eval` once wired in) can check a transcript's behavior, not just which specialist fired.
- Documented that disabling, uninstalling, or reinstalling kumi never touches a project's `.kumi` directory; it stays in place and stays readable either way.
- Fixed: agent metrics recorded every specialist as `unknown` in `.kumi/metrics/agents.jsonl`, because `record_metrics.py` looked for the name in the subagent's own transcript, where it never appears. It now reads `agent_type` from the SubagentStop hook payload and strips the `kumi:` prefix, so agent metrics record the real specialist name instead of `unknown`.

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
