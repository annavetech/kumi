#!/usr/bin/env python3
"""Structural check for the routing evals.

This does not call a model. It verifies the eval set in cases.yaml is coherent:
every case is well-formed, every `expect` names a real skill under ../skills,
and no prompt is duplicated. The behavioural check (that the expected specialist
actually fires) is done by invoking each prompt in Claude Code; see README.md.

The eval data lives in cases.yaml, not in this file. This script only parses and
checks it, using a small YAML subset reader so it needs no dependencies.

Usage (from the plugin root):

    python3 evals/check_cases.py

Exit codes:
    0  every case is well-formed and points at a real skill
    1  one or more cases are malformed or point at a missing skill
    2  usage or environment error (cases file missing, skills dir missing)

Complexity: one linear pass to parse cases, one linear pass to check them; skill
existence is an O(1) set lookup. Standard library only.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CASES = os.path.join(HERE, "cases.yaml")
SKILLS_DIR = os.path.join(ROOT, "skills")

REQUIRED_FIELDS = ["prompt", "expect", "why"]

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_ERROR = 2


def load_cases(path):
    """Parse the fixed-shape cases.yaml without a YAML dependency.

    Only the structure this file uses is supported: a `cases:` list whose items
    are `- key: value` / `  key: value` blocks with quoted scalar values.
    """
    cases = []
    current = None
    in_cases = False
    with open(path, encoding="utf-8") as f:
        for raw in f:
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped == "cases:":
                in_cases = True
                continue
            if not in_cases:
                continue
            # A "- " starts a new case; flush the one we were building.
            if stripped.startswith("- "):
                if current:
                    cases.append(current)
                current = {}
                stripped = stripped[2:].strip()
            if current is None:
                continue
            if ":" in stripped:
                key, _, value = stripped.partition(":")
                current[key.strip()] = value.strip().strip('"')
    if current:
        cases.append(current)
    return cases


def real_skills():
    return {
        name
        for name in os.listdir(SKILLS_DIR)
        if os.path.isfile(os.path.join(SKILLS_DIR, name, "SKILL.md"))
    }


def main():
    if not os.path.isfile(CASES):
        print(f"error: cases file not found: {CASES}")
        return EXIT_ERROR
    if not os.path.isdir(SKILLS_DIR):
        print(f"error: skills directory not found: {SKILLS_DIR}")
        return EXIT_ERROR

    cases = load_cases(CASES)
    skills = real_skills()

    problems = []
    seen_prompts = set()
    covered = set()

    for i, case in enumerate(cases, 1):
        label = (case.get("prompt") or f"<case {i}>")[:60]
        for field in REQUIRED_FIELDS:
            if not case.get(field):
                problems.append(f"case {i} ({label}): missing '{field}'")
        expect = case.get("expect")
        if expect:
            if expect not in skills:
                problems.append(
                    f"case {i} ({label}): expects '{expect}', not a skill"
                )
            else:
                covered.add(expect)
        prompt = case.get("prompt")
        if prompt:
            if prompt in seen_prompts:
                problems.append(f"case {i}: duplicate prompt")
            seen_prompts.add(prompt)

    if not problems:
        for case in cases:
            print(f"ok   {case.get('expect'):5}  {case.get('prompt')[:64]}")

    uncovered = sorted(skills - covered)
    print()
    print(f"{len(cases)} cases, {len(skills)} skills, {len(covered)} skills covered")
    if uncovered:
        print(f"note: no case targets: {', '.join(uncovered)}")
    if problems:
        print()
        for p in problems:
            print(f"FAIL {p}")
        return EXIT_INVALID
    print("all cases well-formed and pointing at real skills")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
