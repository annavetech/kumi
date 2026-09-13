#!/usr/bin/env python3
"""Generate subagent definitions from the skills.

kumi ships each specialist as both a skill (lightweight, invoked by name in the
main session) and a subagent (its own context, so its actions and token/time can
be measured per agent). The skill is the single source of truth; this script
derives agents/<name>.md from skills/<name>/SKILL.md so the two never drift. Run
it whenever a skill changes.

Each generated subagent also gets a tool set, a model, and a color, chosen from
the specialist's role. Reviewers get read-only tools so a reviewer subagent
genuinely cannot edit; implementers and debuggers get edit and shell tools; the
architect gets read and write (it produces a spec document, never code); the
process manager gets shell and read. Colors group the roles at a glance.

The coordinator (yui) is intentionally not generated as a subagent: a subagent
cannot dispatch other subagents, so yui stays a skill that runs in the main
session and routes.

Usage (from the plugin root):
    python3 scripts/build_agents.py          # write agents/
    python3 scripts/build_agents.py --check  # verify agents/ is up to date

Exit codes:
    0  wrote successfully, or (with --check) everything is up to date
    1  (with --check) one or more agent files are missing or stale
    2  usage or environment error

Complexity: one pass over the skills; each skill is read once and written once.
Standard library only.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKILLS_DIR = os.path.join(ROOT, "skills")
AGENTS_DIR = os.path.join(ROOT, "agents")

# Roles that must not become subagents (a subagent cannot dispatch subagents).
EXCLUDE = {"yui"}

MODEL = "sonnet"

# Tool set and color per role kind. Reviewers are read-only by construction.
ROLE_TOOLS = {
    "implementer": ["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
    "debugger": ["Read", "Edit", "Bash", "Glob", "Grep"],
    "reviewer": ["Read", "Bash", "Glob", "Grep"],
    "architect": ["Read", "Write", "Glob", "Grep"],
    "data": ["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
    "ops": ["Bash", "Read", "Glob"],
}
ROLE_COLOR = {
    "implementer": "green",
    "debugger": "orange",
    "reviewer": "blue",
    "architect": "purple",
    "data": "cyan",
    "ops": "yellow",
}

GENERATED_NOTE = (
    "<!-- Generated from skills/{name}/SKILL.md by scripts/build_agents.py. "
    "Edit the skill, not this file. -->"
)


def split_frontmatter(text):
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    return text[3:end].strip(), text[end + 4:].lstrip("\n")


def field(frontmatter, key):
    """Return the value of a frontmatter key, or None. Allows indentation so it
    also reads keys nested under the metadata block."""
    m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+)$", frontmatter, re.MULTILINE)
    return m.group(1).strip() if m else None


def role_kind(role):
    """Classify a metadata role string into one of the tool/color groups."""
    # Match on the words in the role title: "Go Implementer", "Python Debugger",
    # "SQL Specialist", and so on.
    r = (role or "").lower()
    if "implementer" in r:
        return "implementer"
    if "debugger" in r:
        return "debugger"
    if "reviewer" in r:
        return "reviewer"
    if "architect" in r:
        return "architect"
    if "sql" in r:  # covers "SQL Specialist" and "NoSQL Specialist"
        return "data"
    if "process" in r or "ops" in r:
        return "ops"
    return "implementer"


def agent_text(name, description, kind, body):
    note = GENERATED_NOTE.format(name=name)
    tools = ", ".join(ROLE_TOOLS[kind])
    color = ROLE_COLOR[kind]
    return (
        f"---\nname: {name}\ndescription: {description}\n"
        f"tools: {tools}\nmodel: {MODEL}\ncolor: {color}\n---\n\n{note}\n\n{body}"
    )


def build_one(name):
    """Return (filename, content) for a skill, or None to skip it."""
    if name in EXCLUDE:
        return None
    skill_path = os.path.join(SKILLS_DIR, name, "SKILL.md")
    if not os.path.isfile(skill_path):
        return None
    with open(skill_path, encoding="utf-8") as f:
        fm, body = split_frontmatter(f.read())
    if fm is None:
        return None
    description = field(fm, "description")
    if not description:
        return None
    kind = role_kind(field(fm, "role"))
    return f"{name}.md", agent_text(name, description, kind, body.rstrip() + "\n")


def main():
    check = "--check" in sys.argv[1:]
    if not os.path.isdir(SKILLS_DIR):
        print(f"error: skills directory not found: {SKILLS_DIR}")
        return 2

    if not check:
        os.makedirs(AGENTS_DIR, exist_ok=True)

    stale = []
    written = 0
    for name in sorted(os.listdir(SKILLS_DIR)):
        result = build_one(name)
        if result is None:
            continue
        fname, content = result
        out = os.path.join(AGENTS_DIR, fname)
        if check:
            current = None
            if os.path.isfile(out):
                with open(out, encoding="utf-8") as f:
                    current = f.read()
            if current != content:
                stale.append(fname)
        else:
            with open(out, "w", encoding="utf-8") as f:
                f.write(content)
            written += 1

    if check:
        if stale:
            print("out of date (run scripts/build_agents.py):")
            for s in stale:
                print(f"  - {s}")
            return 1
        print("agents/ is up to date")
        return 0

    print(f"generated {written} agents into {os.path.relpath(AGENTS_DIR, ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
