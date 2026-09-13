# Add a PHP agent

This is a full worked example of adding a new specialist, start to finish. Say you work in PHP and want a PHP implementer on the team. We will call it `pim`. The same steps work for any new specialist; only the content changes.

If you want the short version of the rules, see [MANAGING-SPECIALISTS.md](MANAGING-SPECIALISTS.md). This page walks through the actual work.

## 1. Copy the template

```bash
mkdir -p skills/pim
cp template/skill-template/SKILL.md skills/pim/SKILL.md
```

## 2. Fill in the skill

Open `skills/pim/SKILL.md` and replace every placeholder. Keep the sections and their order; the validator checks for them.

The frontmatter:

```yaml
---
name: pim
description: "Writes and edits PHP code from a spec. Send a specific bug to a debugger, a review to a reviewer."
metadata:
  role: PHP Implementer
  domain: PHP
  when-to-use: A PHP feature or change needs to be written or edited from a clear spec.
  hands-off-to: [mart]
---
```

Then the body. A PHP implementer is the same shape as the other implementers (`jaan`, `eero`, `noa`), so the quickest way is to open one of those and follow its structure: a one-line role statement, a hard gate that says read before you write, an anti-pattern, an ordered checklist ending in "run the linter and tests", a process flow, a handoff, key principles, and tone. Change the details to PHP (Composer, PSR standards, PHPUnit, `phpstan`), not the shape.

The hard gate, for example:

```markdown
<HARD-GATE>
Do not write any code until you have read the relevant existing files, identified the conventions already in use, and understood exactly what the task requires. This applies to every change, however simple it looks. Code written without reading the surrounding context is inconsistent and buggy.
</HARD-GATE>
```

## 3. Register it with the coordinator

Open `skills/yui/SKILL.md`. Add one row to the team table:

```markdown
| pim  | `/pim`  | PHP implementation, write and edit PHP features |
```

And a routing rule under "Routing rules":

```markdown
- New PHP feature -> `pim`.
```

That is the only place the coordinator needs to change. It does not hardcode `pim` anywhere else.

## 4. Add an eval case

Open `evals/cases.yaml` and add a case so the routing is covered:

```yaml
  - prompt: "add a PHP endpoint that validates the request and returns JSON"
    expect: pim
    why: writing a new PHP feature
```

## 5. Add it to the roster

Add a row to the table in `skills/README.md` and the "Meet the team" table in `README.md`, matching the existing rows.

## 6. Generate the subagent and run the checks

```bash
python3 scripts/build_agents.py      # creates agents/pim.md from your skill
python3 tests/run_tests.py           # validates the skill, evals, agents, hooks
```

If the suite is green, `pim` is a real specialist: it validates, it routes, and it exists as both a skill (`/pim`) and a subagent. If something fails, the output names exactly what is wrong (a missing section, an out-of-order heading, an eval pointing at a name that does not exist), so you fix that and run it again.

## What you did not have to do

You did not touch any other specialist. You did not change the coordinator's logic, only its table. You did not write the subagent by hand; it was generated from your skill. That is the point of the uniform contract: adding a specialist is filling in a known shape, not wiring up a new system.
