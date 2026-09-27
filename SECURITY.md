# Security Policy

## Supported versions

kumi is pre-1.x and moving fast (`1.0.0` → `1.1.0` → `1.2.0` → `1.3.0` already, see [CHANGELOG.md](CHANGELOG.md)). Only the latest released version, as recorded in [.claude-plugin/plugin.json](.claude-plugin/plugin.json)'s `version` field, is supported. There is no version support table: at this stage, upgrading to the latest release is the fix for a reported vulnerability.

## Reporting a vulnerability

**Primary channel:** [GitHub private vulnerability reporting](https://github.com/annavetech/kumi/security/advisories/new) for this repository. This keeps the report private until a fix is ready, and is what [.github/ISSUE_TEMPLATE/config.yml](.github/ISSUE_TEMPLATE/config.yml)'s contact link points to.

**Fallback:** email **security@annave.tech** if you cannot use GitHub's reporting flow.

Do not open a public issue or pull request for a suspected vulnerability.

You should expect an acknowledgement within 5 business days. We will work with you to understand and confirm the issue, and to agree on a disclosure timeline once a fix is available.

## Scope

kumi's real attack surface is specific, not generic:

- **The hooks** (`hooks/*.py`). These run locally with filesystem access, read a configurable `KUMI_STATE_DIR`, and are invoked by Claude Code on session and tool-use events. A vulnerability here would be a way for hook input (event JSON, transcript content) to cause the hook to read, write, or execute something outside its intended `.kumi` state directory. This includes `overrides.json`, read by two hooks through the same shared loader (`kumi_state.load_overrides`): `apply_overrides.py` injects its `rule` strings verbatim as `SessionStart` context, presented as house rules the team follows; `inject_specialist_context.py` reads the same file on `PreToolUse` for a directly dispatched `Agent`/`Task` call and appends the rules scoped to `all` plus the target specialist into that call's `tool_input.prompt` via `updatedInput`, so a subagent dispatched outside the coordinator's own context also receives them. `.kumi/` is git-excluded, so this file does not arrive by cloning the repo. It is plain instruction text. It has no permissions or sandboxing effect. Anyone who can write to it can add a standing instruction for the whole team. Treat write access to it the same as write access to the project itself.
- **The generated subagents and skills** (`skills/*/SKILL.md`, `agents/*.md`). These are prompt content, not code, but still a delivery vector: if a skill's instructions could be made to follow instructions embedded in external content an agent fetches or reads (a web page, a file, issue or PR text), that is a security issue in this project's design, not just a bug.
- **The supply chain of this repository's own GitHub Actions** (`.github/workflows/`, `.github/scripts/`). Every third-party action is pinned to a full commit SHA specifically to close the class of attack where a tag is silently repointed to a malicious commit. A report that a pinned SHA does not match its claimed tag, or that a workflow's `permissions:`/`pull_request_target` usage is unsafe, belongs here.

**Accepted residual risk:** `.github/workflows/dependency-review.yml` stays on the plain `pull_request` trigger (not `pull_request_target`), because `actions/dependency-review-action` needs to diff the PR's own head manifest content, which a `pull_request_target` checkout deliberately never provides. `pull_request` carries no elevated token and checks out no privileged credential, so there is no token-exfiltration risk, but it does mean the workflow file that runs is the PR's own (editable) copy, so a PR author could in principle edit `dependency-review.yml` in the same PR to weaken or disable the check on their own change. This is a known, accepted tradeoff: the check protects against accidentally introduced vulnerable dependencies, not against a deliberately malicious PR author, and `merge-gate.yml` (which does need to be tamper-resistant) is on `pull_request_target` specifically because it doesn't have this constraint.

**Out of scope:** general Claude Code platform vulnerabilities. Report those to Anthropic directly, not here.
