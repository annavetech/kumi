"""Shared GitHub REST API helper for kumi's repo-automation scripts.
Requests go through the gh CLI, which handles authentication itself."""

import json
import re
import subprocess
import sys
import urllib.parse

# `gh api --include` prints the status line and headers, a blank line, then the body.
RESPONSE_HEAD = re.compile(rb"HTTP/\S+ (\d{3})[^\n]*\n(?:[^\r\n]+\r?\n)*\r?\n")


def github_request(method, path, body=None):
    """Call the GitHub REST API. Returns (status, json_or_None); non-2xx is returned, not raised."""
    args = [
        "gh", "api", "--include", "--method", method,
        "-H", "Accept: application/vnd.github+json",
        "-H", "X-GitHub-Api-Version: 2022-11-28",
    ]
    data = b""
    if body is not None:
        args += ["--input", "-"]
        data = json.dumps(body).encode("utf-8")
    args.append(path)

    try:
        result = subprocess.run(args, input=data, capture_output=True, check=False, timeout=60)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"gh api {method} {path}: no HTTP response: timed out") from None
    head = RESPONSE_HEAD.match(result.stdout)
    if head is None:
        detail = " ".join(result.stderr.decode("utf-8", "replace").split())
        raise RuntimeError(f"gh api {method} {path}: no HTTP response: {detail}")
    status = int(head.group(1))
    raw = result.stdout[head.end():]

    if not raw.strip():
        return status, None
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, None


def add_labels(repo, number, labels):
    """Add one or more labels to an issue or PR. Returns (status, json)."""
    return github_request("POST", f"/repos/{repo}/issues/{number}/labels", {"labels": labels})


def remove_label(repo, number, label):
    """Remove a label from an issue or PR. Tolerates the label already being gone (404)."""
    quoted = urllib.parse.quote(label, safe="")
    status, response = github_request(
        "DELETE", f"/repos/{repo}/issues/{number}/labels/{quoted}"
    )
    if status == 404:
        return 404, None
    return status, response


def get_pull_request(repo, number):
    """Fetch a pull request's current state. Returns (status, json_or_None)."""
    return github_request("GET", f"/repos/{repo}/pulls/{number}")


def post_comment(repo, number, body):
    """Post a new comment on an issue or PR."""
    return github_request("POST", f"/repos/{repo}/issues/{number}/comments", {"body": body})


def set_commit_status(repo, sha, state, description, context="merge-gate"):
    """Post a commit status (description max 140 chars). Returns (status, json)."""
    return github_request(
        "POST",
        f"/repos/{repo}/statuses/{sha}",
        {"state": state, "description": description, "context": context},
    )


def add_assignees(repo, number, assignees):
    """Assign one or more accounts to an issue or PR."""
    return github_request(
        "POST", f"/repos/{repo}/issues/{number}/assignees", {"assignees": assignees}
    )


def actor_permission(repo, username):
    """Return username's permission on repo: "admin", "write", "read", or "none"."""
    status, response = github_request(
        "GET", f"/repos/{repo}/collaborators/{username}/permission"
    )
    if status != 200 or not isinstance(response, dict):
        return "none"
    return response.get("permission", "none")


def is_authorized(repo, username):
    """Return True if username can push to repo (admin or write permission)."""
    return actor_permission(repo, username) in ("admin", "write")


def report_if_error(context, status, body=None, ignore=()):
    """Print a non-2xx status and error message to stderr; ignore lists codes to skip."""
    if status not in ignore and not (200 <= status < 300):
        message = body.get("message") if isinstance(body, dict) else None
        if message:
            print(f"{context}: unexpected status {status}: {message}", file=sys.stderr)
        else:
            print(f"{context}: unexpected status {status}", file=sys.stderr)
