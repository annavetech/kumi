# Managing specialists

Everything you do to change the team: add one, turn one off, edit one, remove one, rename one, or add a whole new stack. Every operation touches the same few places, because the team is uniform, there is no hidden wiring.

## The three places a specialist lives

Before the operations, know the only places a specialist is referenced. Nothing else needs touching, ever.

1. **Its skill folder**, `skills/<name>/SKILL.md`. This is the specialist itself.
2. **The coordinator's role table**, one row in `skills/yui/SKILL.md`. This is the only place `yui` learns a specialist exists.
3. **The evals**, optionally, cases in `evals/cases.yaml` that route to it.

Documentation (`skills/README.md`, `README.md`) lists the roster for readers, so update it too when the roster changes, but it is prose, not wiring.

There is also a fourth, generated place: `agents/<name>.md`, the subagent form. You never edit it by hand. It is produced from the skill by `scripts/build_agents.py`, so after changing a skill you regenerate it. When you remove or rename a specialist, delete its old `agents/<name>.md` yourself, because the generator writes files but does not delete them.

After any change, regenerate the subagents and run the suite:

```bash
python3 scripts/build_agents.py   # sync agents/ with skills/
python3 tests/run_tests.py        # validator, evals, agent check, negatives
```

---

## Add a new specialist

1. Copy `template/skill-template/SKILL.md` to `skills/<name>/SKILL.md`, where `<name>` is the short name it is called by. Fill every section, in order: frontmatter (`name`, a trigger-oriented `description`, and the `metadata` block: `role`, `domain`, `when-to-use`, `hands-off-to`), then Role statement, `<HARD-GATE>`, Anti-Pattern, Checklist, Process Flow, Handoff, Key Principles, Tone.
2. Add one row to the team table in `skills/yui/SKILL.md` (name, `/command`, what it handles). Add a routing rule if the domain overlaps another specialist.
3. Add at least one case to `evals/cases.yaml` (prompt, `expect: <name>`, why).
4. Add the row to the roster in `skills/README.md` and the "Meet the team" table in `README.md`.
5. Run both checks.

That is the whole process. You do not touch any other specialist and you do not change the coordinator's logic, only its table.

## Disable a specialist (turn it off without deleting it)

There is no per-skill on/off flag; a specialist is active because its folder and its role-table row exist. To turn one off while keeping the work:

1. Move its folder out of `skills/`, for example to a `disabled/` folder at the plugin root (not under `skills/`, so the loader and validator ignore it). Do not leave it under `skills/`.
2. Remove its row from the team table in `skills/yui/SKILL.md`, so the coordinator stops routing to it.
3. Remove or comment out its cases in `evals/cases.yaml` (an `expect` pointing at a missing skill fails the check, which is exactly the check doing its job).
4. Remove it from the roster tables in `skills/README.md` and `README.md`.
5. Run both checks.

To turn it back on, reverse the steps: move the folder back under `skills/`, restore the row, restore the cases.

To disable the **entire** plugin (as an end user, not an author), use Claude Code:

```bash
claude plugin disable kumi
```

## Modify an existing specialist

1. Edit its `skills/<name>/SKILL.md`. Keep the section structure intact, same sections, same order. Change the wording, the checklist, the gate, whatever the specialist needs.
2. If you changed what it handles, update its row in the coordinator's team table and any affected routing rule, and update its eval cases so they still describe real triggers.
3. Run both checks.

Changing behaviour never requires touching another specialist. If a change makes two specialists overlap, the fix is a routing rule in `yui`, not a change to the other specialist.

## Remove a specialist permanently

1. Delete its folder `skills/<name>/`.
2. Delete its row from the team table in `skills/yui/SKILL.md`.
3. Delete its cases from `evals/cases.yaml`.
4. Delete its row from the roster in `skills/README.md` and `README.md`.
5. Run both checks, a leftover reference to the deleted name is exactly what they catch.

## Rename a specialist

A rename is a remove-and-add that keeps the content:

1. Rename the folder `skills/<old>/` to `skills/<new>/` and update the `name` in its frontmatter.
2. Update its row in the coordinator's team table (name and `/command`).
3. Update every reference: `hands-off-to` fields in other skills that named it, its eval cases (`expect`), and the roster tables in `skills/README.md` and `README.md`.
4. Run both checks to confirm nothing still points at the old name.

## Add a whole new stack

Adding a language or platform (say Python) is adding a trio of the standard shapes, mirroring an existing stack:

1. Add an implementer, a debugger, and a reviewer, each with the "Add a new specialist" steps above. Model them on an existing trio (for Go: `jaan` / `siim` / `mart`) so the shapes stay consistent.
2. Give them the natural handoffs: implementer and debugger `hands-off-to` the reviewer; the reviewer's findings go back to them.
3. Add their three rows to the coordinator's table, grouped as a stack, plus a routing rule for the new domain.
4. Add eval cases for each, and update the roster tables and the diagrams in `docs/DIAGRAMS.md` if you want the new stack drawn.
5. Run both checks.

Because every stack is the same three shapes, someone who understands one stack already understands the new one, which is the whole reason the team stays coherent as it grows.
