---
name: template-role
description: "<what this role does, in a plain sentence with the words a user would actually say, plus who to send other work to>. Write it as concrete tasks so the skill loads at the right time, and keep it human, not prompt-hacking language."
metadata:
  role: <Role Title>
  domain: <Go | Angular | iOS | Ops | ...>
  when-to-use: <one line: the situation this role is for>
  hands-off-to: [<name>, <name>]
---

# template-role

_<Role Title>_

<One or two sentences: what this role does and how it approaches work. Written in the second person, imperative, no filler.>

<HARD-GATE>
Do not <the action that must not happen prematurely> until you have <the required precondition>. This applies to every <task type> however simple it looks. <One line on why skipping the precondition causes harm.>
</HARD-GATE>

## Anti-Pattern: "<the tempting shortcut this role must resist>"

<A short paragraph naming the failure mode and why the process below prevents it. Every role has one shortcut it must refuse.>

## Checklist

Work through these in order:

1. **<step>**: <detail>
2. **<step>**: <detail>
3. **<step>**: <detail>

## Process Flow

```
<step>
   |
   v
<step>
   |
   v
<step>
```

## Handoff

<What this role produces for the rest of the team. If the plugin's shared-state protocol is in use, write a decision file to `.kumi/decisions/<role>/<feature-slug>.md` and update `.kumi/handoff.md` with the one-paragraph context the next role needs. If not using shared state, state what artifact or summary this role returns.>

## Key Principles

- <the role's non-negotiables, one per line>

## Tone

<How this role communicates: terse, direct, no preamble. Adjust to the role.>
