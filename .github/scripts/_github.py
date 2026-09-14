"""Shared GitHub REST API helper for kumi's repo-automation scripts.

Standard library only (json, os, urllib.request, urllib.error) — see
.kumi/decisions/kai/repo-automation.md §0.2: this repo's custom GitHub-API
logic stays in stdlib Python rather than pulling in actions/github-script's
Node/JS trust boundary.

GITHUB_TOKEN is read from the environment and sent only as the value of the
Authorization header. It is never logged, printed, or included in an
exception message.
"""

import json
import os
import sys
import urllib.error
import urllib.request

API_ROOT = "https://api.github.com"


def github_request(method, path, body=None):
    """Call the GitHub REST API. Returns (status, json_or_None).

    path is joined onto https://api.github.com as-is (it must start with
    "/"). body, when given, is JSON-encoded as the request payload. A
    non-2xx response is not raised: the caller gets the real status code and
    whatever JSON body GitHub sent back (or None if it didn't parse as
    JSON), so 404s and other expected failures can be handled by the caller
    without a try/except around every call.
    """
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


def add_reaction(repo, comment_id, content):
    """React to an issue comment (e.g. content="+1")."""
    return github_request(
        "POST", f"/repos/{repo}/issues/comments/{comment_id}/reactions", {"content": content}
    )


def post_comment(repo, number, body):
    """Post a new comment on an issue or PR."""
    return github_request("POST", f"/repos/{repo}/issues/{number}/comments", {"body": body})


def add_assignees(repo, number, assignees):
    """Assign one or more accounts to an issue or PR."""
    return github_request(
        "POST", f"/repos/{repo}/issues/{number}/assignees", {"assignees": assignees}
    )


def actor_permission(repo, username):
    """Return username's permission on repo: "admin", "write", "read", or "none".

    Uses GET /repos/{repo}/collaborators/{username}/permission rather than
    org membership, because it answers the question that actually matters
    here — can this account push to *this* repo — and it also covers
    outside collaborators with write access, not just org members.
    """
    status, response = github_request(
        "GET", f"/repos/{repo}/collaborators/{username}/permission"
    )
    if status != 200 or not isinstance(response, dict):
        return "none"
    return response.get("permission", "none")


def is_authorized(repo, username):
    """Return True if username can push to repo (admin or write permission)."""
    return actor_permission(repo, username) in ("admin", "write")


def report_if_error(context, status, ignore=()):
    """Print a non-2xx status to stderr. Never raises, never fails the job.

    Callers that discard the (status, json) tuple from the helpers above
    were silently swallowing failed API calls (e.g. a labels POST that 403s
    because permissions: was wrong). This makes that visible in the job log
    without turning it into a hard failure.

    ignore lists status codes that are expected/tolerated for this call and
    must not be reported (e.g. remove_label's documented 404 "already gone"
    case) — real errors (403, 422, 5xx, and 404 from any other call) are
    still reported.
    """
    if status not in ignore and not (200 <= status < 300):
        print(f"{context}: unexpected status {status}", file=sys.stderr)
