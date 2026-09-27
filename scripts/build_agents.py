#!/usr/bin/env python3
"""Generate subagent definitions from the skills.
Derives agents/<name>.md from skills/<name>/SKILL.md, the source of truth, so they never drift."""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKILLS_DIR = os.path.join(ROOT, "skills")
AGENTS_DIR = os.path.join(ROOT, "agents")
HOUSE_RULES_PATH = os.path.join(ROOT, "config", "house_rules.md")
RUNTIME_CONFIG_PATH = os.path.join(ROOT, "config", "runtime.json")

# Roles that must not become subagents (a subagent cannot dispatch subagents).
EXCLUDE = {"yui"}

DEFAULT_MODEL = "inherit"


# Matches a model name safe to write unquoted into YAML frontmatter (covers Bedrock/Vertex ids),
# and rejects whitespace or a trailing colon, either of which would break the line.
MODEL_NAME_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._\[\]:@/-]*[A-Za-z0-9\]])?")

# YAML reserved barewords: unquoted, these parse as null or a boolean instead of a string.
YAML_RESERVED_WORDS = {"null", "true", "false", "yes", "no", "on", "off", "~"}


def usable_model_name(value):
    """True when value is a string that can be written into YAML frontmatter as-is."""
    if not isinstance(value, str) or MODEL_NAME_RE.fullmatch(value) is None:
        return False
    return value.lower() not in YAML_RESERVED_WORDS


def generated_specialist_names():
    """The names generation writes an agent for, or None when the skills tree cannot be read."""
    try:
        names = os.listdir(SKILLS_DIR)
    except OSError:
        return None
    return {
        name for name in names
        if name not in EXCLUDE and os.path.isfile(os.path.join(SKILLS_DIR, name, "SKILL.md"))
    }


def load_model_config():
    """Return (default_model, overrides) from config/runtime.json's "model" section.
    Malformed entries are dropped and named on stderr; the exit code stays 0."""
    ignored = []
    try:
        with open(RUNTIME_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except OSError:
        data = {}
    except json.JSONDecodeError:
        data = {}
        ignored.append("the file (not valid JSON)")

    if not isinstance(data, dict):
        ignored.append("the file (root is not an object)")
        data = {}
    model = data.get("model", {})
    if not isinstance(model, dict):
        ignored.append("model (not an object)")
        model = {}

    default = DEFAULT_MODEL
    if "default" in model:
        if usable_model_name(model["default"]):
            default = model["default"]
        else:
            ignored.append("model.default")

    overrides = {}
    raw_overrides = model.get("overrides", {})
    known = generated_specialist_names()
    if isinstance(raw_overrides, dict):
        for name, value in raw_overrides.items():
            if not usable_model_name(value):
                ignored.append(f"model.overrides.{name}")
            elif known is not None and name not in known:
                ignored.append(f"model.overrides.{name} (not a generated specialist)")
            else:
                overrides[name] = value
    else:
        ignored.append("model.overrides (not an object)")

    if ignored:
        print(
            f"warning: {os.path.relpath(RUNTIME_CONFIG_PATH, ROOT)}: "
            f"ignored {', '.join(ignored)}",
            file=sys.stderr,
        )
    return default, overrides


# Tool set and color per role kind. Reviewers are read-only by construction.
ROLE_TOOLS = {
    "implementer": ["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
    "debugger": ["Read", "Edit", "Bash", "Glob", "Grep"],
    "reviewer": ["Read", "Bash", "Glob", "Grep"],
    "architect": ["Read", "Write", "Glob", "Grep"],
    "data": ["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
    "devops": ["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
    "ops": ["Bash", "Read", "Glob"],
}
ROLE_COLOR = {
    "implementer": "green",
    "debugger": "orange",
    "reviewer": "blue",
    "architect": "purple",
    "data": "cyan",
    "devops": "red",
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
    """Return the value of a frontmatter key, or None; indentation is allowed for nested keys."""
    m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+)$", frontmatter, re.MULTILINE)
    return m.group(1).strip() if m else None


def role_kind(role):
    """Classify a metadata role string into one of the tool/color groups."""
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
    if "devops" in r or "infra" in r:
        return "devops"
    if "process" in r or "ops" in r:
        return "ops"
    return "implementer"


HEADING_RE = re.compile(r"^(#+)(\s)")
FENCE_RE = re.compile(r"^(`{3,}|~{3,})")


def shift_headings(text, by=1):
    """Lower every markdown heading in text by `by` levels, so it nests under a parent doc.
    Lines inside a fenced code block (``` or ~~~, any fence length) are left untouched."""
    lines = text.split("\n")
    out = []
    fence_char, fence_len = None, 0
    for line in lines:
        m = FENCE_RE.match(line.lstrip())
        if m:
            marker = m.group(1)
            if fence_char is None:
                fence_char, fence_len = marker[0], len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_len:
                fence_char, fence_len = None, 0
            out.append(line)
            continue
        if fence_char is None:
            line = HEADING_RE.sub(lambda mm: ("#" * (len(mm.group(1)) + by)) + mm.group(2), line)
        out.append(line)
    return "\n".join(out)


def load_house_rules():
    """Read kumi's own shared house rules, shifted one heading level to nest in a host doc."""
    with open(HOUSE_RULES_PATH, encoding="utf-8") as f:
        return shift_headings(f.read().rstrip() + "\n")


def agent_text(name, description, kind, body, house_rules, model):
    note = GENERATED_NOTE.format(name=name)
    tools = ", ".join(ROLE_TOOLS[kind])
    color = ROLE_COLOR[kind]
    return (
        f"---\nname: {name}\ndescription: {description}\n"
        f"tools: {tools}\nmodel: {model}\ncolor: {color}\n---\n\n{note}\n\n{body}"
        f"\n{house_rules}"
    )


def build_one(name, default_model, model_overrides):
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
    house_rules = load_house_rules()
    model = model_overrides.get(name, default_model)
    content = agent_text(name, description, kind, body.rstrip() + "\n", house_rules, model)
    return f"{name}.md", content


def main():
    check = "--check" in sys.argv[1:]
    if not os.path.isdir(SKILLS_DIR):
        print(f"error: skills directory not found: {SKILLS_DIR}")
        return 2

    if not check:
        os.makedirs(AGENTS_DIR, exist_ok=True)

    default_model, model_overrides = load_model_config()
    stale = []
    written = 0
    for name in sorted(os.listdir(SKILLS_DIR)):
        result = build_one(name, default_model, model_overrides)
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
