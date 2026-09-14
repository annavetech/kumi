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

## Adding a specialist

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/MANAGING-SPECIALISTS.md](docs/MANAGING-SPECIALISTS.md), which own this process. Do not duplicate it here.

## How repo automation works

The full design (CODEOWNERS, auto-assign, chat commands and the merge gate, size and path labels, the label taxonomy and its sync, Dependabot, dependency review, lint and coverage in CI, the stale bot, and the hold on outside contributors' CI) is specified in [.kumi/decisions/kai/repo-automation.md](.kumi/decisions/kai/repo-automation.md). Read that rather than a second summary here that can drift from the workflows themselves.

## Cutting a release

1. Bump the `version` field in `.claude-plugin/plugin.json`.
2. Move `CHANGELOG.md`'s `[Unreleased]` section to a new dated `[X.Y.Z]` heading.
3. Commit.
4. `git tag vX.Y.Z`
5. Push the tag.
