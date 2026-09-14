## What does this change do?

<!-- One or two sentences: what changed and why. -->

## Related issue

Closes #

## Type of change

- [ ] Bug fix
- [ ] New specialist / new stack trio
- [ ] Change to an existing specialist
- [ ] Documentation
- [ ] CI / repo automation
- [ ] Other (describe above)

## Checklist

- [ ] `python3 scripts/build_agents.py` run and `agents/` matches `skills/` (only if a skill changed)
- [ ] `python3 tests/run_tests.py` passes locally
- [ ] `ruff check` and the Markdown lint pass locally (see DEVELOPMENT.md)
- [ ] Roster docs updated if a specialist was added, removed, or renamed (`skills/README.md`, root `README.md`, `skills/yui/SKILL.md`)
- [ ] `CHANGELOG.md` updated under `[Unreleased]`

## Security

- [ ] This change does not introduce a way for external content (fetched pages, files, issue/PR text) to be treated as instructions by an agent.

By submitting this pull request, I confirm my contribution is made under the
terms of the MIT license (see [LICENSE](../LICENSE)), and that I have read
[CONTRIBUTING.md](../CONTRIBUTING.md).

Found a security issue instead of a bug? Do not open a public PR — see
[SECURITY.md](../SECURITY.md).
