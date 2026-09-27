#!/usr/bin/env python3
"""kumi test suite.
Runs every check the plugin ships with, including that the validator rejects malformed skills."""

import contextlib
import datetime
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
GITHUB_SCRIPTS_DIR = os.path.join(ROOT, ".github", "scripts")
HOOKS_DIR = os.path.join(ROOT, "hooks")
sys.path.insert(0, HERE)
sys.path.insert(0, SCRIPTS_DIR)
sys.path.insert(0, GITHUB_SCRIPTS_DIR)
sys.path.insert(0, HOOKS_DIR)

import capture_memory  # noqa: E402
import chat_commands  # noqa: E402
import restore_memory  # noqa: E402
import strip_stale_approval  # noqa: E402
from _github import report_if_error  # noqa: E402
from build_agents import HOUSE_RULES_PATH, role_kind, shift_headings  # noqa: E402
from merge_gate import MAX_DESCRIPTION_LENGTH, decide_state  # noqa: E402
from validate_skills import CONTRACT, check_skill, load_contract  # noqa: E402

PASS, FAIL = 0, 0

# No automation process may ever produce an emoji.
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
    # "DevOps Specialist" contains "ops", so devops must be checked before process/ops.
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


def test_house_rules_present_in_every_generated_agent():
    # The build shifts headings one level to nest under the host doc; compare the shifted form.
    with open(HOUSE_RULES_PATH, encoding="utf-8") as f:
        rules_text = shift_headings(f.read().rstrip() + "\n")
    heading_line = rules_text.splitlines()[0]
    agents_dir = os.path.join(ROOT, "agents")
    missing = []
    wrong_heading = []
    for fname in sorted(os.listdir(agents_dir)):
        with open(os.path.join(agents_dir, fname), encoding="utf-8") as f:
            content = f.read()
        if rules_text not in content:
            missing.append(fname)
        elif heading_line not in content.splitlines():
            wrong_heading.append(fname)
    name = "config/house_rules.md text appears verbatim in every generated agent"
    if not missing and not wrong_heading:
        ok(name)
    else:
        bad(name, f"missing from: {missing}; wrong heading level in: {wrong_heading}")


def test_house_rules_present_in_yui_skill():
    # yui is hand-maintained, not generated, but nests the rules the same shifted way.
    with open(HOUSE_RULES_PATH, encoding="utf-8") as f:
        rules_text = shift_headings(f.read().rstrip() + "\n")
    heading_line = rules_text.splitlines()[0]
    with open(os.path.join(ROOT, "skills", "yui", "SKILL.md"), encoding="utf-8") as f:
        body = f.read()
    name = "config/house_rules.md text appears verbatim in skills/yui/SKILL.md"
    if rules_text not in body:
        bad(name, "house rules text not found in yui's SKILL.md body")
    elif heading_line not in body.splitlines():
        bad(name, f"heading line {heading_line!r} not present as a whole line (level drift)")
    else:
        ok(name)


def test_build_agents_check_catches_house_rules_drift():
    tmp_root = tempfile.mkdtemp()
    try:
        for sub in ("scripts", "skills", "agents", "config"):
            shutil.copytree(os.path.join(ROOT, sub), os.path.join(tmp_root, sub))
        drifted = os.path.join(tmp_root, "config", "house_rules.md")
        with open(drifted, "a", encoding="utf-8") as f:
            f.write("- A brand-new rule not yet baked into agents/.\n")
        # Untraced: this script is a tmp copy deleted below, so coverage data
        # pointing at it would break "coverage report" after the temp dir is gone.
        env = dict(os.environ)
        env.pop("COVERAGE_PROCESS_START", None)
        env.pop("COVERAGE_PROCESS_CONFIG", None)
        r = subprocess.run(
            [sys.executable, os.path.join(tmp_root, "scripts", "build_agents.py"), "--check"],
            capture_output=True, text=True, env=env,
        )
        name = "build_agents.py --check catches house_rules.md drift"
        if r.returncode == 1 and "out of date" in r.stdout:
            ok(name)
        else:
            bad(name, f"rc={r.returncode} stdout={r.stdout!r} stderr={r.stderr!r}")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_shift_headings_skips_fenced_code_blocks():
    fixture = (
        "# Title\n"
        "\n"
        "Some rule text.\n"
        "\n"
        "```\n"
        "# not a heading, a shell comment\n"
        "```\n"
        "\n"
        "~~~~\n"
        "## also not a heading\n"
        "~~~~\n"
        "\n"
        "## Real subheading\n"
    )
    lines = shift_headings(fixture, by=1).split("\n")
    name = "shift_headings shifts real headings but leaves fenced-block lines untouched"
    # (line index, exact expected line) -- whole-line equality, not substring containment,
    # so a wrong extra "#" cannot hide inside a longer matched string.
    expected = {
        0: "## Title",
        5: "# not a heading, a shell comment",
        9: "## also not a heading",
        12: "### Real subheading",
    }
    mismatches = {i: lines[i] for i, exp in expected.items() if lines[i] != exp}
    if not mismatches:
        ok(name)
    else:
        bad(name, f"expected={expected} got={mismatches}")


def test_yui_skill_does_not_contradict_verify_rule():
    with open(os.path.join(ROOT, "skills", "yui", "SKILL.md"), encoding="utf-8") as f:
        body = f.read()
    replacement = "never redo or second-guess the specialist's own domain judgment"
    name = "yui's SKILL.md drops 'do not verify' and states the narrowed rule instead"
    if "do not verify" not in body.lower() and replacement in body:
        ok(name)
    else:
        bad(
            name,
            f"contains 'do not verify': {'do not verify' in body.lower()}; "
            f"contains narrowed replacement: {replacement in body}",
        )


def test_chat_ops_workflow_permissions():
    # Labeling a PR comment via GITHUB_TOKEN needs both issues:write and pull-requests:write.
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


def test_chat_ops_grants_statuses_write():
    # chat-ops posts the merge-gate status itself after changing a label.
    path = os.path.join(ROOT, ".github", "workflows", "chat-ops.yml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    perms_block = text.split("jobs:", 1)[0]
    name = "chat-ops workflow grants statuses:write"
    if "statuses: write" in perms_block:
        ok(name)
    else:
        bad(name, "missing statuses: write in the top-level permissions block")


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
    # Not a realistic input; confirms an unusual pile-up of hold labels stays within the limit.
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


def test_strip_stale_approval_job_permissions():
    # This job's own permissions: block replaces the workflow-level one, for this job only.
    path = os.path.join(ROOT, ".github", "workflows", "merge-gate.yml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    job_marker = "\n  strip-stale-approval:\n"
    name = "strip-stale-approval job grants only pull-requests:write and statuses:write"
    if job_marker not in text:
        bad(name, "job not found in merge-gate.yml")
        return
    job_text = text[text.index(job_marker) + len(job_marker):]
    next_job = re.search(r"\n  [a-zA-Z0-9_-]+:\n", job_text)
    if next_job:
        job_text = job_text[:next_job.start()]
    required = ("pull-requests: write", "statuses: write")
    missing = [perm for perm in required if perm not in job_text]
    forbidden = ("contents: write", "issues: write")
    over_broad = [perm for perm in forbidden if perm in job_text]
    if missing or over_broad:
        bad(name, f"missing={missing} over_broad={over_broad}")
    else:
        ok(name)


def test_merge_gate_job_named_apart_from_status_context():
    # The job id must differ from the "merge-gate" commit-status context merge_gate.py posts.
    path = os.path.join(ROOT, ".github", "workflows", "merge-gate.yml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    name = "merge-gate job id differs from the merge-gate status context it posts"
    if "merge-gate-status:" in text and "\n  merge-gate:\n" not in text:
        ok(name)
    else:
        bad(name, "job id collides with (or is missing from) the status context name")


def test_merge_gate_never_checks_out_pr_head():
    # pull_request_target's write-capable token must never check out the PR's own code.
    path = os.path.join(ROOT, ".github", "workflows", "merge-gate.yml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    name = "merge-gate never checks out the PR's own head ref"
    if "ref:" not in text:
        ok(name)
    else:
        bad(name, "found an explicit checkout ref in a pull_request_target workflow")


def test_refresh_merge_gate_status_posts_current_state():
    # Must post against the PR's live head sha and labels, not the comment's own event payload.
    pr = {"labels": [{"name": "lgtm"}, {"name": "approved"}], "head": {"sha": "abc123"}}
    with mock.patch("chat_commands.get_pull_request", return_value=(200, pr)) as get_pr, \
            mock.patch("chat_commands.set_commit_status", return_value=(201, {})) as set_status:
        chat_commands.refresh_merge_gate_status("annavetech/kumi", 42)
    name = "refresh_merge_gate_status posts decide_state's result at the PR's current head sha"
    expect_get = mock.call("annavetech/kumi", 42)
    expect_status = mock.call("annavetech/kumi", "abc123", "success", "lgtm and approved; not held")
    if get_pr.call_args == expect_get and set_status.call_args == expect_status:
        ok(name)
    else:
        bad(name, f"get_pr={get_pr.call_args} set_status={set_status.call_args}")


def test_refresh_merge_gate_status_swallows_get_failure():
    with mock.patch("chat_commands.get_pull_request", return_value=(404, None)), \
            mock.patch("chat_commands.set_commit_status") as set_status:
        chat_commands.refresh_merge_gate_status("annavetech/kumi", 42)
    name = "refresh_merge_gate_status never posts a status when the PR fetch fails"
    if not set_status.called:
        ok(name)
    else:
        bad(name, "posted a status despite a failed get_pull_request")


def test_handle_lgtm_refreshes_status_after_label_added():
    with mock.patch("chat_commands.is_authorized", return_value=True), \
            mock.patch("chat_commands.add_labels", return_value=(200, {})), \
            mock.patch("chat_commands.refresh_merge_gate_status") as refresh:
        chat_commands.handle_lgtm("annavetech/kumi", 42, "anna")
    name = "handle_lgtm refreshes the merge-gate status after a successful add_labels"
    if refresh.call_args == mock.call("annavetech/kumi", 42):
        ok(name)
    else:
        bad(name, f"refresh call: {refresh.call_args}")


def test_handle_lgtm_skips_refresh_on_label_failure():
    with mock.patch("chat_commands.is_authorized", return_value=True), \
            mock.patch("chat_commands.add_labels", return_value=(403, {"message": "no"})), \
            mock.patch("chat_commands.refresh_merge_gate_status") as refresh:
        chat_commands.handle_lgtm("annavetech/kumi", 42, "anna")
    name = "handle_lgtm does not refresh the status when add_labels itself failed"
    if not refresh.called:
        ok(name)
    else:
        bad(name, "refresh_merge_gate_status was called despite a failed add_labels")


def test_handle_approve_refreshes_status_after_label_added():
    with mock.patch("chat_commands.is_authorized", return_value=True), \
            mock.patch("chat_commands.add_labels", return_value=(200, {})), \
            mock.patch("chat_commands.refresh_merge_gate_status") as refresh:
        chat_commands.handle_approve("annavetech/kumi", 42, "anna")
    name = "handle_approve refreshes the merge-gate status after a successful add_labels"
    if refresh.call_args == mock.call("annavetech/kumi", 42):
        ok(name)
    else:
        bad(name, f"refresh call: {refresh.call_args}")


def test_handle_approve_skips_refresh_on_label_failure():
    with mock.patch("chat_commands.is_authorized", return_value=True), \
            mock.patch("chat_commands.add_labels", return_value=(403, {"message": "no"})), \
            mock.patch("chat_commands.refresh_merge_gate_status") as refresh:
        chat_commands.handle_approve("annavetech/kumi", 42, "anna")
    name = "handle_approve does not refresh the status when add_labels itself failed"
    if not refresh.called:
        ok(name)
    else:
        bad(name, "refresh_merge_gate_status was called despite a failed add_labels")


def test_handle_hold_refreshes_status_after_label_added():
    # /hold must recompute against the label set including the hold just added.
    with mock.patch("chat_commands.is_authorized", return_value=True), \
            mock.patch("chat_commands.add_labels", return_value=(200, {})), \
            mock.patch("chat_commands.refresh_merge_gate_status") as refresh:
        chat_commands.handle_hold("annavetech/kumi", 42, "anna", "anna")
    name = "handle_hold refreshes the merge-gate status after adding the hold label"
    if refresh.call_args == mock.call("annavetech/kumi", 42):
        ok(name)
    else:
        bad(name, f"refresh call: {refresh.call_args}")


def test_handle_hold_skips_refresh_on_label_failure():
    with mock.patch("chat_commands.is_authorized", return_value=True), \
            mock.patch("chat_commands.add_labels", return_value=(403, {"message": "no"})), \
            mock.patch("chat_commands.refresh_merge_gate_status") as refresh:
        chat_commands.handle_hold("annavetech/kumi", 42, "anna", "anna")
    name = "handle_hold does not refresh the status when add_labels itself failed"
    if not refresh.called:
        ok(name)
    else:
        bad(name, "refresh_merge_gate_status was called despite a failed add_labels")


def test_handle_unhold_refreshes_on_removed_or_already_gone():
    for status in (200, 404):
        with mock.patch("chat_commands.is_authorized", return_value=True), \
                mock.patch("chat_commands.remove_label", return_value=(status, None)), \
                mock.patch("chat_commands.refresh_merge_gate_status") as refresh:
            chat_commands.handle_unhold("annavetech/kumi", 42, "anna", "anna")
        name = f"handle_unhold refreshes the status when remove_label returns {status}"
        if refresh.call_args == mock.call("annavetech/kumi", 42):
            ok(name)
        else:
            bad(name, f"refresh call: {refresh.call_args}")


def test_handle_unhold_skips_refresh_on_label_failure():
    # 404 is tolerated as "already gone", so use a genuine error (403) to exercise the guard.
    with mock.patch("chat_commands.is_authorized", return_value=True), \
            mock.patch("chat_commands.remove_label", return_value=(403, {"message": "no"})), \
            mock.patch("chat_commands.refresh_merge_gate_status") as refresh:
        chat_commands.handle_unhold("annavetech/kumi", 42, "anna", "anna")
    name = "handle_unhold does not refresh the status when remove_label genuinely failed"
    if not refresh.called:
        ok(name)
    else:
        bad(name, "refresh_merge_gate_status was called despite a failed remove_label")


def test_handle_ok_to_test_never_refreshes_status():
    # decide_state never reads ok-to-test/needs-ok-to-test labels.
    with mock.patch("chat_commands.is_authorized", return_value=True), \
            mock.patch("chat_commands.remove_label", return_value=(200, None)), \
            mock.patch("chat_commands.add_labels", return_value=(200, {})), \
            mock.patch("chat_commands.refresh_merge_gate_status") as refresh:
        chat_commands.handle_ok_to_test("annavetech/kumi", 42, "anna", "author")
    name = "handle_ok_to_test never calls refresh_merge_gate_status"
    if not refresh.called:
        ok(name)
    else:
        bad(name, "refresh_merge_gate_status was called from handle_ok_to_test")


def test_strip_stale_approval_removes_lgtm_and_approved():
    with (
        mock.patch("strip_stale_approval.remove_label", return_value=(200, None)) as remove,
        mock.patch("strip_stale_approval.set_commit_status", return_value=(201, {})) as set_status,
    ):
        result = strip_stale_approval.strip_and_report(
            "annavetech/kumi", 42, "def456", {"lgtm", "approved"}
        )
    name = "strip_and_report removes both lgtm and approved when present"
    removed = sorted(c.args[2] for c in remove.call_args_list)
    expect_status = mock.call("annavetech/kumi", "def456", "pending", "Needs approved, lgtm labels")
    if result and removed == ["approved", "lgtm"] and set_status.call_args == expect_status:
        ok(name)
    else:
        bad(name, f"result={result} removed={removed} set_status={set_status.call_args}")


def test_strip_stale_approval_leaves_hold_untouched():
    with (
        mock.patch("strip_stale_approval.remove_label", return_value=(200, None)) as remove,
        mock.patch("strip_stale_approval.set_commit_status", return_value=(201, {})) as set_status,
    ):
        result = strip_stale_approval.strip_and_report(
            "annavetech/kumi", 42, "def456", {"lgtm", "approved", "do-not-merge/hold"}
        )
    name = "strip_and_report never removes a do-not-merge/* hold label"
    removed = [c.args[2] for c in remove.call_args_list]
    hold_status = ("pending", "Blocked by do-not-merge/hold")
    expect_status = mock.call("annavetech/kumi", "def456", *hold_status)
    if result and "do-not-merge/hold" not in removed and set_status.call_args == expect_status:
        ok(name)
    else:
        bad(name, f"removed={removed} set_status={set_status.call_args}")


def test_strip_stale_approval_nothing_to_remove():
    # A push to a PR that only has a hold: nothing to strip.
    with (
        mock.patch("strip_stale_approval.remove_label") as remove,
        mock.patch("strip_stale_approval.set_commit_status", return_value=(201, {})) as set_status,
    ):
        result = strip_stale_approval.strip_and_report(
            "annavetech/kumi", 42, "def456", {"do-not-merge/hold"}
        )
    name = "strip_and_report posts the unchanged hold status when there is nothing to strip"
    hold_status = ("pending", "Blocked by do-not-merge/hold")
    expect_status = mock.call("annavetech/kumi", "def456", *hold_status)
    if result and not remove.called and set_status.call_args == expect_status:
        ok(name)
    else:
        bad(name, f"remove.called={remove.called} set_status={set_status.call_args}")


def test_strip_stale_approval_fails_closed_on_remove_error():
    with mock.patch("strip_stale_approval.remove_label", return_value=(403, {"message": "no"})), \
            mock.patch("strip_stale_approval.set_commit_status") as set_status:
        result = strip_stale_approval.strip_and_report(
            "annavetech/kumi", 42, "def456", {"lgtm"}
        )
    name = "strip_and_report fails closed and posts nothing when a label removal errors"
    if result is False and not set_status.called:
        ok(name)
    else:
        bad(name, f"result={result} set_status.called={set_status.called}")


def test_strip_stale_approval_fails_closed_on_status_post_error():
    with (
        mock.patch("strip_stale_approval.remove_label", return_value=(200, None)),
        mock.patch("strip_stale_approval.set_commit_status", return_value=(403, {"message": "no"})),
    ):
        result = strip_stale_approval.strip_and_report(
            "annavetech/kumi", 42, "def456", {"lgtm"}
        )
    name = "strip_and_report fails closed (returns False) when posting the status itself fails"
    if result is False:
        ok(name)
    else:
        bad(name, f"result={result}")


def run_github_script_without_token(script_name, event):
    """Run a .github/scripts/*.py script with no GITHUB_TOKEN set. Returns CompletedProcess."""
    fd, event_path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(event, f)
    env = dict(os.environ)
    env.pop("GITHUB_TOKEN", None)
    env["GITHUB_EVENT_PATH"] = event_path
    env["GITHUB_REPOSITORY"] = "annavetech/kumi"
    try:
        return subprocess.run(
            [sys.executable, os.path.join(GITHUB_SCRIPTS_DIR, script_name)],
            capture_output=True, text=True, env=env,
        )
    finally:
        os.remove(event_path)


def test_merge_gate_exits_clean_without_token():
    event = {
        "pull_request": {
            "labels": [{"name": "lgtm"}, {"name": "approved"}],
            "head": {"sha": "abc123"},
        }
    }
    r = run_github_script_without_token("merge_gate.py", event)
    name = "merge_gate.py exits 1 with a clear message when GITHUB_TOKEN is missing, no traceback"
    if r.returncode == 1 and "GITHUB_TOKEN" in r.stdout and "Traceback" not in r.stderr:
        ok(name)
    else:
        bad(name, f"rc={r.returncode} stdout={r.stdout!r} stderr={r.stderr!r}")


def test_strip_stale_approval_exits_clean_without_token():
    event = {
        "pull_request": {
            "number": 42,
            "head": {"sha": "def456"},
            "labels": [{"name": "lgtm"}, {"name": "approved"}],
        }
    }
    r = run_github_script_without_token("strip_stale_approval.py", event)
    name = "strip_stale_approval.py exits 1 with a clear message when the token is missing"
    if r.returncode == 1 and "GITHUB_TOKEN" in r.stdout and "Traceback" not in r.stderr:
        ok(name)
    else:
        bad(name, f"rc={r.returncode} stdout={r.stdout!r} stderr={r.stderr!r}")


def test_validate_claude_manifest_job_pins_npm_version_safely():
    # The job installs claude with npm ci, pinned by the lockfile integrity hashes.
    name = "validate-claude-manifest job installs the claude CLI from a pinned npm lockfile"
    problems = []

    ci_path = os.path.join(ROOT, ".github", "workflows", "ci.yml")
    with open(ci_path, encoding="utf-8") as f:
        text = f.read()
    job_marker = "\n  validate-claude-manifest:\n"
    if job_marker not in text:
        bad(name, "job not found in ci.yml")
        return
    job_text = text[text.index(job_marker):]

    forbidden = {
        "curl": r"\bcurl\b",
        "wget": r"\bwget\b",
        "pipe to a shell": r"\|\s*(sh|bash)\b",
        "npx": r"\bnpx\b",
        "bunx": r"\bbunx\b",
        "uvx": r"\buvx\b",
        "pipx run": r"\bpipx\s+run\b",
        "pnpm dlx": r"\bpnpm\s+dlx\b",
        "yarn dlx": r"\byarn\s+dlx\b",
    }
    found = [label for label, pattern in forbidden.items() if re.search(pattern, job_text)]
    if found:
        problems.append(f"forbidden installer(s) found: {', '.join(found)}")
    if "npm ci" not in job_text:
        problems.append("job never runs npm ci")
    if "working-directory: .github/claude-cli" not in job_text:
        problems.append("npm ci does not run with working-directory: .github/claude-cli")
    if "--ignore-scripts" in job_text:
        problems.append(
            "npm ci uses --ignore-scripts, which skips the postinstall that places the binary"
        )

    package_json_path = os.path.join(ROOT, ".github", "claude-cli", "package.json")
    lock_path = os.path.join(ROOT, ".github", "claude-cli", "package-lock.json")
    with open(package_json_path, encoding="utf-8") as f:
        package_json = json.load(f)
    with open(lock_path, encoding="utf-8") as f:
        lock = json.load(f)

    pkg_name = "@anthropic-ai/claude-code"
    version = package_json.get("dependencies", {}).get(pkg_name)
    if not version or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        problems.append(f"package.json does not pin an exact X.Y.Z version, got {version!r}")

    packages = lock.get("packages", {})
    main_pkg = packages.get(f"node_modules/{pkg_name}", {})
    linux_pkg = packages.get(f"node_modules/{pkg_name}-linux-x64", {})
    if main_pkg.get("version") != version:
        problems.append(f"lockfile main package version {main_pkg.get('version')!r} != {version!r}")
    if linux_pkg.get("version") != version:
        problems.append(
            f"lockfile linux-x64 package version {linux_pkg.get('version')!r} != {version!r}"
        )
    for label, pkg in (("main package", main_pkg), ("linux-x64 package", linux_pkg)):
        integrity = pkg.get("integrity", "")
        if not integrity.startswith("sha512-"):
            problems.append(f"{label} integrity does not start with sha512-: {integrity!r}")

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
    # workdir is the subprocess's real cwd, so a hook's os.getcwd() fallback lands here.
    workdir = tempfile.mkdtemp()
    empty = tempfile.mkdtemp(dir=workdir)  # a dir with no .kumi
    git_dir = os.path.join(workdir, ".git", "info")
    os.makedirs(git_dir)
    with open(os.path.join(git_dir, "exclude"), "wb") as f:
        f.write(b"already-here\n\xff\xfe not valid utf-8\n")  # pre-existing non-UTF-8 bytes
    common_inputs = ['', 'not json', '{}', f'{{"cwd":"{empty}"}}']
    # Malformed cwd (int, null, list, dict, empty string) used to raise TypeError in os.path.join.
    malformed_cwd_inputs = [
        '{"cwd":123}',
        '{"cwd":null}',
        '{"cwd":["a"]}',
        '{"cwd":{"a":1}}',
        '{"cwd":""}',
    ]
    # ensure_state needs a real is_kumi_call shape to reach its cwd-handling code at all.
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


# A real subagent transcript's lines never carry a "subagent_type" or "agent" field.
SUBAGENT_TRANSCRIPT_LINES = [
    {
        "parentUuid": None,
        "isSidechain": True,
        "agentId": "aaadd4043fa023033",
        "type": "user",
        "message": {"role": "user", "content": "Task: review hello.py."},
        "uuid": "66d1a116-7361-4963-916a-bca2f203b476",
        "timestamp": "2026-09-21T11:44:05.578Z",
        "cwd": "/private/tmp/kumi-memory-check",
        "sessionId": "afe6c14e-5cb6-49d8-a8c9-3ad2aca8758c",
        "version": "2.1.278",
    },
    {
        "parentUuid": "66d1a116-7361-4963-916a-bca2f203b476",
        "isSidechain": True,
        "agentId": "aaadd4043fa023033",
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": "No findings.",
            "usage": {
                "input_tokens": 14,
                "output_tokens": 1290,
                "cache_read_input_tokens": 199343,
                "cache_creation_input_tokens": 62535,
            },
        },
        "uuid": "77e2b227-8472-5a74-a27d-cca3f214c587",
        "timestamp": "2026-09-21T11:44:09.905Z",
        "cwd": "/private/tmp/kumi-memory-check",
        "sessionId": "afe6c14e-5cb6-49d8-a8c9-3ad2aca8758c",
        "version": "2.1.278",
    },
]


def run_record_metrics(payload_obj, proc_cwd=None):
    """Run record_metrics.py with a JSON payload on stdin, return CompletedProcess."""
    stdin = json.dumps(payload_obj) if payload_obj is not None else ""
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "hooks", "record_metrics.py")],
        input=stdin, capture_output=True, text=True, cwd=proc_cwd,
    )


def test_record_metrics_subagent_agent_name():
    # Must resolve the specialist name from the payload's "agent_type" even when
    # the transcript itself never mentions the agent's name.
    project = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(project, ".kumi"))
        transcript_path = os.path.join(project, "agent-aaadd4043fa023033.jsonl")
        with open(transcript_path, "w", encoding="utf-8") as f:
            for line in SUBAGENT_TRANSCRIPT_LINES:
                f.write(json.dumps(line) + "\n")

        payload = {
            "hook_event_name": "SubagentStop",
            "stop_hook_active": False,
            "agent_id": "aaadd4043fa023033",
            "agent_transcript_path": transcript_path,
            "agent_type": "kumi:ivo",
            "session_id": "afe6c14e-5cb6-49d8-a8c9-3ad2aca8758c",
            "transcript_path": transcript_path,
            "cwd": project,
        }
        r = run_record_metrics(payload, proc_cwd=project)

        agents_path = os.path.join(project, ".kumi", "metrics", "agents.jsonl")
        record = None
        if os.path.isfile(agents_path):
            with open(agents_path, encoding="utf-8") as f:
                lines = [line for line in f if line.strip()]
            if lines:
                record = json.loads(lines[-1])

        msg = "record_metrics resolves the real specialist name from agent_type, not \"unknown\""
        if r.returncode == 0 and record is not None and record.get("agent") == "ivo":
            ok(msg)
        else:
            bad(
                msg,
                f"rc={r.returncode} record={record!r} stderr={r.stderr}",
            )
    finally:
        shutil.rmtree(project, ignore_errors=True)


def run_restore_memory(payload_obj, proc_cwd=None):
    """Run restore_memory.py with a JSON payload on stdin, return CompletedProcess."""
    stdin = json.dumps(payload_obj) if payload_obj is not None else ""
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "hooks", "restore_memory.py")],
        input=stdin, capture_output=True, text=True, cwd=proc_cwd,
    )


def restore_memory_context(project):
    payload = {"hook_event_name": "SessionStart", "cwd": project}
    r = run_restore_memory(payload, proc_cwd=project)
    context = ""
    if r.stdout.strip():
        context = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    return r, context


def test_restore_memory_does_not_split_on_body_headings():
    # Two body headings, so the old "last 3 fragments" split drops the first real
    # entry entirely; the new split must still keep both real entries in full.
    project = tempfile.mkdtemp()
    try:
        memory_dir = os.path.join(project, ".kumi", "memory")
        os.makedirs(memory_dir)
        log_text = (
            "# kumi memory\n\n"
            "Append-only record of finished work.\n"
            "\n## 2026-09-14 11:23:01\n"
            "\nSome earlier entry text.\n"
            "\n## Scope - all 15 items required\n"
            "\nScope body text.\n"
            "\n## What eks-anywhere actually does\n"
            "\nMore scope body.\n"
            "\n## 2026-09-14 11:36:07\n"
            "\nSecond entry text.\n"
        )
        with open(os.path.join(memory_dir, "log.md"), "w", encoding="utf-8") as f:
            f.write(log_text)
        r, context = restore_memory_context(project)
        embedded = (
            "Some earlier entry text.\n\n"
            "## Scope - all 15 items required\n\n"
            "Scope body text.\n\n"
            "## What eks-anywhere actually does\n\n"
            "More scope body."
        )
        name = "restore_memory keeps a body heading inside an entry, not as its own boundary"
        if (
            r.returncode == 0
            and "## 2026-09-14 11:23:01" in context
            and "## 2026-09-14 11:36:07" in context
            and embedded in context
        ):
            ok(name)
        else:
            bad(name, f"rc={r.returncode} context={context!r} stderr={r.stderr}")
    finally:
        shutil.rmtree(project, ignore_errors=True)


def test_restore_memory_never_truncates_current_handoff():
    cases = [
        ("handoff over the combined cap stays whole", 6000, True),
        ("handoff over the sane ceiling is cut with a pointer, never silently", 50000, False),
    ]
    for label, size, expect_verbatim in cases:
        project = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(project, ".kumi"))
            handoff_text = "x" * size
            with open(os.path.join(project, ".kumi", "handoff.md"), "w", encoding="utf-8") as f:
                f.write(handoff_text)
            r, context = restore_memory_context(project)
            if expect_verbatim:
                condition = (
                    r.returncode == 0 and handoff_text in context and "[truncated]" not in context
                )
            else:
                condition = (
                    r.returncode == 0
                    and handoff_text not in context
                    and "read .kumi/handoff.md directly" in context
                    and "[truncated]" not in context
                )
            if condition:
                ok(label)
            else:
                bad(label, f"rc={r.returncode} context_len={len(context)} stderr={r.stderr}")
        finally:
            shutil.rmtree(project, ignore_errors=True)


def test_restore_memory_drops_oldest_whole_entries_over_budget():
    # A small handoff leaves most of the budget for memory; three large entries do not
    # all fit, so the oldest whole entry is dropped rather than any entry cut mid-body.
    project = tempfile.mkdtemp()
    try:
        memory_dir = os.path.join(project, ".kumi", "memory")
        os.makedirs(memory_dir)
        body = "x" * (restore_memory.MAX_CONTEXT_CHARS // 3)
        log_text = "# kumi memory\n\n" + "".join(
            f"\n## 2026-0{i}-01 00:00:0{i}\n\n{body}\n" for i in (1, 2, 3)
        )
        with open(os.path.join(memory_dir, "log.md"), "w", encoding="utf-8") as f:
            f.write(log_text)
        r, context = restore_memory_context(project)
        name = "restore_memory drops the oldest whole entry, never a partial one, over budget"
        if (
            r.returncode == 0
            and "## 2026-03-01 00:00:03" in context
            and "## 2026-01-01 00:00:01" not in context
        ):
            ok(name)
        else:
            bad(name, f"rc={r.returncode} context_len={len(context)} stderr={r.stderr}")
    finally:
        shutil.rmtree(project, ignore_errors=True)


def test_resolve_restore_entries_handles_bad_zero_and_negative():
    cases = [
        ({"memory": {"restore_entries": 5}}, 5, "a good value passes through"),
        ({"memory": {"restore_entries": 0}}, 0, "zero means no entries, not the default"),
        (
            {"memory": {"restore_entries": -1}},
            restore_memory.DEFAULT_RESTORE_ENTRIES,
            "negative falls back to the default",
        ),
        (
            {"memory": {"restore_entries": "nope"}},
            restore_memory.DEFAULT_RESTORE_ENTRIES,
            "non-numeric falls back to the default",
        ),
        (
            {"memory": {"restore_entries": None}},
            restore_memory.DEFAULT_RESTORE_ENTRIES,
            "null falls back to the default",
        ),
        (
            {"memory": {}},
            restore_memory.DEFAULT_RESTORE_ENTRIES,
            "missing key falls back to the default",
        ),
    ]
    for cfg, expected, label in cases:
        got = restore_memory.resolve_restore_entries(cfg)
        name = f"resolve_restore_entries: {label}"
        if got == expected:
            ok(name)
        else:
            bad(name, f"cfg={cfg} got={got} expected={expected}")


def run_capture_memory(payload_obj, proc_cwd=None):
    """Run capture_memory.py with a JSON payload on stdin, return CompletedProcess."""
    stdin = json.dumps(payload_obj) if payload_obj is not None else ""
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "hooks", "capture_memory.py")],
        input=stdin, capture_output=True, text=True, cwd=proc_cwd,
    )


def test_capture_memory_rotates_when_log_exceeds_threshold():
    project = tempfile.mkdtemp()
    try:
        kumi_dir = os.path.join(project, ".kumi")
        memory_dir = os.path.join(kumi_dir, "memory")
        os.makedirs(memory_dir)
        with open(os.path.join(kumi_dir, "handoff.md"), "w", encoding="utf-8") as f:
            f.write("work in progress")

        with open(os.path.join(ROOT, "config", "runtime.json"), encoding="utf-8") as f:
            threshold = json.load(f)["memory"]["rotate_entries"]

        seeded = threshold - 1
        entries = "".join(
            f"\n## 2026-01-01 00:{i // 60:02d}:{i % 60:02d}\n\nold entry {i}\n"
            for i in range(seeded)
        )
        with open(os.path.join(memory_dir, "log.md"), "w", encoding="utf-8") as f:
            f.write("# kumi memory\n\nAppend-only record.\n" + entries)

        payload = {"hook_event_name": "Stop", "cwd": project}
        r = run_capture_memory(payload, proc_cwd=project)

        archives = [
            n for n in os.listdir(memory_dir)
            if n.startswith("log.") and n != "log.md" and n.endswith(".md")
        ]
        log_path = os.path.join(memory_dir, "log.md")
        remaining = 0
        if os.path.isfile(log_path):
            with open(log_path, encoding="utf-8") as f:
                remaining = len(re.findall(r"\n## \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\n", f.read()))

        name = "capture_memory rotates the oldest entries into an archive once the log fills up"
        if r.returncode == 0 and archives and remaining < threshold:
            ok(name)
        else:
            bad(
                name,
                f"rc={r.returncode} archives={archives} remaining={remaining} "
                f"threshold={threshold} stderr={r.stderr}",
            )
    finally:
        shutil.rmtree(project, ignore_errors=True)


def test_resolve_rotate_entries_handles_bad_zero_and_negative():
    cases = [
        ({"memory": {"rotate_entries": 100}}, 100, "a good value passes through"),
        (
            {"memory": {"rotate_entries": 0}},
            capture_memory.DEFAULT_ROTATE_ENTRIES,
            "zero falls back to the default",
        ),
        (
            {"memory": {"rotate_entries": -5}},
            capture_memory.DEFAULT_ROTATE_ENTRIES,
            "negative falls back to the default",
        ),
        (
            {"memory": {"rotate_entries": "nope"}},
            capture_memory.DEFAULT_ROTATE_ENTRIES,
            "non-numeric falls back to the default",
        ),
        (
            {"memory": {"rotate_entries": None}},
            capture_memory.DEFAULT_ROTATE_ENTRIES,
            "null falls back to the default",
        ),
        (
            {"memory": {}},
            capture_memory.DEFAULT_ROTATE_ENTRIES,
            "missing key falls back to the default",
        ),
    ]
    for cfg, expected, label in cases:
        got = capture_memory.resolve_rotate_entries(cfg)
        name = f"resolve_rotate_entries: {label}"
        if got == expected:
            ok(name)
        else:
            bad(name, f"cfg={cfg} got={got} expected={expected}")


def test_capture_memory_appends_second_rotation_onto_same_dated_archive():
    project = tempfile.mkdtemp()
    try:
        kumi_dir = os.path.join(project, ".kumi")
        memory_dir = os.path.join(kumi_dir, "memory")
        os.makedirs(memory_dir)

        with open(os.path.join(ROOT, "config", "runtime.json"), encoding="utf-8") as f:
            threshold = json.load(f)["memory"]["rotate_entries"]

        def seed_log(day):
            seeded = threshold - 1
            entries = "".join(
                f"\n## 2026-01-{day:02d} 00:{i // 60:02d}:{i % 60:02d}\n\nold entry {i}\n"
                for i in range(seeded)
            )
            with open(os.path.join(memory_dir, "log.md"), "w", encoding="utf-8") as f:
                f.write("# kumi memory\n\nAppend-only record.\n" + entries)

        with open(os.path.join(kumi_dir, "handoff.md"), "w", encoding="utf-8") as f:
            f.write("first rotation")
        seed_log(1)
        r1 = run_capture_memory({"hook_event_name": "Stop", "cwd": project}, proc_cwd=project)

        archive_path = os.path.join(memory_dir, f"log.{datetime.date.today().isoformat()}.md")
        first_size = os.path.getsize(archive_path) if os.path.isfile(archive_path) else 0

        with open(os.path.join(kumi_dir, "handoff.md"), "w", encoding="utf-8") as f:
            f.write("second rotation, different handoff")
        seed_log(2)
        r2 = run_capture_memory({"hook_event_name": "Stop", "cwd": project}, proc_cwd=project)

        second_size = os.path.getsize(archive_path) if os.path.isfile(archive_path) else -1

        name = "capture_memory appends a same-day second rotation onto the existing dated archive"
        if (
            r1.returncode == 0 and r2.returncode == 0
            and first_size > 0 and second_size > first_size
        ):
            ok(name)
        else:
            bad(
                name,
                f"rc1={r1.returncode} rc2={r2.returncode} first_size={first_size} "
                f"second_size={second_size} stderr1={r1.stderr} stderr2={r2.stderr}",
            )
    finally:
        shutil.rmtree(project, ignore_errors=True)


def test_capture_memory_lock_serializes_concurrent_holders():
    memory_dir = tempfile.mkdtemp()
    try:
        active = []
        overlap = []
        guard = threading.Lock()

        def worker():
            with capture_memory._locked(memory_dir):
                with guard:
                    active.append(1)
                    if len(active) > 1:
                        overlap.append(True)
                time.sleep(0.03)
                with guard:
                    active.pop()

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        name = "capture_memory._locked lets only one holder in at a time"
        if not overlap and not os.path.exists(os.path.join(memory_dir, ".lock")):
            ok(name)
        else:
            bad(name, f"overlap={overlap}")
    finally:
        shutil.rmtree(memory_dir, ignore_errors=True)


def test_capture_memory_lock_reclaims_a_stale_lock():
    memory_dir = tempfile.mkdtemp()
    try:
        lock_path = os.path.join(memory_dir, ".lock")
        with open(lock_path, "w", encoding="utf-8"):
            pass
        old = time.time() - 120
        os.utime(lock_path, (old, old))

        acquired = []
        with capture_memory._locked(memory_dir, timeout=2.0, stale_after=1.0):
            acquired.append(True)

        name = "capture_memory._locked reclaims a lock left behind by a crashed hook"
        if acquired and not os.path.exists(lock_path):
            ok(name)
        else:
            bad(name, f"acquired={acquired} lock_exists={os.path.exists(lock_path)}")
    finally:
        shutil.rmtree(memory_dir, ignore_errors=True)


def test_capture_memory_lock_times_out_without_blocking_forever():
    memory_dir = tempfile.mkdtemp()
    try:
        lock_path = os.path.join(memory_dir, ".lock")
        with open(lock_path, "w", encoding="utf-8"):
            pass  # freshly held, not stale, so this must not be reclaimed

        name = "capture_memory._locked gives up after its timeout instead of blocking forever"
        try:
            with capture_memory._locked(memory_dir, timeout=0.2, stale_after=60.0):
                pass
            bad(name, "lock was acquired despite a live holder")
        except TimeoutError:
            ok(name)
    finally:
        shutil.rmtree(memory_dir, ignore_errors=True)


def test_capture_memory_fails_open_when_lock_is_held():
    project = tempfile.mkdtemp()
    try:
        kumi_dir = os.path.join(project, ".kumi")
        memory_dir = os.path.join(kumi_dir, "memory")
        os.makedirs(memory_dir)
        with open(os.path.join(kumi_dir, "handoff.md"), "w", encoding="utf-8") as f:
            f.write("work in progress")
        # Simulates another hook currently mid-write.
        with open(os.path.join(memory_dir, ".lock"), "w", encoding="utf-8"):
            pass

        payload = {"hook_event_name": "Stop", "cwd": project}
        r = run_capture_memory(payload, proc_cwd=project)

        log_path = os.path.join(memory_dir, "log.md")
        name = "capture_memory exits 0 and writes nothing when another run holds the lock"
        if r.returncode == 0 and not os.path.isfile(log_path):
            ok(name)
        else:
            bad(name, f"rc={r.returncode} log_exists={os.path.isfile(log_path)} stderr={r.stderr}")
    finally:
        shutil.rmtree(project, ignore_errors=True)


def test_capture_memory_lock_release_never_removes_a_lock_it_no_longer_owns():
    memory_dir = tempfile.mkdtemp()
    try:
        lock_path = os.path.join(memory_dir, ".lock")
        cm1 = capture_memory._locked(memory_dir, timeout=2.0, stale_after=1.0)
        cm1.__enter__()  # holder 1 acquires

        old = time.time() - 120
        os.utime(lock_path, (old, old))  # make it look abandoned to a second holder

        cm2 = capture_memory._locked(memory_dir, timeout=2.0, stale_after=1.0)
        cm2.__enter__()  # holder 2 reclaims the stale lock, writes its own token
        with open(lock_path, encoding="utf-8") as f:
            owner_token = f.read()

        cm1.__exit__(None, None, None)  # holder 1's release must not touch holder 2's lock

        still_there = os.path.isfile(lock_path)
        current_token = None
        if still_there:
            with open(lock_path, encoding="utf-8") as f:
                current_token = f.read()

        name = "capture_memory._locked release does not remove a lock now owned by another holder"
        if still_there and current_token == owner_token:
            ok(name)
        else:
            bad(
                name,
                f"still_there={still_there} current_token={current_token} "
                f"owner_token={owner_token}",
            )

        cm2.__exit__(None, None, None)
    finally:
        shutil.rmtree(memory_dir, ignore_errors=True)


def test_capture_memory_repeated_remove_failure_does_not_duplicate_archive():
    project = tempfile.mkdtemp()
    try:
        kumi_dir = os.path.join(project, ".kumi")
        memory_dir = os.path.join(kumi_dir, "memory")
        os.makedirs(memory_dir)
        with open(os.path.join(kumi_dir, "handoff.md"), "w", encoding="utf-8") as f:
            f.write("work in progress")

        with open(os.path.join(ROOT, "config", "runtime.json"), encoding="utf-8") as f:
            threshold = json.load(f)["memory"]["rotate_entries"]

        seeded = threshold - 1
        entries = "".join(
            f"\n## 2026-01-01 00:{i // 60:02d}:{i % 60:02d}\n\nold entry {i}\n"
            for i in range(seeded)
        )
        log_path = os.path.join(memory_dir, "log.md")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("# kumi memory\n\nAppend-only record.\n" + entries)

        archive_path = os.path.join(memory_dir, f"log.{datetime.date.today().isoformat()}.md")
        payload = {"hook_event_name": "Stop", "cwd": project}
        real_remove = os.remove

        def guarded_remove(path, *a, **kw):
            if os.path.abspath(path) == os.path.abspath(log_path):
                raise OSError("simulated: file held open")
            return real_remove(path, *a, **kw)

        def archive_size():
            return os.path.getsize(archive_path) if os.path.isfile(archive_path) else -1

        with mock.patch("os.remove", side_effect=guarded_remove):
            with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))):
                capture_memory.main()
            size_after_first = archive_size()

            with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))):
                capture_memory.main()
            size_after_second = archive_size()

        name = "capture_memory does not duplicate the archive when removing the log keeps failing"
        if size_after_first > 0 and size_after_second == size_after_first:
            ok(name)
        else:
            bad(name, f"size_after_first={size_after_first} size_after_second={size_after_second}")
    finally:
        shutil.rmtree(project, ignore_errors=True)


def run_ensure_state(payload_obj, env_extra=None, proc_cwd=None):
    """Run ensure_state.py with a JSON payload on stdin; proc_cwd is the subprocess's cwd."""
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


def test_ensure_state_anchors_to_repo_root_from_subdirectory():
    project = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(project, ".git"))
        deep = os.path.join(project, "decisions", "mart", "sub")
        os.makedirs(deep)
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/kumi:yui do it",
            "cwd": deep,
        }
        r = run_ensure_state(payload)

        root_kumi = os.path.join(project, ".kumi")
        deep_kumi = os.path.join(deep, ".kumi")
        exclude_path = os.path.join(project, ".git", "info", "exclude")
        exclude_has_entry = False
        if os.path.isfile(exclude_path):
            with open(exclude_path, encoding="utf-8") as f:
                exclude_has_entry = ".kumi/" in f.read().splitlines()

        msg = "state anchors to the repo root, not a subdirectory kumi was invoked from"
        if (
            r.returncode == 0
            and os.path.isdir(root_kumi)
            and not os.path.isdir(deep_kumi)
            and exclude_has_entry
        ):
            ok(msg)
        else:
            bad(
                msg,
                f"rc={r.returncode} root_kumi={os.path.isdir(root_kumi)} "
                f"deep_kumi={os.path.isdir(deep_kumi)} exclude={exclude_has_entry}",
            )
    finally:
        shutil.rmtree(project, ignore_errors=True)


def test_ensure_state_reuses_existing_ancestor_kumi():
    project = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(project, ".git"))
        os.makedirs(os.path.join(project, ".kumi"))
        nested_cwd = os.path.join(project, ".kumi", "decisions", "mart")
        os.makedirs(nested_cwd)
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/kumi:yui do it",
            "cwd": nested_cwd,
        }
        r = run_ensure_state(payload)

        nested_kumi = os.path.join(nested_cwd, ".kumi")
        msg = "reuses an existing ancestor .kumi instead of nesting a new one"
        if r.returncode == 0 and not os.path.isdir(nested_kumi):
            ok(msg)
        else:
            bad(msg, f"rc={r.returncode} nested_kumi_exists={os.path.isdir(nested_kumi)}")
    finally:
        shutil.rmtree(project, ignore_errors=True)


def test_ensure_state_resolves_symlinked_ancestor():
    # outside/.kumi is an unrelated project's state dir. Reached via a raw (unresolved)
    # path, walking above the symlink lands in outside's own ancestry and picks it up
    # by mistake; realpath must resolve the symlink first so the walk stays inside real_project.
    real_project = tempfile.mkdtemp()
    outside = tempfile.mkdtemp()
    link = os.path.join(outside, "link")
    try:
        os.makedirs(os.path.join(real_project, ".git"))
        os.makedirs(os.path.join(real_project, "sub"))
        os.makedirs(os.path.join(outside, ".kumi"))
        os.symlink(real_project, link)
        cwd = os.path.join(link, "sub")
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/kumi:yui do it",
            "cwd": cwd,
        }
        r = run_ensure_state(payload)

        root_kumi = os.path.join(real_project, ".kumi")
        exclude_path = os.path.join(real_project, ".git", "info", "exclude")
        exclude_has_entry = False
        if os.path.isfile(exclude_path):
            with open(exclude_path, encoding="utf-8") as f:
                exclude_has_entry = ".kumi/" in f.read().splitlines()

        msg = "resolves a symlinked ancestor instead of reusing an unrelated project's .kumi"
        if r.returncode == 0 and os.path.isdir(root_kumi) and exclude_has_entry:
            ok(msg)
        else:
            bad(
                msg,
                f"rc={r.returncode} root_kumi={os.path.isdir(root_kumi)} "
                f"exclude={exclude_has_entry}",
            )
    finally:
        shutil.rmtree(real_project, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)


def test_ensure_state_git_root_wins_over_stray_kumi_above():
    # A stray .kumi above the repo's own .git must never hijack the repo; the walk
    # stops at the nearest .git, so the anchor stays the repo root.
    outside = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(outside, ".kumi"))
        project = os.path.join(outside, "repo")
        os.makedirs(os.path.join(project, ".git"))
        deep = os.path.join(project, "decisions", "mart", "sub")
        os.makedirs(deep)
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/kumi:yui do it",
            "cwd": deep,
        }
        r = run_ensure_state(payload)

        root_kumi = os.path.join(project, ".kumi")
        stray_kumi = os.path.join(outside, ".kumi")
        exclude_path = os.path.join(project, ".git", "info", "exclude")
        exclude_has_entry = False
        if os.path.isfile(exclude_path):
            with open(exclude_path, encoding="utf-8") as f:
                exclude_has_entry = ".kumi/" in f.read().splitlines()

        msg = "a stray .kumi above the repo root never hijacks the repo's own .git anchor"
        if (
            r.returncode == 0
            and os.path.isdir(root_kumi)
            and not os.listdir(stray_kumi)
            and exclude_has_entry
        ):
            ok(msg)
        else:
            bad(
                msg,
                f"rc={r.returncode} root_kumi={os.path.isdir(root_kumi)} "
                f"stray_kumi_contents={os.listdir(stray_kumi)} exclude={exclude_has_entry}",
            )
    finally:
        shutil.rmtree(outside, ignore_errors=True)


def test_ensure_state_kumi_state_dir_relative_anchors_to_repo_root():
    project = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(project, ".git"))
        deep = os.path.join(project, "decisions", "mart")
        os.makedirs(deep)
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/kumi:yui do it",
            "cwd": deep,
        }
        r = run_ensure_state(payload, env_extra={"KUMI_STATE_DIR": "mystate"})
        target = os.path.join(project, "mystate")
        nested = os.path.join(deep, "mystate")
        msg = "a relative KUMI_STATE_DIR anchors to the repo root, not the subdirectory"
        if r.returncode == 0 and os.path.isdir(target) and not os.path.isdir(nested):
            ok(msg)
        else:
            bad(
                msg,
                f"rc={r.returncode} target={os.path.isdir(target)} nested={os.path.isdir(nested)}",
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
    test_house_rules_present_in_every_generated_agent()
    test_house_rules_present_in_yui_skill()
    test_build_agents_check_catches_house_rules_drift()
    test_shift_headings_skips_fenced_code_blocks()
    test_yui_skill_does_not_contradict_verify_rule()
    test_chat_ops_workflow_permissions()
    test_chat_ops_grants_statuses_write()
    test_report_if_error_prints_github_message()
    test_report_if_error_ignores_expected_status()
    test_merge_gate_decide_state()
    test_merge_gate_description_length_capped()
    test_merge_gate_workflow_permissions()
    test_strip_stale_approval_job_permissions()
    test_merge_gate_job_named_apart_from_status_context()
    test_merge_gate_never_checks_out_pr_head()
    test_refresh_merge_gate_status_posts_current_state()
    test_refresh_merge_gate_status_swallows_get_failure()
    test_handle_lgtm_refreshes_status_after_label_added()
    test_handle_lgtm_skips_refresh_on_label_failure()
    test_handle_approve_refreshes_status_after_label_added()
    test_handle_approve_skips_refresh_on_label_failure()
    test_handle_hold_refreshes_status_after_label_added()
    test_handle_hold_skips_refresh_on_label_failure()
    test_handle_unhold_refreshes_on_removed_or_already_gone()
    test_handle_unhold_skips_refresh_on_label_failure()
    test_handle_ok_to_test_never_refreshes_status()
    test_strip_stale_approval_removes_lgtm_and_approved()
    test_strip_stale_approval_leaves_hold_untouched()
    test_strip_stale_approval_nothing_to_remove()
    test_strip_stale_approval_fails_closed_on_remove_error()
    test_strip_stale_approval_fails_closed_on_status_post_error()
    test_merge_gate_exits_clean_without_token()
    test_strip_stale_approval_exits_clean_without_token()
    test_validate_claude_manifest_job_pins_npm_version_safely()
    test_no_emoji_under_github()
    test_all_real_skills_pass()
    test_eval_cases_pass()
    test_agents_up_to_date()
    test_hooks_never_fail()
    test_restore_memory_does_not_split_on_body_headings()
    test_restore_memory_never_truncates_current_handoff()
    test_restore_memory_drops_oldest_whole_entries_over_budget()
    test_resolve_restore_entries_handles_bad_zero_and_negative()
    test_capture_memory_rotates_when_log_exceeds_threshold()
    test_resolve_rotate_entries_handles_bad_zero_and_negative()
    test_capture_memory_appends_second_rotation_onto_same_dated_archive()
    test_capture_memory_lock_serializes_concurrent_holders()
    test_capture_memory_lock_reclaims_a_stale_lock()
    test_capture_memory_lock_times_out_without_blocking_forever()
    test_capture_memory_fails_open_when_lock_is_held()
    test_capture_memory_lock_release_never_removes_a_lock_it_no_longer_owns()
    test_capture_memory_repeated_remove_failure_does_not_duplicate_archive()
    test_record_metrics_subagent_agent_name()
    test_ensure_state_creates_on_kumi_call()
    test_ensure_state_non_kumi_call_is_noop()
    test_ensure_state_empty_or_malformed_stdin()
    test_ensure_state_idempotent()
    test_ensure_state_kumi_state_dir_env()
    test_ensure_state_git_exclude()
    test_ensure_state_non_string_cwd_falls_back()
    test_ensure_state_non_utf8_exclude_file()
    test_ensure_state_git_as_file_skips_exclude()
    test_ensure_state_anchors_to_repo_root_from_subdirectory()
    test_ensure_state_reuses_existing_ancestor_kumi()
    test_ensure_state_resolves_symlinked_ancestor()
    test_ensure_state_git_root_wins_over_stray_kumi_above()
    test_ensure_state_kumi_state_dir_relative_anchors_to_repo_root()
    print()
    print(f"{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
