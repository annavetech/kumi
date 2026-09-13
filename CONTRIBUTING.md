# Contributing to kumi

kumi is a framework, so adding a specialist is uniform and mechanical. Every skill follows the same contract, which is why the team can grow without rewriting any existing part.

## Add a specialist in 3 steps

1. **Copy the template.** Copy `template/skill-template/SKILL.md` to `skills/<name>/SKILL.md`, where `<name>` is the short, memorable name the specialist is called by. Fill in every section, do not remove or reorder them:
   - Frontmatter: `name`, a `description` written as a plain sentence of what the role does (with the words a user would actually say, so it loads at the right time), and the `metadata` block (`role`, `domain`, `when-to-use`, `hands-off-to`).
   - The fixed sections in order: Role statement, `<HARD-GATE>`, Anti-Pattern, Checklist, Process Flow, Handoff, Key Principles, Tone.

2. **Register it with the coordinator.** Add one row to the team table in `skills/yui/SKILL.md` (name, `/command`, what it handles) and, if relevant, a routing rule. This is the only place the coordinator learns about a specialist, it never hardcodes them anywhere else.

3. **Generate its subagent and run the checks.**
   ```bash
   python3 scripts/build_agents.py   # writes agents/<name>.md from your skill
   python3 tests/run_tests.py        # validator, evals, agent check, negatives
   ```
   The generator produces the subagent form so the specialist ships both ways. The test suite confirms the skill has valid frontmatter and every required section in order, that the routing eval is coherent, and that `agents/` matches the skills. A new specialist that passes is a valid specialist.

That is the whole process. You do not touch any other specialist, and you do not change the coordinator's logic, only its role table. You also do not write the subagent by hand; it is generated from the skill.

## The contract, in short

Every specialist is one of three shapes, and they stay consistent within a shape:

- **Implementers** (jaan, liis, ren): read context first, work from a spec, smallest correct change, verify with a build.
- **Debuggers** (siim, kadi, shu): reproduce first, find the root cause, touch only the broken path, verify the failure is gone.
- **Reviewers** (mart, tiiu, ryo): read-only, checklist-driven, findings ranked by severity, never edit.

Plus the **coordinator** (yui) which only routes, and cross-cutting roles like the **process manager** (enn).

When you add a new stack (say Python), the natural shape is a new implement/debug/review trio that mirrors the existing ones. That consistency is the point: someone who knows how `jaan`/`siim`/`mart` relate already knows how a new trio relates.

## Other operations

To disable, modify, remove, or rename a specialist, or to add a whole new stack, see [docs/MANAGING-SPECIALISTS.md](docs/MANAGING-SPECIALISTS.md), which has the exact steps for each. In short: edit `skills/<name>/SKILL.md`, keep the section structure intact, and run the validator before opening a change.

## Style

- No filler. The skills are terse and imperative by design.
- Keep the shared discipline: act on the request, make the smallest correct change, verify, state observations at the end rather than chasing them.
- Match the existing skills' voice; read two or three before writing a new one.
