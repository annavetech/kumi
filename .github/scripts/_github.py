"""Shared GitHub REST API helper for kumi's repo-automation scripts.
GITHUB_TOKEN is read from the environment and never logged or printed."""

import json
import os
import sys
import urllib.error
import urllib.request

API_ROOT = "https://api.github.com"


def github_request(method, path, body=None):
    """Call the GitHub REST API. Returns (status, json_or_None); non-2xx is returned, not raised."""
    url = f"{API_ROOT}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        request.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(request) as response:
            status = response.getcode()
            raw = response.read()
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read()

    if not raw:
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
    status, response = github_request(
        "DELETE", f"/repos/{repo}/issues/{number}/labels/{label}"
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
