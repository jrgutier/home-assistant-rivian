#!/usr/bin/env python3
"""Print the shell a workflow actually executes, comments stripped.

Gates that grep a workflow's raw text read its comments too. Every comment in
this repo's workflows describes the bug it fixed -- "was `sed -i '/version/c...`",
"was `::set-output`" -- so a raw grep for the bug finds the description of the
fix and reports the bug is still present. Six gates in this project have already
been defeated that way.

It also joins backslash continuations, so `zip -q -r x.zip ./ \\` + `-i '*.py'`
reads as one command rather than two lines neither of which matches.

Usage: workflow_runs.py <workflow.yaml>
"""

from __future__ import annotations

import sys

import yaml


def main() -> int:
    with open(sys.argv[1]) as handle:
        doc = yaml.safe_load(handle)

    out: list[str] = []
    for job in (doc.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            run = step.get("run")
            if not run:
                continue
            # Join continuations first: a comment cannot span one, so order is safe.
            joined = run.replace("\\\n", " ")
            for line in joined.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    out.append(line)
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
