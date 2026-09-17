# Development

## Setup

None. kumi is stdlib-only at runtime: clone the repo and run the suite.

To match CI's lint and coverage checks locally, install the CI-only tooling once:

```bash
python3 -m pip install -r requirements.txt
```

## Running the checks

These are the exact commands CI runs (see `.github/workflows/ci.yml`):

```bash
python3 tests/run_tests.py
ruff check hooks scripts tests evals .github/scripts
pymarkdown --config .pymarkdown.json scan -r . -e .github/pull_request_template.md
coverage run --rcfile=.coveragerc tests/run_tests.py && coverage combine && coverage report --rcfile=.coveragerc
```

`pull_request_template.md` is excluded from the Markdown lint on purpose: GitHub renders it inside the "Open a pull request" form, which already has its own title field, so the template intentionally starts at `##` rather than a redundant top-level heading.

If you have the `claude` CLI installed locally, these are the same manifest checks CI runs (see the `validate-claude-manifest` job): `.` covers `.claude-plugin/marketplace.json` and, through the self-referencing `plugins[]` entry, `plugin.json`; `./skills` and `./agents` cover every skill and agent file's frontmatter, which a run against `.` alone does not open.

```bash
claude plugin validate .
claude plugin validate ./skills
claude plugin validate ./agents
claude plugin validate . --strict
claude plugin validate ./skills --strict
claude plugin validate ./agents --strict
```

The `validate-claude-manifest` job downloads the `linux-x64` `claude` binary straight to a file and checks its sha256 against a literal pinned in the job (`CLAUDE_CODE_LINUX_X64_SHA256`) before it is ever made executable; nothing is piped to a shell. To bump `CLAUDE_CODE_VERSION`: fetch `https://downloads.claude.ai/claude-code-releases/<new version>/manifest.json`, copy `platforms.linux-x64.checksum` into `CLAUDE_CODE_LINUX_X64_SHA256`, then independently download `https://downloads.claude.ai/claude-code-releases/<new version>/linux-x64/claude` and run `sha256sum` on it to confirm the two agree before trusting either. That checksum only proves the downloaded bytes match what Anthropic published at that URL; it is not a signature.

## Adding a specialist

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/MANAGING-SPECIALISTS.md](docs/MANAGING-SPECIALISTS.md), which own this process. Do not duplicate it here.

## How repo automation works

The full design (CODEOWNERS, auto-assign, chat commands and the merge gate, size and path labels, the label taxonomy and its sync, Dependabot, dependency review, lint and coverage in CI, the stale bot, and the hold on outside contributors' CI) is specified in [.kumi/decisions/kai/repo-automation.md](.kumi/decisions/kai/repo-automation.md). Read that rather than a second summary here that can drift from the workflows themselves.

## How the CI scripts fail

`.github/scripts/*.py` split deliberately into two failure modes, named in each file's own docstring:

- **Fails closed** (`merge_gate.py`): any exception while reading the PR's event payload exits 1 with a message and posts no commit status at all, never a silent pass. This is the actual merge-blocking check (the solo-maintainer alternative to a native required review, see `.kumi/decisions/kai/repo-automation.md`), so a bug in it must never merge a PR it failed to evaluate. That is separate from the label state it reports once it can read the payload: a PR simply waiting on `lgtm`/`approved`, or held by a `do-not-merge/*` label, is not a bug, so it gets a `pending` commit status, not a failed job. See "The merge gate reports pending, not failed" below.
- **Fails open** (`chat_commands.py`, `auto_assign.py`, `needs_ok_to_test.py`): every one catches broad exceptions and exits 0 regardless, logging the error to stderr rather than failing the job. These are conveniences (labeling, assigning, chat commands), so a bug in one of them must never turn into a red, blocking check on someone's unrelated PR.

`_github.py`'s `report_if_error(context, status, body=None, ignore=())` is the shared helper behind the fail-open scripts' error visibility: earlier versions of these scripts discarded the `(status, json)` tuple from a GitHub API call, so a `403` from a misconfigured `permissions:` block failed silently. `report_if_error` prints any unexpected non-2xx status to stderr, along with GitHub's own `message` field when the response body carries one (for example "Resource not accessible by integration", which names the missing permission), skipping statuses the caller explicitly expects (like a `404` on `remove_label` for a label that's already gone) — without ever raising or failing the job itself, visible in the log, but still fail-open.

### The merge gate reports pending, not failed

`merge-gate.yml`'s job (`merge-gate-status`) always ends green once it has read the event payload and posted a status; the actual merge-blocking signal is the `merge-gate` commit status it posts to `POST /repos/{repo}/statuses/{sha}`: `pending` while `lgtm`/`approved` are missing or a `do-not-merge/*` label holds the PR, `success` once both labels are present and nothing holds it. This mirrors Prow's tide, which reports a pool's merge-readiness as a status instead of failing a check while a PR is simply waiting its turn. Branch protection's required check points at the `merge-gate` commit-status context, not at the `merge-gate-status` job's own check run — the two are named apart on purpose so they can't be confused.

## Cutting a release

1. Bump the `version` field in `.claude-plugin/plugin.json`.
2. Move `CHANGELOG.md`'s `[Unreleased]` section to a new dated `[X.Y.Z]` heading.
3. Commit.
4. `git tag vX.Y.Z`
5. Push the tag.
