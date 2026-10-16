#!/usr/bin/env python3
"""Check the plugin version agrees across plugin.json, CHANGELOG.md, marketplace.json and a tag.
Usage: check_version.py [--tag vX.Y.Z] [--root DIR]. Exits 1 on a mismatch, 2 on bad input."""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_NAME = "kumi"

# A Keep a Changelog section heading, for example "## [1.4.0] - 2026-10-04" or "## [Unreleased]".
HEADING_RE = re.compile(r"^## \[([^\]]+)\]")


def released_version(changelog_text):
    """The version in the first changelog heading that is not [Unreleased], or None."""
    for line in changelog_text.splitlines():
        m = HEADING_RE.match(line)
        if m and m.group(1).strip().lower() != "unreleased":
            return m.group(1).strip()
    return None


def load_object(path):
    """Load a JSON file whose top level must be an object; raise ValueError otherwise."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level is not a JSON object")
    return data


def marketplace_version(marketplace):
    """The version the marketplace entry for this plugin carries, or None when it carries none."""
    plugins = marketplace.get("plugins") or []
    if not isinstance(plugins, list):
        raise ValueError("marketplace.json: plugins is not a list")
    for entry in plugins:
        if not isinstance(entry, dict):
            raise ValueError("marketplace.json: a plugins entry is not a JSON object")
        if entry.get("name") == PLUGIN_NAME:
            return entry.get("version")
    return None


def find_problems(root, tag=None):
    """Return (plugin_version, problems, compared); compared names the sources checked."""
    plugin_dir = os.path.join(root, ".claude-plugin")
    version = load_object(os.path.join(plugin_dir, "plugin.json")).get("version")
    if not isinstance(version, str) or not version:
        return version, ["plugin.json has no version"], ["plugin.json"]

    problems, compared = [], ["plugin.json", "CHANGELOG.md"]
    with open(os.path.join(root, "CHANGELOG.md"), encoding="utf-8") as f:
        released = released_version(f.read())
    if released is None:
        problems.append("CHANGELOG.md has no released version heading")
    elif released != version:
        problems.append(f"plugin.json version {version} != newest CHANGELOG.md release {released}")

    marketplace_path = os.path.join(plugin_dir, "marketplace.json")
    if os.path.isfile(marketplace_path):
        listed = marketplace_version(load_object(marketplace_path))
        if listed is not None:
            compared.append("marketplace.json")
        if listed is not None and listed != version:
            problems.append(f"plugin.json version {version} != marketplace.json version {listed}")

    if tag is not None:
        compared.append(f"tag {tag}")
        if tag != f"v{version}":
            problems.append(f"tag {tag} != v{version} from plugin.json")
    return version, problems, compared


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    tag, root = None, ROOT
    while args:
        flag = args.pop(0)
        if flag in ("--tag", "--root") and args:
            value = args.pop(0)
            if flag == "--tag":
                tag = value
            else:
                root = value
        else:
            print(f"usage: check_version.py [--tag vX.Y.Z] [--root DIR] (bad argument: {flag})")
            return 2

    try:
        version, problems, compared = find_problems(root, tag)
    except (OSError, ValueError) as e:
        print(f"error: {e}")
        return 2
    if problems:
        print("version mismatch:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"version {version} agrees across {', '.join(compared)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
