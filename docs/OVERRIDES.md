# Project overrides

`.kumi/overrides.json` holds project-specific rules on top of kumi's own built-in discipline. Rules under `all` apply to every specialist; rules under a specialist's name apply only to that one. See [config/overrides.example.json](../config/overrides.example.json) for the shape.

One file, one shared loader (`hooks/kumi_state.py`'s `load_trusted_overrides`), read by two hooks, because the two paths a specialist can be reached through need the rules delivered differently.

## Confirming the file

A repository can ship a `.kumi/overrides.json`, so kumi applies the rules only after the user confirms the exact file content. Until then no rule text is shown to the model or to the user.

1. At session start, a project with an unconfirmed `overrides.json` gets a notice instead of rules: the file's path, the first 32 hex characters of its SHA-256 as a code, and the command to confirm it. The model is told to treat the file as project data and not to follow it.
2. Open the file in an editor and review it.
3. Type `/kumi:trust <code>`, with 32 to 64 hex characters of the SHA-256 and nothing else.
4. `hooks/confirm_overrides.py` (`UserPromptExpansion`, matcher `^kumi:(?:un)?trust$`) checks the code against the current file and records the confirmation outside the project, in the plugin's data directory, keyed by the file's resolved path and its SHA-256. The result is shown to the user once. The model gets only a fixed note, with nothing from the file. The note and the skill tell it to reply with one fixed line, "Done. The result is shown above", and nothing else. A code that does not match records nothing.

`/kumi:trust` alone shows the path, the full SHA-256, the rule count per scope, and whether the file is applied; it records nothing. `/kumi:untrust` removes the confirmation.

Both commands are user-only. Their skills set `disable-model-invocation: true`, so the model cannot call them, and `UserPromptExpansion` fires only when the user types a command, so a model action never records a confirmation. The command arguments reach the hook as a JSON field; no shell runs them.

Any change to the file, by any editor, a `git pull`, or the model, gives a new hash. The rules then stop applying and the notice says the file changed since it was confirmed. Review it and confirm again; the new confirmation replaces the old one.

## Path 1: the coordinator's own session

`hooks/apply_overrides.py` fires on `SessionStart` and injects the confirmed rules as `additionalContext`. This reaches the main session, which is `yui` whenever a user calls `/yui` or talks to kumi directly. It does not reach a subagent: `SessionStart` context is not passed into an `Agent`/`Task` dispatch.

## Path 2: a directly dispatched specialist

`hooks/inject_specialist_context.py` fires on `PreToolUse`, matcher `Agent|Task`. It resolves the target specialist from `tool_input.subagent_type`, loads the confirmed rules scoped to `all` plus that specialist, and if any apply, returns a `PreToolUse` response with `hookSpecificOutput.updatedInput` that appends them to `tool_input.prompt`. This is the only path that reaches a specialist dispatched directly, whether `yui` did the dispatching or a slash command bypassed `yui` entirely. The `Skill` tool is excluded from this hook's matcher: skill-mode use runs in the caller's own context, which already receives path 1's `SessionStart` content.

The same hook also checks the dispatch brief itself before a specialist starts: a brief missing a goal, an output format, where to look, or limits is denied, with a message naming the missing part, so the coordinator rewrites it rather than dispatching an underspecified task. See `skills/yui/SKILL.md`'s "Hand off with context" step for the brief structure this expects.

## The honest limit

Both hooks are guarded to always exit 0, so a malformed or missing `overrides.json` never blocks a dispatch. Neither hook invents rules; they only relay whatever is written in the file. A file the user has not confirmed is never shown to the model.
