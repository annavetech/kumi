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

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
GITHUB_SCRIPTS_DIR = os.path.join(ROOT, ".github", "scripts")
sys.path.insert(0, HERE)
sys.path.insert(0, SCRIPTS_DIR)
sys.path.insert(0, GITHUB_SCRIPTS_DIR)

from _github import report_if_error  # noqa: E402
from build_agents import role_kind  # noqa: E402
from merge_gate import MAX_DESCRIPTION_LENGTH, decide_state  # noqa: E402
from validate_skills import CONTRACT, check_skill, load_contract  # noqa: E402

PASS, FAIL = 0, 0

# Anna's rule: no automation process may ever produce an emoji. Pictographs,
# misc symbols, dingbats, and the variation-selector-16 that turns a plain
# glyph into its emoji-presentation form.
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # misc symbols and pictographs through extended-A
    "\U00002600-\U000027BF"  # misc symbols, dingbats
    "\U0000FE0F"  # variation selector-16 (emoji presentation)
    "]"
)


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
            VALID_SKILL.replace(
                "## Anti-Pattern: \"shortcut\"",
                "## Tone\n\nMoved up.\n\n## Anti-Pattern: \"shortcut\"",
            ),
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


def test_role_kind_devops_before_ops():
    # "DevOps Specialist" contains the substring "ops", so the devops branch
    # must be checked before the process/ops branch or it would misclassify
    # into enn's kind (no Edit/Write), leaving sora unable to write its own
    # Dockerfiles and workflow files.
    cases = [
        ("DevOps Specialist", "devops"),
        ("Infra Specialist", "devops"),
        ("Process Manager", "ops"),
    ]
    for role, expect in cases:
        got = role_kind(role)
        if got == expect:
            ok(f"role_kind({role!r}) == {expect!r}")
        else:
            bad(f"role_kind({role!r}) == {expect!r}", f"got {got!r}")


def test_chat_ops_workflow_permissions():
    # A PR comment's `issue_number` resolves to a pull request, and adding a
    # label or reacting to that comment via GITHUB_TOKEN 403s with only
    # `issues: write` — GitHub requires `pull-requests: write` too (see
    # workflow-syntax's own example: "pull-requests: write permits an action
    # to add a label to a pull request"). Both runs of chat-ops on PR #6
    # (2026-09-17) 403'd on add_labels and add_reaction for exactly this
    # reason. Guard the workflow-level permissions block against regressing.
    path = os.path.join(ROOT, ".github", "workflows", "chat-ops.yml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    perms_block = text.split("jobs:", 1)[0]
    required = ("issues: write", "pull-requests: write")
    missing = [perm for perm in required if perm not in perms_block]
    if missing:
        bad("chat-ops workflow grants issues:write and pull-requests:write", f"missing: {missing}")
    else:
        ok("chat-ops workflow grants issues:write and pull-requests:write")


def test_report_if_error_prints_github_message():
    message = "Resource not accessible by integration"
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        report_if_error("add_labels(approved)", 403, {"message": message})
    output = stderr.getvalue()
    name = "report_if_error prints GitHub's error message, not just the status"
    if "403" in output and message in output:
        ok(name)
    else:
        bad(name, f"got: {output!r}")


def test_report_if_error_ignores_expected_status():
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        report_if_error("remove_label(x)", 404, {"message": "Not Found"}, ignore=(404,))
    if stderr.getvalue() == "":
        ok("report_if_error stays silent on an ignored status")
    else:
        bad("report_if_error stays silent on an ignored status", f"got: {stderr.getvalue()!r}")


def test_merge_gate_decide_state():
    cases = [
        (set(), "pending", "Needs approved, lgtm labels"),
        ({"lgtm"}, "pending", "Needs approved label"),
        ({"approved"}, "pending", "Needs lgtm label"),
        ({"lgtm", "approved"}, "success", "lgtm and approved; not held"),
        ({"lgtm", "approved", "do-not-merge/hold"}, "pending", "Blocked by do-not-merge/hold"),
        ({"do-not-merge/hold"}, "pending", "Blocked by do-not-merge/hold"),
        (
            {"lgtm", "do-not-merge/hold", "do-not-merge/work-in-progress"},
            "pending",
            "Blocked by do-not-merge/hold, do-not-merge/work-in-progress",
        ),
    ]
    for labels, expect_state, expect_desc in cases:
        state, desc = decide_state(labels)
        name = f"decide_state({sorted(labels)!r}) == ({expect_state!r}, {expect_desc!r})"
        if state == expect_state and desc == expect_desc:
            ok(name)
        else:
            bad(name, f"got ({state!r}, {desc!r})")


def test_merge_gate_description_length_capped():
    # A defensive cap, not a realistic input: confirms an unusual pile-up of
    # do-not-merge/* labels can never produce a status GitHub would reject.
    holds = {f"do-not-merge/a-fairly-long-reason-{i}" for i in range(20)}
    state, desc = decide_state(holds)
    name = "decide_state caps description at GitHub's 140-character limit"
    if state == "pending" and len(desc) <= MAX_DESCRIPTION_LENGTH:
        ok(name)
    else:
        bad(name, f"len={len(desc)} desc={desc!r}")


def test_merge_gate_workflow_permissions():
    path = os.path.join(ROOT, ".github", "workflows", "merge-gate.yml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    perms_block = text.split("jobs:", 1)[0]
    name = "merge-gate workflow grants only contents:read and statuses:write"
    required = ("contents: read", "statuses: write")
    missing = [perm for perm in required if perm not in perms_block]
    forbidden = ("contents: write", "issues: write", "pull-requests: write")
    over_broad = [perm for perm in forbidden if perm in perms_block]
    if missing or over_broad:
        bad(name, f"missing={missing} over_broad={over_broad}")
    else:
        ok(name)


def test_merge_gate_job_named_apart_from_status_context():
    # The job id (and its check-run name) must differ from the "merge-gate"
    # commit-status context merge_gate.py posts, or the two are impossible
    # to tell apart in branch protection's required-checks list.
    path = os.path.join(ROOT, ".github", "workflows", "merge-gate.yml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    name = "merge-gate job id differs from the merge-gate status context it posts"
    if "merge-gate-status:" in text and "\n  merge-gate:\n" not in text:
        ok(name)
    else:
        bad(name, "job id collides with (or is missing from) the status context name")


def test_merge_gate_never_checks_out_pr_head():
    # pull_request_target hands the job a write-capable token; it must only
    # read the event payload, never check out or run the PR's own code.
    path = os.path.join(ROOT, ".github", "workflows", "merge-gate.yml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    name = "merge-gate never checks out the PR's own head ref"
    if "ref:" not in text:
        ok(name)
    else:
        bad(name, "found an explicit checkout ref in a pull_request_target workflow")


def test_validate_claude_manifest_job_pins_checksum_safely():
    # Findings from ivo's review of the validate-claude-manifest job: (1) the
    # comment must never claim a signature that doesn't exist — the job only
    # ever checks a sha256 checksum; (2) nothing may be piped straight to a
    # shell, and the sha256 it checks against must be a literal pinned in the
    # repo, not fetched from the same origin as the binary at run time.
    path = os.path.join(ROOT, ".github", "workflows", "ci.yml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    job_marker = "\n  validate-claude-manifest:\n"
    if job_marker not in text:
        bad("validate-claude-manifest job pins a sha256 literal safely", "job not found in ci.yml")
        return
    job_text = text[text.index(job_marker):]

    problems = []
    if not re.search(r'"[a-f0-9]{64}"', job_text):
        problems.append("no 64-hex sha256 literal found")
    if re.search(r"curl[^\n|]*\|\s*bash", job_text):
        problems.append("pipes curl output straight to bash")
    if re.search(r"(?i)gpg|signed", job_text):
        problems.append("claims a signature ('GPG'/'signed') the job does not verify")

    name = "validate-claude-manifest job pins a sha256 literal safely"
    if problems:
        bad(name, "; ".join(problems))
    else:
        ok(name)


def test_no_emoji_under_github():
    result = subprocess.run(
        ["git", "-C", ROOT, "ls-files", ".github"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        bad("no emoji under .github", f"git ls-files failed: {result.stderr}")
        return
    offenders = []
    for rel_path in result.stdout.splitlines():
        path = os.path.join(ROOT, rel_path)
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except (UnicodeDecodeError, OSError):
            continue
        if EMOJI_PATTERN.search(text):
            offenders.append(rel_path)
    if offenders:
        bad("no emoji under .github", f"emoji found in: {offenders}")
    else:
        ok("no emoji under .github")


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
    # workdir is passed as the subprocess's real working directory, so a
    # hook's os.getcwd() fallback (e.g. ensure_state on a non-string cwd)
    # lands here rather than in this repo.
    workdir = tempfile.mkdtemp()
    empty = tempfile.mkdtemp(dir=workdir)  # a dir with no .kumi
    git_dir = os.path.join(workdir, ".git", "info")
    os.makedirs(git_dir)
    with open(os.path.join(git_dir, "exclude"), "wb") as f:
        f.write(b"already-here\n\xff\xfe not valid utf-8\n")  # pre-existing non-UTF-8 bytes
    common_inputs = ['', 'not json', '{}', f'{{"cwd":"{empty}"}}']
    # Malformed-cwd shapes (int, null, list, dict, empty string): kumi_state's
    # state_dir passes cwd straight into os.path.join, which used to raise
    # TypeError on anything but a string, and every one of these hooks lacked
    # an outer boundary to catch it. Run against all six hooks, not just
    # ensure_state, where this was first found and fixed.
    malformed_cwd_inputs = [
        '{"cwd":123}',
        '{"cwd":null}',
        '{"cwd":["a"]}',
        '{"cwd":{"a":1}}',
        '{"cwd":""}',
    ]
    # ensure_state also needs a real is_kumi_call shape (hook_event_name +
    # prompt) to reach its cwd-handling code path at all, plus a case with a
    # valid cwd that exercises the pre-seeded non-UTF-8 exclude file above.
    ensure_state_inputs = [
        '{"hook_event_name":"UserPromptSubmit","prompt":"/kumi:yui hi","cwd":123}',
        '{"hook_event_name":"UserPromptSubmit","prompt":"/kumi:yui hi","cwd":null}',
        '{"hook_event_name":"UserPromptSubmit","prompt":"/kumi:yui hi","cwd":["a"]}',
        '{"hook_event_name":"UserPromptSubmit","prompt":"/kumi:yui hi","cwd":{"a":1}}',
        '{"hook_event_name":"UserPromptSubmit","prompt":"/kumi:yui hi","cwd":""}',
        f'{{"hook_event_name":"UserPromptSubmit","prompt":"/kumi:yui hi","cwd":"{workdir}"}}',
    ]
    hooks = [
        "capture_memory", "restore_memory", "log_activity", "record_metrics",
        "apply_overrides", "ensure_state",
    ]
    all_ok = True
    try:
        for hook in hooks:
            inputs = common_inputs + malformed_cwd_inputs
            inputs += ensure_state_inputs if hook == "ensure_state" else []
            for payload in inputs:
                r = subprocess.run(
                    [sys.executable, os.path.join(ROOT, "hooks", f"{hook}.py")],
                    input=payload, capture_output=True, text=True, cwd=workdir,
                )
                if r.returncode != 0:
                    all_ok = False
                    bad(f"hook {hook} exits 0", f"payload={payload!r} rc={r.returncode} {r.stderr}")
                    break
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if all_ok:
        ok("hooks never fail on bad or empty input")


def run_ensure_state(payload_obj, env_extra=None, proc_cwd=None):
    """Run ensure_state.py with a JSON payload on stdin, return CompletedProcess.

    proc_cwd sets the subprocess's real working directory, distinct from the
    payload's own "cwd" field, so a fallback to os.getcwd() can be pinned to
    a disposable temp dir instead of wherever the test runner happens to be.
    """
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    stdin = json.dumps(payload_obj) if payload_obj is not None else ""
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "hooks", "ensure_state.py")],
        input=stdin, capture_output=True, text=True, env=env, cwd=proc_cwd,
    )


def test_ensure_state_creates_on_kumi_call():
    cases = [
        (
            "creates dir on /kumi: prompt",
            {"hook_event_name": "UserPromptSubmit", "prompt": "/kumi:yui do the thing"},
        ),
        (
            "creates dir on kumi skill",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Skill",
                "tool_input": {"skill": "kumi:eero"},
            },
        ),
        (
            "creates dir on kumi agent",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "kumi:eero"},
            },
        ),
        (
            "creates dir on kumi Task (older name)",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Task",
                "tool_input": {"subagent_type": "kumi:eero"},
            },
        ),
        (
            "creates dir on kumi command via UserPromptExpansion",
            {
                "hook_event_name": "UserPromptExpansion",
                "expansion_type": "slash_command",
                "command_name": "kumi:eero",
            },
        ),
    ]
    for label, extra in cases:
        project = tempfile.mkdtemp()
        try:
            payload = {**extra, "cwd": project}
            r = run_ensure_state(payload)
            kumi_dir = os.path.join(project, ".kumi")
            if r.returncode == 0 and os.path.isdir(kumi_dir) and r.stdout == "":
                ok(label)
            else:
                bad(
                    label,
                    f"rc={r.returncode} exists={os.path.isdir(kumi_dir)} "
                    f"stdout={r.stdout!r} stderr={r.stderr}",
                )
        finally:
            shutil.rmtree(project, ignore_errors=True)


def test_ensure_state_non_kumi_call_is_noop():
    cases = [
        (
            "does nothing on non-kumi prompt",
            {"hook_event_name": "UserPromptSubmit", "prompt": "please help with this"},
        ),
        (
            "does nothing on non-kumi skill",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Skill",
                "tool_input": {"skill": "other-skill"},
            },
        ),
        (
            "does nothing on non-kumi agent",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "other-agent"},
            },
        ),
        (
            "does nothing on unrelated tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Edit",
                "tool_input": {"file_path": "x.py"},
            },
        ),
        (
            "does nothing on non-kumi command via UserPromptExpansion",
            {
                "hook_event_name": "UserPromptExpansion",
                "expansion_type": "slash_command",
                "command_name": "other-skill",
            },
        ),
    ]
    for label, payload in cases:
        project = tempfile.mkdtemp()
        try:
            payload = {**payload, "cwd": project}
            r = run_ensure_state(payload)
            kumi_dir = os.path.join(project, ".kumi")
            if r.returncode == 0 and not os.path.isdir(kumi_dir) and r.stdout == "":
                ok(label)
            else:
                bad(
                    label,
                    f"rc={r.returncode} exists={os.path.isdir(kumi_dir)} "
                    f"stdout={r.stdout!r} stderr={r.stderr}",
                )
        finally:
            shutil.rmtree(project, ignore_errors=True)


def test_ensure_state_empty_or_malformed_stdin():
    cases = [("does nothing on empty stdin", ""), ("does nothing on malformed stdin", "not json")]
    for label, raw in cases:
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "hooks", "ensure_state.py")],
            input=raw, capture_output=True, text=True,
        )
        if r.returncode == 0 and r.stdout == "":
            ok(label)
        else:
            bad(label, f"rc={r.returncode} stdout={r.stdout!r} stderr={r.stderr}")


def test_ensure_state_idempotent():
    project = tempfile.mkdtemp()
    try:
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/kumi:yui do it",
            "cwd": project,
        }
        r1 = run_ensure_state(payload)
        r2 = run_ensure_state(payload)
        kumi_dir = os.path.join(project, ".kumi")
        if r1.returncode == 0 and r2.returncode == 0 and os.path.isdir(kumi_dir):
            ok("no error when .kumi already exists")
        else:
            bad("no error when .kumi already exists", f"rc1={r1.returncode} rc2={r2.returncode}")
    finally:
        shutil.rmtree(project, ignore_errors=True)


def test_ensure_state_kumi_state_dir_env():
    project = tempfile.mkdtemp()
    state = tempfile.mkdtemp()
    absolute_target = os.path.join(state, "elsewhere")
    try:
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/kumi:yui do it",
            "cwd": project,
        }
        r = run_ensure_state(payload, env_extra={"KUMI_STATE_DIR": absolute_target})
        if r.returncode == 0 and os.path.isdir(absolute_target):
            ok("honours an absolute KUMI_STATE_DIR")
        else:
            bad(
                "honours an absolute KUMI_STATE_DIR",
                f"rc={r.returncode} exists={os.path.isdir(absolute_target)}",
            )
    finally:
        shutil.rmtree(project, ignore_errors=True)
        shutil.rmtree(state, ignore_errors=True)

    project = tempfile.mkdtemp()
    try:
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/kumi:yui do it",
            "cwd": project,
        }
        r = run_ensure_state(payload, env_extra={"KUMI_STATE_DIR": "mystate"})
        target = os.path.join(project, "mystate")
        if r.returncode == 0 and os.path.isdir(target):
            ok("honours a relative KUMI_STATE_DIR")
        else:
            bad(
                "honours a relative KUMI_STATE_DIR",
                f"rc={r.returncode} exists={os.path.isdir(target)}",
            )
    finally:
        shutil.rmtree(project, ignore_errors=True)


def test_ensure_state_git_exclude():
    project = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(project, ".git"))  # a git work tree, no repo needed for this check
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/kumi:yui do it",
            "cwd": project,
        }
        run_ensure_state(payload)
        run_ensure_state(payload)  # run twice: the entry must not duplicate

        exclude_path = os.path.join(project, ".git", "info", "exclude")
        gitignore_path = os.path.join(project, ".gitignore")
        with open(exclude_path, encoding="utf-8") as f:
            lines = [line for line in f.read().splitlines() if line == ".kumi/"]

        if len(lines) == 1 and not os.path.exists(gitignore_path):
            ok("adds .git/info/exclude entry once and never touches .gitignore")
        else:
            bad(
                "adds .git/info/exclude entry once and never touches .gitignore",
                f"entries={lines} gitignore_exists={os.path.exists(gitignore_path)}",
            )
    finally:
        shutil.rmtree(project, ignore_errors=True)


def test_ensure_state_non_string_cwd_falls_back():
    cases = [("int cwd", 12345), ("list cwd", ["a", "b"]), ("null cwd", None)]
    for label, bad_cwd in cases:
        project = tempfile.mkdtemp()
        try:
            payload = {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "/kumi:yui hi",
                "cwd": bad_cwd,
            }
            r = run_ensure_state(payload, proc_cwd=project)
            kumi_dir = os.path.join(project, ".kumi")
            if r.returncode == 0 and os.path.isdir(kumi_dir) and r.stdout == "":
                ok(f"non-string cwd ({label}) exits 0, falls back to the real cwd")
            else:
                bad(
                    f"non-string cwd ({label}) exits 0, falls back to the real cwd",
                    f"rc={r.returncode} exists={os.path.isdir(kumi_dir)} "
                    f"stdout={r.stdout!r} stderr={r.stderr}",
                )
        finally:
            shutil.rmtree(project, ignore_errors=True)


def test_ensure_state_non_utf8_exclude_file():
    project = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(project, ".git", "info"))
        exclude_path = os.path.join(project, ".git", "info", "exclude")
        original = b"already-here\n\xff\xfe not valid utf-8\n"
        with open(exclude_path, "wb") as f:
            f.write(original)

        payload = {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/kumi:yui do it",
            "cwd": project,
        }
        r = run_ensure_state(payload)

        with open(exclude_path, "rb") as f:
            after = f.read()

        added_once = after.count(b".kumi/\n") == 1
        preserved = after.startswith(original)
        msg = "non-UTF-8 .git/info/exclude does not crash, entry added once, bytes preserved"
        if r.returncode == 0 and added_once and preserved:
            ok(msg)
        else:
            bad(
                msg,
                f"rc={r.returncode} added_once={added_once} "
                f"preserved={preserved} stderr={r.stderr}",
            )
    finally:
        shutil.rmtree(project, ignore_errors=True)


def test_ensure_state_git_as_file_skips_exclude():
    project = tempfile.mkdtemp()
    try:
        with open(os.path.join(project, ".git"), "w", encoding="utf-8") as f:
            f.write("gitdir: /somewhere/worktrees/x\n")  # worktree/submodule marker file
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/kumi:yui do it",
            "cwd": project,
        }
        r = run_ensure_state(payload)
        kumi_dir = os.path.join(project, ".kumi")
        exclude_path = os.path.join(project, ".git", "info", "exclude")
        if r.returncode == 0 and os.path.isdir(kumi_dir) and not os.path.exists(exclude_path):
            ok(".git as a file skips the exclude step and still exits 0")
        else:
            bad(
                ".git as a file skips the exclude step and still exits 0",
                f"rc={r.returncode} kumi_exists={os.path.isdir(kumi_dir)} "
                f"exclude_exists={os.path.exists(exclude_path)}",
            )
    finally:
        shutil.rmtree(project, ignore_errors=True)


def main():
    try:
        contract = load_contract(CONTRACT)
    except Exception as e:
        print(f"error: {e}")
        return 2
    test_positive_valid_sample(contract)
    test_negative_cases(contract)
    test_role_kind_devops_before_ops()
    test_chat_ops_workflow_permissions()
    test_report_if_error_prints_github_message()
    test_report_if_error_ignores_expected_status()
    test_merge_gate_decide_state()
    test_merge_gate_description_length_capped()
    test_merge_gate_workflow_permissions()
    test_merge_gate_job_named_apart_from_status_context()
    test_merge_gate_never_checks_out_pr_head()
    test_validate_claude_manifest_job_pins_checksum_safely()
    test_no_emoji_under_github()
    test_all_real_skills_pass()
    test_eval_cases_pass()
    test_agents_up_to_date()
    test_hooks_never_fail()
    test_ensure_state_creates_on_kumi_call()
    test_ensure_state_non_kumi_call_is_noop()
    test_ensure_state_empty_or_malformed_stdin()
    test_ensure_state_idempotent()
    test_ensure_state_kumi_state_dir_env()
    test_ensure_state_git_exclude()
    test_ensure_state_non_string_cwd_falls_back()
    test_ensure_state_non_utf8_exclude_file()
    test_ensure_state_git_as_file_skips_exclude()
    print()
    print(f"{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
