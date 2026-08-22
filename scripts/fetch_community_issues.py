#!/usr/bin/env python3
"""Fetch every issue (all states) from the given repos, full body + comments,
into a local directory for offline grepping.

Used by the community-fixture sweep (tests/fixtures/community/PROVENANCE.md)
to search issue text and file attachments for real vehicle diagnostics,
since GitHub's issue search does not do literal substring matching on
snake_case/camelCase field names. Re-run this to refresh the sweep.

Usage: fetch_community_issues.py [output_dir]
"""

import json
import os
import subprocess
import sys

REPOS = ["bretterer/home-assistant-rivian", "bretterer/rivian-python-client"]


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "community_issues"
    os.makedirs(f"{out}/issues", exist_ok=True)

    failed = []
    for repo in REPOS:
        slug = repo.replace("/", "_")
        listing = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                repo,
                "--state",
                "all",
                "--limit",
                "500",
                "--json",
                "number,title,url",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        issues = json.loads(listing.stdout)
        with open(f"{out}/{slug}_issues.json", "w") as f:
            f.write(listing.stdout)

        for it in issues:
            n = it["number"]
            fpath = f"{out}/issues/{slug}_{n}.json"
            if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
                continue
            r = subprocess.run(
                [
                    "gh",
                    "issue",
                    "view",
                    str(n),
                    "--repo",
                    repo,
                    "--json",
                    "number,title,url,body,comments,author",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if r.returncode != 0:
                failed.append((repo, n, r.stderr.strip()))
                continue
            with open(fpath, "w") as f:
                f.write(r.stdout)
        print(f"done {repo}: {len(issues)} issues")

    if failed:
        print("failed:", failed)


if __name__ == "__main__":
    main()
