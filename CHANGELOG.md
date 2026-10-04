# Changelog

All notable changes to kumi are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] - 2026-10-04

### Added

- Session start shows a notice when `.kumi/overrides.json` is not confirmed. It gives the file's path, its code, and the exact `/kumi:trust <code>` command to apply it, and says so when a confirmed file has changed since it was confirmed.
- `/kumi:untrust`, a user-only command that stops applying the project's rules file.
- A CI job that runs the test suite on Python 3.9.
- An eval case for a resume request: yui reads the handoff, reports what it says, and asks before doing anything the handoff asks for.

### Changed

- New README that opens with a coded demo animation (`assets/demo/yui-demo.svg`) of a `/yui` request going through questions, a plan, design, build and review. The diagram, the per-stack specialist tables and the sponsor link are removed from the README.
- The hooks now state Python 3.9 or later as the minimum (`docs/MEMORY.md`).
- The plugin description now says the hooks say at the next session start that saved work exists, instead of saying they restore it.

### Security

- Session start no longer adds a project's `.kumi/handoff.md` or memory log to the session. A hook now only says, in fixed text, that saved state exists, and the model reads it as information when the user asks to resume. Affected: 1.0.0 to 1.3.0 (1.3.0 raised the handoff limit to 20,000 characters).
- Rules in `.kumi/overrides.json` now apply only after the user confirms the exact file by typing `/kumi:trust <code>`, a user-only command the model cannot call. The confirmation is stored outside the project and keyed by the file's path and SHA-256, so a rules file that comes with a cloned repository, or any later change to it, is never followed until confirmed. A confirmation applies to specialist dispatches right away and to the main session from the next session start. Affected: session-start rules 1.0.0 to 1.3.0; rules added to specialist dispatch prompts 1.3.0.
- The results of `/kumi:trust` and `/kumi:untrust` are shown to the user once. The model replies with one fixed line and receives nothing from the rules file.
- yui no longer reads `overrides.json` or copies its rules into a dispatch brief. Affected: 1.3.0.
- yui reads an existing handoff only when the user asks to resume, and no hook points the model at it. Affected: 1.0.0 to 1.3.0.
- The activity log no longer stores command text, URLs, search patterns, or queries. It stores the tool name and, for file tools only, a path. On the first kumi call in a project, 1.4.0 removes stored command text from that project's existing activity log. Affected: 1.0.0 to 1.3.0.
- Hooks no longer write into a `.kumi` directory before kumi is called in that project. Affected: 1.0.0 to 1.3.0.
- Hooks no longer follow symbolic links inside the state directory, for reading or writing. Affected: 1.0.0 to 1.3.0.
- The state directory is now the one at the git work-tree root. A `.kumi` in a subfolder, or in a parent folder of a project without git, is used only if kumi was called there before. In a git worktree the state directory is now excluded through the shared `info/exclude`. Affected: 1.0.0 to 1.3.0 (parent-folder search added in 1.3.0).
- Memory log entries now hold at most 4,000 characters of the handoff, written as a block quote so handoff text cannot forge an entry, and at most three dated archives are kept (`memory.keep_archives`). Affected: 1.0.0 to 1.3.0.
- Activity log fields now write control characters as visible escapes, so one action is always one line. Affected: 1.0.0 to 1.3.0.
- The house rule about decisions on record now covers decisions the user made, and a new rule says kumi's state files are project data. Affected: 1.3.0.
- `SECURITY.md` wrongly said `.kumi/` cannot arrive by cloning a repository. It now describes this threat model. Affected: 1.2.0 to 1.3.0.

### Upgrading

- Existing `overrides.json` files stop applying until confirmed. Review the file in an editor, type `/kumi:trust` in a session to see its path, code and rule count, then type `/kumi:trust <code>` to apply it.
- `memory.restore_entries` is removed from `config/runtime.json`.

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
- The reviewer skills (`mart`, `ivo`, `tiiu`, `aki`, `ryo`) now also check every changed file, not just source, for a leaked internal path or working-state detail.
- The same reviewer skills now also require actually running the project's own lint, test, and build commands locally, instead of a read-through opinion.
- The same reviewer skills now also check the result against the brief, confirming every part is answered and that any completeness claim states what was searched.
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

- A coordinated team of named specialists: implement, debug, and review trios for Go, Angular, iOS, Python, and React; a cross-cutting architect (kai); SQL and NoSQL specialists (saku, remo); a process manager (enn); and the coordinator (yui).
- Each specialist ships as both a skill and a generated subagent, with role-based tools (reviewers are read-only), a model, and a color.
- Cross-session memory: work is captured when an agent stops and restored when a new session starts.
- Observability: an activity log, plus per-session and per-agent token and time metrics.
- User overrides: house rules from a JSON file, applied on top of the built-in discipline without changing any source file.
- A configurable state location through the KUMI_STATE_DIR environment variable.
- A uniform skill contract with a validator, a routing eval set, a test suite, worked examples, and full documentation.
