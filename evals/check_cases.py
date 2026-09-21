#!/usr/bin/env python3
"""Structural check for the routing evals in cases.yaml.
Verifies every case is well-formed and every `expect` names a real skill; does not call a model."""

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
    """Parse the fixed-shape cases.yaml without a YAML dependency."""
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
        must, must_not = case.get("must"), case.get("must_not")
        if (must or must_not) and not (must and must_not):
            missing = "must" if not must else "must_not"
            problems.append(f"case {i} ({label}): must/must_not is one-sided, missing '{missing}'")

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
