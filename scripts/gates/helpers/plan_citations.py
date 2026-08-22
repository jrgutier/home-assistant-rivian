#!/usr/bin/env python3
"""f11 --corpus plan: a lightweight, LOCAL-ONLY audit of `file.py:N` style
citations inside one or more plan markdown documents.

Deliberately not the same rigor as citations.py's code-corpus check, and this
output must never be read as "these citations are correct" -- corrected after
review: this mode only catches two mechanical things:

  * the cited file cannot be found anywhere in the repo, or
  * the cited line/range falls past the end of the file it resolves to.

That is bounds-checking, not content verification, and a STALE-but-in-bounds
citation is invisible to it by construction: a line number that used to be
right and drifted because the file only grew still looks "in bounds" of the
file it drifted within. Concretely: a hand audit this session found 11+ drifted
citations in this exact corpus (const.py:88->:89, coordinator.py:1265-1272->
:1452-1460, entity.py:75-79->:74-80, coordinator.py:1292->:1490, among
others) and every one of them passes bounds-checking, because none of them
resolved past end-of-file.

So every finding below is labelled UNVERIFIED, never PASS -- "0 unresolved or
out-of-bounds" is not evidence the citations are accurate, only that none of
them are IMPOSSIBLE. Extending the anchor-sidecar design from citations.py's
code corpus to this one (a plan_anchors.tsv, keyed the same way: the citing
line's text hashed, the cited *file's* content fingerprinted -- prose on the
citing side doesn't change that mechanism, since it never needed an AST of
the citing document) would give this corpus real content verification. That
is a real follow-up, not done here.

Not run by CI or pre-commit -- see f11.sh's "--corpus plan" branch. Neither
plan file lives in the repo's committed tree (one under ~/.claude/plans/, one
under the gitignored .omc/plans/), so this corpus cannot be CI-bound even
once verification is real.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import citations as C

FULL_RE = re.compile(r"(?P<file>[A-Za-z_][A-Za-z0-9_./]*\.py):(?P<spec>\d+(?:-\d+)?)")


# Plan documents cite more than custom_components/ -- tests/, scripts/, probe
# files -- so resolution searches the whole repo, not just the code corpus.
# Same __pycache__ exclusion as citations.py; also skips .venv, which a
# code-corpus-only search never needed to.
def _repo_python_files() -> list[Path]:
    return [
        p
        for p in C.REPO_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
        and ".venv" not in p.parts
        and "venv" not in p.parts
    ]


def audit_one(plan_path: Path, all_py: list[Path]) -> tuple[int, int]:
    """Returns (total citations, unresolved-or-out-of-bounds count)."""
    text = plan_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    bad = 0
    total = 0
    seen: set[tuple[str, str]] = set()
    for i, line in enumerate(lines, 1):
        for m in FULL_RE.finditer(line):
            token, spec = m.group("file"), m.group("spec")
            key = (token, spec)
            total += 1
            resolved = [p for p in all_py if p.name == Path(token).name]
            if not resolved:
                if key not in seen:
                    print(
                        f"UNRESOLVED\t{plan_path.name}:{i}\t{token}:{spec}\t no file named {token!r} anywhere in the repo"
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
    return total, bad


def audit(plan_paths: list[Path]) -> int:
    all_py = _repo_python_files()
    total = 0
    bad = 0
    for plan_path in plan_paths:
        t, b = audit_one(plan_path, all_py)
        total += t
        bad += b
    print(f"CENSUS\ttotal={total} unresolved_or_out_of_bounds={bad}")
    print(
        "UNVERIFIED\tbounds-only check -- 0 unresolved/out-of-bounds is NOT a "
        "correctness signal. A stale-but-in-bounds line number (the common "
        "case after a file only grows) is invisible to this mode by "
        "construction. See this file's module docstring."
    )
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: plan_citations.py <plan.md> [<plan2.md> ...]", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(audit([Path(p) for p in sys.argv[1:]]))
