# Security Policy

## Supported versions

kumi moves fast (`1.0.0` → `1.1.0` → `1.2.0` → `1.3.0` → `1.4.0` so far, see [CHANGELOG.md](CHANGELOG.md)). Only the latest released version, as recorded in [.claude-plugin/plugin.json](.claude-plugin/plugin.json)'s `version` field, is supported. There is no version support table: at this stage, upgrading to the latest release is the fix for a reported vulnerability.

## Reporting a vulnerability

**Primary channel:** [GitHub private vulnerability reporting](https://github.com/annavetech/kumi/security/advisories/new) for this repository. This keeps the report private until a fix is ready, and is what [.github/ISSUE_TEMPLATE/config.yml](.github/ISSUE_TEMPLATE/config.yml)'s contact link points to.

**Fallback:** email **security@annave.tech** if you cannot use GitHub's reporting flow.

Do not open a public issue or pull request for a suspected vulnerability.

You should expect an acknowledgement within 5 business days. We will work with you to understand and confirm the issue, and to agree on a disclosure timeline once a fix is available.

## Scope

kumi's real attack surface is specific, not generic:

- **The hooks** (`hooks/*.py`). They run locally on Claude Code session and tool events. A repository can ship a `.kumi/` directory: `.git/info/exclude` is local to each clone, so it does not stop that. kumi therefore treats every file in the state directory as project data that may have come with the repository:
  - No hook adds the handoff, the memory log, the status file, or decision files to a session. At session start a hook only says, in fixed text, that such files exist.
  - `overrides.json` rules apply only after the user confirms the exact file content by typing `/kumi:trust <code>`, where the code is 32 to 64 hex characters of the file's SHA-256. The command cannot be called by the model, and a hook that fires only on a user-typed command records the confirmation outside the project, in the plugin's data directory, keyed by the file's resolved path and its SHA-256. Any change to the file needs a new confirmation. Until then the rules are not shown to the model.
  - Hooks write logs, memory, and metrics only into a state directory the user has enabled by calling kumi in that project. That record is also kept outside the project.
  - Hooks do not follow a symbolic link inside the state directory, for reading or for writing. On platforms without `O_NOFOLLOW` and directory file descriptors (Windows), each path component is checked for a link before it is opened, which leaves a short race, and the owner and mode of the plugin's data directory are not checked.
  - The activity log stores the time, a short session id, the tool name, and, for file tools only, a file path. It never stores command text, URLs, search patterns, or queries.

  A vulnerability here is a way for repository content, hook input, or transcript content to reach a session as instructions without the user's confirmation, or to make a hook read or write outside the state directory or the plugin's data directory.
- **The generated subagents and skills** (`skills/*/SKILL.md`, `agents/*.md`). These are prompt content, not code, but still a delivery vector: if a skill's instructions could be made to follow instructions embedded in external content an agent fetches or reads (a web page, a file, issue or PR text), that is a security issue in this project's design, not just a bug.
- **The supply chain of this repository's own GitHub Actions** (`.github/workflows/`, `.github/scripts/`). Every third-party action is pinned to a full commit SHA specifically to close the class of attack where a tag is silently repointed to a malicious commit. A report that a pinned SHA does not match its claimed tag, or that a workflow's `permissions:`/`pull_request_target` usage is unsafe, belongs here.

**Accepted residual risk:** `.github/workflows/dependency-review.yml` stays on the plain `pull_request` trigger (not `pull_request_target`), because `actions/dependency-review-action` needs to diff the PR's own head manifest content, which a `pull_request_target` checkout deliberately never provides. `pull_request` carries no elevated token and checks out no privileged credential, so there is no token-exfiltration risk, but it does mean the workflow file that runs is the PR's own (editable) copy, so a PR author could in principle edit `dependency-review.yml` in the same PR to weaken or disable the check on their own change. This is a known, accepted tradeoff: the check protects against accidentally introduced vulnerable dependencies, not against a deliberately malicious PR author, and `merge-gate.yml` (which does need to be tamper-resistant) is on `pull_request_target` specifically because it doesn't have this constraint.

**Accepted residual risk:** the model can write a trust record for `overrides.json` directly into the plugin's data directory, because hooks and the model's tools run as the same operating-system user; Claude Code's permission prompt for writes outside the project is the check.

**Out of scope:** general Claude Code platform vulnerabilities. Report those to Anthropic directly, not here. Also out of scope: Claude Code's own project settings (`.claude/settings.json`), which can define hooks and environment for a session. That trust boundary belongs to Claude Code.
