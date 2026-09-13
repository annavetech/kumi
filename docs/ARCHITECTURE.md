# kumi architecture

kumi is designed as a small framework, not a collection of independent prompts. The design goal is a uniform, extensible team: easy to learn (every part is the same shape), easy to extend (adding a part is mechanical), and easy to use (one coordinator, or any specialist by name).

## The design principle

kumi is built like a plugin system. Every specialist conforms to one interface, the same skill contract. The coordinator dispatches to them without knowing anything specific about any one of them, because it only knows a role table. This keeps the parts interchangeable and lets the set grow without any existing part being rewritten:

- **One contract, many specialists.** Each specialist is a skill that follows the same fixed shape, so they are uniform and any one can be read to understand all of them.
- **A dispatcher that knows nothing specific.** The coordinator routes by a role table alone. Adding a specialist is adding a row; the coordinator's own logic never changes.
- **One shared format between them.** Specialists never read each other's internals. They pass context through one convention under `.kumi/`, so any role can consume any other role's output.
- **Extension is mechanical.** Adding a specialist means copying a template, filling in the sections, adding a row, and running the validator. It is never a rewrite.

## The four pillars

### 1. The uniform skill contract

Every specialist `SKILL.md` has the same shape, in a fixed order:

- **Frontmatter**: `name`, a trigger-oriented `description`, and a `metadata` block (`role`, `domain`, `when-to-use`, `hands-off-to`).
- **Sections**, in this order: Role statement, `<HARD-GATE>`, Anti-Pattern, Checklist, Process Flow, Handoff, Key Principles, Tone.

Because the shape never varies, reading one skill teaches all of them. The `template/skill-template/SKILL.md` is the canonical form; `tests/validate_skills.py` enforces it.

### 2. The coordinator as a uniform dispatcher

`yui` holds a single role table (name, command, what each handles) and dispatches by it. It never implements, debugs, or reviews. Adding a specialist means adding one row to that table. The coordinator's own logic never changes.

### 3. Uniform shared state

Every specialist reads and writes through one convention under `.kumi/` in the working project:

- `status.md` for phase tracking
- `handoff.md` for the current role-to-role context
- `decisions/<role>/<feature-slug>.md` for each role's decisions

Because the format is identical for every role, any role can consume any other role's output. So the team behaves as a system, not a set of disconnected skills. It is optional for single-role tasks and used only for multi-step work.

This state is also made durable. A bundled hook (`hooks/capture_memory.py`) fires on `Stop` and `SubagentStop` and appends the current handoff and decisions to an append-only `.kumi/memory/log.md`. Capture is driven by the runtime, not by a specialist remembering to save, so it is guaranteed rather than best-effort. See [MEMORY.md](MEMORY.md).

### 4. The extension mechanism

Three artifacts make adding a specialist mechanical and safe:

- `template/skill-template/SKILL.md` is the scaffold to copy.
- `CONTRIBUTING.md` is the "add a specialist in 3 steps" guide.
- `tests/validate_skills.py` is a validator that checks any skill conforms (frontmatter present, required sections present and in order). It is the single source of truth for "is this a valid skill", so conformance is mechanical, not a judgment call.

## Skills and subagents

Each specialist ships two ways. As a skill it runs inside the session you invoke it from. As a subagent (under `agents/`) it runs in its own context, which is what lets its actions and its token and time usage be measured on their own. The skill is the source of truth; `scripts/build_agents.py` generates the subagent from it, so the two never drift, and `scripts/build_agents.py --check` fails if they do. The generator also gives each subagent a tool set, a model, and a color from its role, so a reviewer subagent is read-only by construction and cannot edit, while an implementer gets edit and shell tools. The coordinator is the one specialist with no subagent form, because a subagent cannot dispatch other subagents.

## Memory and observability

The shared state is also made durable and observable through bundled hooks, driven by the runtime rather than by any specialist remembering to act:

- Memory is a loop. A `Stop`/`SubagentStop` hook captures finished work to `.kumi/memory/log.md`; a `SessionStart` hook restores the recent entries into a new session, so work resumes instead of starting cold. See [MEMORY.md](MEMORY.md).
- Observability is opt-in by the presence of `.kumi/`. A `PostToolUse` hook logs each tool action, and a `Stop`/`SubagentStop` hook records token and time usage per session and per agent. See [OBSERVABILITY.md](OBSERVABILITY.md).

The names of all these files live in `config/runtime.json`, so the layout is data, not code.

## Invariants

These stay true no matter how many specialists are added:

- The coordinator never hardcodes a specialist; it only knows the role table.
- The coordinator never routes to itself. A `/yui` call is already the coordinator acting; `yui` is not in its own role table, so it dispatches only to specialists and can never loop by calling `yui` from `yui`.
- No specialist knows another's internals; they communicate only through the shared handoff format.
- Adding, removing, or renaming a specialist touches only that skill's folder and one role-table row.
- The validator is the sole definition of a conforming skill.

## Role shapes

Specialists come in a few consistent shapes, which is why the team reads as coherent:

- **Implementers** (jaan, liis, ren, eero, noa): read context, work from a spec, smallest correct change, verify.
- **Debuggers** (siim, kadi, shu, anu, rui): reproduce, find root cause, touch only the broken path, verify the failure is gone.
- **Reviewers** (mart, tiiu, ryo, ivo, aki): read-only, checklist-driven, findings ranked by severity.
- **Architect** (kai): designs and specs before code, for any stack. Cross-cutting, not tied to one language.
- **Data specialists** (saku for SQL, remo for NoSQL): model and change data with the smallest safe change. Single roles, because a database does not need a full trio.
- **Coordinator** (yui): routes only.
- **Cross-cutting** (enn): process management.

Every language area is the same implement/debug/review trio, so the extensibility is visible in the roster itself: adding a stack is adding one more trio of the same three shapes. The architect, the process manager, and the data specialists sit outside the trios as cross-cutting or single roles that serve all of them.
