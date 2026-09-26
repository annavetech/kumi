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

The `validate-claude-manifest` job installs `claude` from npm with `npm ci` in `.github/claude-cli`. The integrity hashes in `package-lock.json` pin the exact package and its native binary. Install scripts stay enabled because the package's postinstall step places the native binary. To bump the version, edit `package.json` in that folder and regenerate `package-lock.json`, or merge the Dependabot pull request that does both.

## Adding a specialist

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/MANAGING-SPECIALISTS.md](docs/MANAGING-SPECIALISTS.md), which own this process. Do not duplicate it here.

## How repo automation works

The full design (CODEOWNERS, auto-assign, chat commands and the merge gate, size and path labels, the label taxonomy and its sync, Dependabot, dependency review, lint and coverage in CI, the stale bot, and the hold on outside contributors' CI) lives in the workflow and script files under `.github/`. Read those rather than a second summary here that can drift from the workflows themselves.

## How the CI scripts fail

`.github/scripts/*.py` split deliberately into two failure modes, named in each file's own docstring:

- **Fails closed** (`merge_gate.py`, `strip_stale_approval.py`): any exception while reading the PR's event payload exits 1 with a message and posts no commit status at all, never a silent pass. This is the actual merge-blocking check (the solo-maintainer alternative to a native required review), so a bug in it must never merge a PR it failed to evaluate. `strip_stale_approval.py` fails the same way for the same reason: it exists to keep the gate honest about approval state after a new commit, so a bug in it must never leave a stale `success` status after the labels have changed. That is separate from the label state it reports once it can read the payload: a PR simply waiting on `lgtm`/`approved`, or held by a `do-not-merge/*` label, is not a bug, so it gets a `pending` commit status, not a failed job. See "The merge gate reports pending, not failed" below.
- **Fails open** (`chat_commands.py`, `auto_assign.py`, `needs_ok_to_test.py`): every one catches broad exceptions and exits 0 regardless, logging the error to stderr rather than failing the job. These are conveniences (labeling, assigning, chat commands), so a bug in one of them must never turn into a red, blocking check on someone's unrelated PR.

`_github.py`'s `report_if_error(context, status, body=None, ignore=())` is the shared helper behind the fail-open scripts' error visibility: earlier versions of these scripts discarded the `(status, json)` tuple from a GitHub API call, so a `403` from a misconfigured `permissions:` block failed silently. `report_if_error` prints any unexpected non-2xx status to stderr, along with GitHub's own `message` field when the response body carries one (for example "Resource not accessible by integration", which names the missing permission), skipping statuses the caller explicitly expects (like a `404` on `remove_label` for a label that's already gone), without ever raising or failing the job itself, visible in the log, but still fail-open.

### The merge gate reports pending, not failed

`merge-gate.yml`'s job (`merge-gate-status`) always ends green once it has read the event payload and posted a status; the actual merge-blocking signal is the `merge-gate` commit status it posts to `POST /repos/{repo}/statuses/{sha}`: `pending` while `lgtm`/`approved` are missing or a `do-not-merge/*` label holds the PR, `success` once both labels are present and nothing holds it. This mirrors Prow's tide, which reports a pool's merge-readiness as a status instead of failing a check while a PR is simply waiting its turn. Branch protection's required check points at the `merge-gate` commit-status context, not at the `merge-gate-status` job's own check run. The two are named apart on purpose so they can't be confused.

## Cutting a release

1. Bump the `version` field in `.claude-plugin/plugin.json`.
2. Move `CHANGELOG.md`'s `[Unreleased]` section to a new dated `[X.Y.Z]` heading.
3. Commit.
4. `git tag vX.Y.Z`
5. Push the tag.
