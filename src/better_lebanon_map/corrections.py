"""Collect the "this is the right street" confirmations sent from a published copy of the map.

On a copy published on GitHub (publish.py), confirming a street on an address card opens an issue
of the repository titled "Access: <address>" that holds one line of JSON: the building and the point
of the street it is reached from. Anyone can send one, so a person reads each issue and labels the
ones to keep `accepted`. This command copies those into data/corrections/streets.jsonl, which the
next build applies (access.load_chosen), like the confirmations the local server saves.

  uv run python -I -m better_lebanon_map.corrections --repo owner/name [--label accepted]

It reads GitHub's public API: no account is needed for a public repository (set GITHUB_TOKEN for a
private one). Issues already collected are skipped, so it can be run again at any time.
"""

import argparse
import json
import os
import re
import urllib.parse
import urllib.request

from . import serve

LINE = re.compile(r'\{[^{}]*"key"[^{}]*\}')


def issues(repo, label):
    """The repository's issues with that label, open or closed (pull requests left out)."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "BetterLebanonMap-corrections/1.0"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    page, out = 1, []
    while True:
        query = urllib.parse.urlencode({"labels": label, "state": "all", "per_page": 100, "page": page})
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/issues?{query}", headers=headers)
        batch = json.load(urllib.request.urlopen(req, timeout=30))
        out += [i for i in batch if "pull_request" not in i]
        if len(batch) < 100:
            return out
        page += 1


def collect(found, path=serve.CHOSEN):
    """Appends the corrections of those issues to the file; returns (issues added, issues without a
    usable correction). An issue whose number is already in the file is skipped."""
    seen = set()
    if path.exists():
        seen = {json.loads(line).get("issue") for line in path.read_text().splitlines() if line.strip()}
    added, unusable = [], []
    for issue in sorted(found, key=lambda i: i["number"]):
        if issue["number"] in seen:
            continue
        match = LINE.search(issue.get("body") or "")
        try:
            serve.choose(json.loads(match.group(0)), path, issue=issue["number"])
            added.append(issue["number"])
        except (AttributeError, KeyError, TypeError, ValueError):
            unusable.append(issue["number"])
    return added, unusable


def main():
    ap = argparse.ArgumentParser(description="Collect accepted street confirmations from GitHub issues")
    ap.add_argument("--repo", required=True, help="the GitHub repository, as owner/name")
    ap.add_argument("--label", default="accepted", help="the label a person gives the issues to keep")
    args = ap.parse_args()
    found = issues(args.repo, args.label)
    added, unusable = collect(found)
    print(f"{len(found)} issues labelled {args.label!r}: {len(added)} added to {serve.CHOSEN}, "
          f"{len(found) - len(added) - len(unusable)} already there" + (f", no usable correction in {unusable}" if unusable else ""))
    if added:
        print("Rebuild to apply them: uv run python -I -m better_lebanon_map.pipeline")


if __name__ == "__main__":
    main()
