# Anatomy of the package

This is the full picture of what kumi is made of: what defines a single specialist, and what makes up the whole plugin. Read this if you want to understand the structure before you change or extend it.

## What defines one specialist

A specialist is referenced in a small, fixed set of places. Nothing about it is hidden anywhere else.

1. `skills/<name>/SKILL.md`, the specialist itself. This is the source of truth. Its frontmatter carries the `name`, a trigger-oriented `description`, and a `metadata` block (`role`, `domain`, `when-to-use`, `hands-off-to`). Its body carries the fixed sections in order: the role statement, a hard gate, an anti-pattern, a checklist, a process flow, a handoff, key principles, and tone.
2. `agents/<name>.md`, the subagent version, generated from the skill by `scripts/build_agents.py`. You do not edit this by hand; you edit the skill and regenerate. The coordinator (`yui`) is the one specialist with no subagent version, because a subagent cannot dispatch other subagents.
3. One row in the team table in `skills/yui/SKILL.md`, plus a routing rule. This is the only place the coordinator learns a specialist exists.
4. One or more cases in `evals/cases.yaml` that route to it.
5. A row in the roster tables in `skills/README.md` and `README.md`.

That is the whole footprint. Add those and a specialist exists; remove them and it is gone.

## What makes up the whole plugin

```
.claude-plugin/
  plugin.json          the plugin manifest (name, version, description)
  marketplace.json     lets the repo install as its own marketplace

skills/                the specialists, one folder each, plus a README roster
  yui/SKILL.md         the coordinator
  jaan/ siim/ ...      the rest of the team

agents/                subagent versions, generated from skills/

hooks/                 the runtime behaviour
  hooks.json           registers the hooks on their events
  kumi_state.py        shared helper that reads config/runtime.json
  capture_memory.py    writes finished work to memory (Stop, SubagentStop)
  restore_memory.py    reads memory back into a new session (SessionStart)
  log_activity.py      logs each tool action (PostToolUse)
  record_metrics.py    records token and time usage (Stop, SubagentStop)

config/
  contract.json        the rules for a valid skill (read by the validator)
  runtime.json         the names and layout of the .kumi state files

evals/
  cases.yaml           the routing set: which prompt should reach which specialist
  check_cases.py       structural check that the set stays coherent
  README.md            how the evals work

examples/              worked transcripts of the team in use
template/              the scaffold to copy when adding a specialist
scripts/build_agents.py  generates agents/ from skills/
tests/
  validate_skills.py   checks every skill against the contract
  run_tests.py         the full suite, including negative cases

docs/                  ARCHITECTURE, DIAGRAMS, MANAGING-SPECIALISTS, MEMORY,
                       ANATOMY (this file), and a README
CHANGELOG.md  CONTRIBUTING.md  CODE_OF_CONDUCT.md  LICENSE  README.md
```

## The .kumi working state

None of the above is written into the plugin at runtime. When the team works on a project, it keeps its shared state under `.kumi/` in that project (gitignored):

```
.kumi/
  status.md            phase tracking
  handoff.md           the current role-to-role context
  decisions/<role>/    each role's decisions, one file per feature
  memory/log.md        append-only history, written when an agent stops
  logs/activity.log    one line per tool action
  metrics/             token and time usage, per session and per agent
```

The plugin ships the behaviour; the `.kumi` directory holds what that behaviour produces in your project. The names of these files all come from `config/runtime.json`, so you can change them in one place.

## How the pieces relate

- The **skill** is the source of truth for a specialist. The **agent** is generated from it. The **validator** and **contract** decide whether a skill is well-formed. The **evals** decide whether it routes. The **hooks** and **config** decide what happens while the team works and how its memory survives between sessions. The **docs** explain all of it.
- Change a specialist by editing its skill and running `scripts/build_agents.py` and `tests/run_tests.py`. Everything else follows from those.
