#!/usr/bin/env python3
"""kumi test suite.

Runs every check the plugin ships with and, importantly, verifies the negative
cases too: that the validator actually rejects malformed skills, and that the
hooks never fail no matter what they are handed. A validator that never says no
is not a validator, so those negative cases are the point.

Usage (from the plugin root):
    python3 tests/run_tests.py

Exit codes:
    0  all tests passed
    1  one or more tests failed
    2  environment error

Standard library only.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from validate_skills import check_skill, load_contract, CONTRACT  # noqa: E402

PASS, FAIL = 0, 0


def ok(name):
    global PASS
    PASS += 1
    print(f"ok   {name}")


def bad(name, detail):
    global FAIL
    FAIL += 1
    print(f"FAIL {name}")
    print(f"     {detail}")


VALID_SKILL = """---
name: sample
description: "You MUST use this for the sample."
metadata:
  role: Sample
  domain: Sample
  when-to-use: when sampling
  hands-off-to: [other]
---

# sample, Sample

Intro line.

<HARD-GATE>
Do NOT do the thing prematurely.
</HARD-GATE>

## Anti-Pattern: "shortcut"

Body.

## Checklist

1. step

## Process Flow

```
a -> b
```

## Handoff

Hands off.

## Key Principles

- one

## Tone

Terse.
"""


def write_tmp(text):
    fd, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def test_positive_valid_sample(contract):
    path = write_tmp(VALID_SKILL)
    try:
        problems = check_skill(path, contract)
        if problems:
            bad("valid sample passes", f"unexpected problems: {problems}")
        else:
            ok("valid sample passes")
    finally:
        os.remove(path)


def test_negative_cases(contract):
    cases = [
        ("no frontmatter", "no frontmatter here", "missing YAML frontmatter"),
        (
            "missing description",
            VALID_SKILL.replace('description: "You MUST use this for the sample."\n', ""),
            "frontmatter missing 'description'",
        ),
        (
            "missing metadata role",
            VALID_SKILL.replace("  role: Sample\n", ""),
            "metadata missing 'role'",
        ),
        (
            "missing hard gate",
            VALID_SKILL.replace("<HARD-GATE>\nDo NOT do the thing prematurely.\n</HARD-GATE>", ""),
            "missing <HARD-GATE> block",
        ),
        (
            "missing a section",
            VALID_SKILL.replace("## Tone\n\nTerse.\n", ""),
            "missing section '## Tone'",
        ),
        (
            "sections out of order",
            VALID_SKILL.replace("## Anti-Pattern: \"shortcut\"", "## Tone\n\nMoved up.\n\n## Anti-Pattern: \"shortcut\""),
            "out of order",
        ),
    ]
    for label, text, expect in cases:
        path = write_tmp(text)
        try:
            problems = check_skill(path, contract)
            if any(expect in p for p in problems):
                ok(f"rejects: {label}")
            else:
                bad(f"rejects: {label}", f"expected '{expect}', got {problems}")
        finally:
            os.remove(path)


def run(script, *args):
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, script), *args],
        capture_output=True, text=True,
    )


def test_all_real_skills_pass():
    r = run("tests/validate_skills.py")
    ok("all real skills pass") if r.returncode == 0 else bad(
        "all real skills pass", r.stdout + r.stderr)


def test_eval_cases_pass():
    r = run("evals/check_cases.py")
    ok("eval cases coherent") if r.returncode == 0 else bad(
        "eval cases coherent", r.stdout + r.stderr)


def test_agents_up_to_date():
    r = run("scripts/build_agents.py", "--check")
    ok("agents up to date") if r.returncode == 0 else bad(
        "agents up to date", r.stdout + r.stderr)


def test_hooks_never_fail():
    empty = tempfile.mkdtemp()  # a dir with no .kumi
    inputs = ['', 'not json', '{}', f'{{"cwd":"{empty}"}}']
    hooks = ["capture_memory", "restore_memory", "log_activity", "record_metrics", "apply_overrides"]
    all_ok = True
    for hook in hooks:
        for payload in inputs:
            r = subprocess.run(
                [sys.executable, os.path.join(ROOT, "hooks", f"{hook}.py")],
                input=payload, capture_output=True, text=True,
            )
            if r.returncode != 0:
                all_ok = False
                bad(f"hook {hook} exits 0", f"payload={payload!r} rc={r.returncode} {r.stderr}")
                break
    if all_ok:
        ok("hooks never fail on bad or empty input")


def main():
    try:
        contract = load_contract(CONTRACT)
    except Exception as e:
        print(f"error: {e}")
        return 2
    test_positive_valid_sample(contract)
    test_negative_cases(contract)
    test_all_real_skills_pass()
    test_eval_cases_pass()
    test_agents_up_to_date()
    test_hooks_never_fail()
    print()
    print(f"{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
