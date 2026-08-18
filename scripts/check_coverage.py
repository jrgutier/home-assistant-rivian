"""Enforce a separate coverage floor for our code and for the vendored client.

`--cov-fail-under` is a single global number and cannot express this. After s07
the same measurement covers two populations with different obligations:

  custom_components/rivian/**            code we write -- held to a high bar
  custom_components/rivian/rivian_client vendored client -- held to its own bar

Collapsing them into one figure would let the integration's coverage rot behind a
large, slowly-improving vendored denominator, or force the vendored code to be
excluded entirely, which the plan's own pre-mortem calls coverage theatre.

Both floors ratchet upward only. Raise them when the real number rises; never
lower one to make a run pass.
"""

from __future__ import annotations

import json
import pathlib
import sys

INTEGRATION_FLOOR = 83.0
CLIENT_FLOOR = 59.0

VENDORED = "custom_components/rivian/rivian_client/"


def main() -> int:
    report = pathlib.Path("coverage.json")
    if not report.exists():
        print("coverage.json not found -- run pytest with --cov-report=json first")
        return 2

    files = json.loads(report.read_text())["files"]
    buckets = {"integration": [0, 0], "client": [0, 0]}
    for name, data in files.items():
        bucket = "client" if VENDORED in name else "integration"
        buckets[bucket][0] += data["summary"]["num_statements"]
        buckets[bucket][1] += data["summary"]["covered_lines"]

    failed = False
    for bucket, floor in (("integration", INTEGRATION_FLOOR), ("client", CLIENT_FLOOR)):
        total, covered = buckets[bucket]
        if not total:
            print(f"{bucket}: no statements measured -- is the path right?")
            failed = True
            continue
        pct = 100.0 * covered / total
        status = "OK  " if pct >= floor else "FAIL"
        print(
            f"{status} {bucket:12s} {pct:6.2f}%  (floor {floor:.1f}%)  {covered}/{total}"
        )
        if pct < floor:
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
