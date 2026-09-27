# Project overrides

`.kumi/overrides.json` holds project-specific rules on top of kumi's own built-in discipline. Rules under `all` apply to every specialist; rules under a specialist's name apply only to that one. See [config/overrides.example.json](../config/overrides.example.json) for the shape.

One file, one shared loader (`hooks/kumi_state.py`'s `load_overrides`), read by two hooks, because the two paths a specialist can be reached through need the rules delivered differently.

## Path 1: the coordinator's own session

`hooks/apply_overrides.py` fires on `SessionStart` and injects the matching rules as `additionalContext`. This reaches the main session, which is `yui` whenever a user calls `/yui` or talks to kumi directly. It does not reach a subagent: `SessionStart` context is not passed into an `Agent`/`Task` dispatch.

## Path 2: a directly dispatched specialist

`hooks/inject_specialist_context.py` fires on `PreToolUse`, matcher `Agent|Task`. It resolves the target specialist from `tool_input.subagent_type`, loads the rules scoped to `all` plus that specialist, and if any apply, returns a `PreToolUse` response with `hookSpecificOutput.updatedInput` that appends them to `tool_input.prompt`. This is the only path that reaches a specialist dispatched directly, whether `yui` did the dispatching or a slash command bypassed `yui` entirely. The `Skill` tool is excluded from this hook's matcher: skill-mode use runs in the caller's own context, which already receives path 1's `SessionStart` content.

The same hook also checks the dispatch brief itself before a specialist starts: a brief missing a goal, an output format, where to look, or limits is denied, with a message naming the missing part, so the coordinator rewrites it rather than dispatching an underspecified task. See `skills/yui/SKILL.md`'s "Hand off with context" step for the brief structure this expects.

## The honest limit

Both hooks are guarded to always exit 0, so a malformed or missing `overrides.json` never blocks a dispatch. Neither hook invents rules; they only relay whatever is written in the file.
