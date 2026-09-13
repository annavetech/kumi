# The specialists

This folder holds the team. Each subfolder is one specialist, defined by a single `SKILL.md` that follows the same contract as every other. This page is the roster: who they are, how they relate, and where to read each one.

For the design behind the team, see [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md). For all the diagrams, see [../docs/DIAGRAMS.md](../docs/DIAGRAMS.md).

## What a specialist is

A specialist is one skill file. It carries a trigger-oriented description (so it fires when the work matches), a hard gate (what it must do before acting), an ordered checklist, a process flow, a handoff, and its principles and tone. Because every specialist has the same shape, reading one teaches you all of them.

## The roster

Call the coordinator to route work, or call any specialist directly by name.

| Name | Call | Shape | Role | Skill |
|------|------|-------|------|-------|
| **yui**  | `/yui`  | Coordinator | Routes work to the right specialist, or runs a feature end to end | [yui/SKILL.md](yui/SKILL.md) |
| **kai**  | `/kai`  | Architect | Designs and specs before any code is written, for any stack | [kai/SKILL.md](kai/SKILL.md) |
| **jaan** | `/jaan` | Implementer | Writes and edits Go features | [jaan/SKILL.md](jaan/SKILL.md) |
| **siim** | `/siim` | Debugger | Finds and fixes a specific Go bug | [siim/SKILL.md](siim/SKILL.md) |
| **mart** | `/mart` | Reviewer | Read-only Go quality, security, architecture review | [mart/SKILL.md](mart/SKILL.md) |
| **liis** | `/liis` | Implementer | Writes and edits Angular features | [liis/SKILL.md](liis/SKILL.md) |
| **kadi** | `/kadi` | Debugger | Finds and fixes a specific Angular bug | [kadi/SKILL.md](kadi/SKILL.md) |
| **tiiu** | `/tiiu` | Reviewer | Read-only Angular review | [tiiu/SKILL.md](tiiu/SKILL.md) |
| **ren**  | `/ren`  | Implementer | Writes and edits iOS (Swift/SwiftUI) features | [ren/SKILL.md](ren/SKILL.md) |
| **shu**  | `/shu`  | Debugger | Finds and fixes a specific iOS bug | [shu/SKILL.md](shu/SKILL.md) |
| **ryo**  | `/ryo`  | Reviewer | Read-only iOS review | [ryo/SKILL.md](ryo/SKILL.md) |
| **eero** | `/eero` | Implementer | Writes and edits Python features | [eero/SKILL.md](eero/SKILL.md) |
| **anu**  | `/anu`  | Debugger | Finds and fixes a specific Python bug | [anu/SKILL.md](anu/SKILL.md) |
| **ivo**  | `/ivo`  | Reviewer | Read-only Python review | [ivo/SKILL.md](ivo/SKILL.md) |
| **noa**  | `/noa`  | Implementer | Writes and edits React/TypeScript features | [noa/SKILL.md](noa/SKILL.md) |
| **rui**  | `/rui`  | Debugger | Finds and fixes a specific React bug | [rui/SKILL.md](rui/SKILL.md) |
| **aki**  | `/aki`  | Reviewer | Read-only React review | [aki/SKILL.md](aki/SKILL.md) |
| **saku** | `/saku` | Specialist | Relational schema, queries, and safe migrations | [saku/SKILL.md](saku/SKILL.md) |
| **remo** | `/remo` | Specialist | Document and key-value modeling and access patterns | [remo/SKILL.md](remo/SKILL.md) |
| **enn**  | `/enn`  | Process manager | Starts, stops, and inspects dev servers and ports | [enn/SKILL.md](enn/SKILL.md) |

## The three shapes

Most specialists are one of three shapes, and they stay consistent within a shape across stacks. This is why the team reads as coherent instead of twenty unrelated prompts.

- **Implementers** (`jaan`, `liis`, `ren`, `eero`, `noa`), read context first, work from a spec, make the smallest correct change, verify.
- **Debuggers** (`siim`, `kadi`, `shu`, `anu`, `rui`), reproduce first, find the root cause, touch only the broken path, verify the failure is gone.
- **Reviewers** (`mart`, `tiiu`, `ryo`, `ivo`, `aki`), read-only, checklist-driven, findings ranked by severity, never edit.

Every language area is the same trio, and nothing more. The rest are cross-cutting single roles that serve all of them: the **coordinator** (`yui`), which only routes; the **architect** (`kai`), which specs work before code for any stack; the **data specialists** (`saku` for SQL, `remo` for NoSQL); and the **process manager** (`enn`). Databases are single specialists on purpose, because they do not need a full trio.

Learn how `jaan` / `siim` / `mart` relate for Go, and you already know how each other stack's trio relates: `liis` / `kadi` / `tiiu` for Angular, `ren` / `shu` / `ryo` for iOS, `eero` / `anu` / `ivo` for Python, `noa` / `rui` / `aki` for React. A new stack is a new trio of the same three shapes.

## How they work together

For a single-role task, call the specialist directly. For a task that spans roles, `yui` sequences them and passes context through shared state under `.kumi/` in the working project. See [../docs/DIAGRAMS.md](../docs/DIAGRAMS.md) for the collaboration graph, the end-to-end sequence, and the shared-state data flow.

## Adding one

Adding a specialist is mechanical: copy the template, fill the fixed sections, add one row to the coordinator's table, run the validator. See [../CONTRIBUTING.md](../CONTRIBUTING.md).
