#!/usr/bin/env python3
"""Validate that every skill conforms to the kumi skill contract.

The contract itself lives in config/contract.json, not in this file, so the
rules can be changed without editing code. This script only enforces whatever
that file declares: required frontmatter keys, required metadata keys, a
hard-gate block, and the required sections in order.

Usage (from the plugin root):

    python3 tests/validate_skills.py

Exit codes:
    0  all skills valid
    1  one or more skills failed validation
    2  usage or environment error (config missing, skills dir missing, bad JSON)

Complexity: each skill file is read once and scanned in a single linear pass
(O(n) in the file size); section order is checked with one forward scan, no
re-reads. Standard library only.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKILLS_DIR = os.path.join(ROOT, "skills")
CONTRACT = os.path.join(ROOT, "config", "contract.json")

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_ERROR = 2


def load_contract(path):
    """Load and sanity-check the contract file. Raises ValueError if unusable."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for key in ("frontmatter_required", "metadata_required", "required_sections"):
        if not isinstance(data.get(key), list):
            raise ValueError(f"contract missing list '{key}'")
    if not isinstance(data.get("hard_gate"), dict):
        raise ValueError("contract missing 'hard_gate' object")
    return data


def split_frontmatter(text):
    """Return (frontmatter_text, body), or (None, text) when there is none."""
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    return text[3:end].strip(), text[end + 4:]


def check_skill(path, contract):
    """Return a list of problem strings for one skill (empty means valid)."""
    problems = []
    with open(path, encoding="utf-8") as f:
        text = f.read()

    fm, body = split_frontmatter(text)
    if fm is None:
        return ["missing YAML frontmatter"]

    for key in contract["frontmatter_required"]:
        if not re.search(rf"^{re.escape(key)}\s*:", fm, re.MULTILINE):
            problems.append(f"frontmatter missing '{key}'")

    if "metadata:" not in fm:
        problems.append("frontmatter missing 'metadata' block")
    else:
        for key in contract["metadata_required"]:
            if not re.search(rf"^\s+{re.escape(key)}\s*:", fm, re.MULTILINE):
                problems.append(f"metadata missing '{key}'")

    gate = contract["hard_gate"]
    if gate["open"] not in body or gate["close"] not in body:
        problems.append(f"missing {gate['open']} block")

    # Walk the required sections in order. Each must appear later in the file
    # than the one before it, which is what keeps every skill the same shape.
    ordered = contract.get("sections_must_be_ordered", True)
    last_index = -1
    for section in contract["required_sections"]:
        idx = body.find(section)
        if idx == -1:
            problems.append(f"missing section '{section}'")
        elif ordered and idx < last_index:
            problems.append(f"section out of order '{section}'")
        else:
            last_index = idx

    return problems


def main():
    try:
        contract = load_contract(CONTRACT)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: cannot load contract {CONTRACT}: {e}")
        return EXIT_ERROR

    if not os.path.isdir(SKILLS_DIR):
        print(f"error: skills directory not found: {SKILLS_DIR}")
        return EXIT_ERROR

    failures = 0
    checked = 0
    for name in sorted(os.listdir(SKILLS_DIR)):
        skill_md = os.path.join(SKILLS_DIR, name, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        checked += 1
        problems = check_skill(skill_md, contract)
        if problems:
            failures += 1
            print(f"FAIL {name}")
            for p in problems:
                print(f"     - {p}")
        else:
            print(f"ok   {name}")

    print()
    print(f"{checked} skills checked, {failures} failed")
    return EXIT_INVALID if failures else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
