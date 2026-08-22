#!/usr/bin/env python3
"""f11 --corpus plan: a lightweight, LOCAL-ONLY audit of `file.py:N` style
citations inside a plan markdown document.

Deliberately not the same rigor as citations.py's code-corpus check. A plan
document is prose that gets rewritten wholesale between iterations, not code
with a stable AST -- there is no hand-authored anchor sidecar here, and none
is planned. This can only catch two mechanical things:

  * the cited file cannot be found under custom_components/ at all, or
  * the cited line/range falls past the end of the file it resolves to.

It CANNOT tell "moved" from "was always imprecise" the way the code corpus's
--check can (that needs a content fingerprint, which is exactly the
hand-reviewed sidecar work a plan document does not get). Exit 0 means
"nothing mechanically impossible found", not "every citation is accurate".

Not run by CI or pre-commit -- see f11.sh's "--corpus plan" branch.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import citations as C

FULL_RE = re.compile(r"(?P<file>[A-Za-z_][A-Za-z0-9_./]*\.py):(?P<spec>\d+(?:-\d+)?)")


# The plan document cites more than custom_components/ -- tests/, scripts/,
# probe files -- so resolution searches the whole repo, not just the code
# corpus. Same __pycache__ exclusion as citations.py; also skips .venv, which
# a code-corpus-only search never needed to.
def _repo_python_files() -> list[Path]:
    return [
        p
        for p in C.REPO_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
        and ".venv" not in p.parts
        and "venv" not in p.parts
    ]


def audit(plan_path: Path) -> int:
    text = plan_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    bad = 0
    total = 0
    seen: set[tuple[str, str]] = set()
    all_py = _repo_python_files()
    for i, line in enumerate(lines, 1):
        for m in FULL_RE.finditer(line):
            token, spec = m.group("file"), m.group("spec")
            key = (token, spec)
            total += 1
            resolved = [p for p in all_py if p.name == Path(token).name]
            if not resolved:
                if key not in seen:
                    print(
                        f"UNRESOLVED\t{plan_path.name}:{i}\t{token}:{spec}\t no file named {token!r} under custom_components/"
                    )
                    bad += 1
                seen.add(key)
                continue
            _lo, hi = C._spec_to_range(spec)
            in_bounds = any(
                hi <= len(p.read_text(encoding="utf-8", errors="replace").splitlines())
                for p in resolved
            )
            if not in_bounds:
                counts = ", ".join(
                    f"{p.relative_to(C.REPO_ROOT)}={len(p.read_text(encoding='utf-8', errors='replace').splitlines())}"
                    for p in resolved
                )
                print(
                    f"OUT-OF-BOUNDS\t{plan_path.name}:{i}\t{token}:{spec}\t candidates: {counts}"
                )
                bad += 1
    print(f"CENSUS\ttotal={total} out_of_bounds_or_unresolved={bad}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: plan_citations.py <plan.md>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(audit(Path(sys.argv[1])))
