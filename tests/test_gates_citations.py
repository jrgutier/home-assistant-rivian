"""Regression test for the f11 citation-drift gate's --fix path.

scripts/gates/helpers/citations.py is not part of the custom_components
package -- it is a repo-maintenance script, run manually or via
scripts/gates/f11.sh, never imported by the integration. This test invokes
it as a subprocess against a scratch tree (F11_REPO_ROOT), the same
mechanism its own module docstring describes for "the deliberate-drift
test": mirror a citing file and its anchors into a throwaway directory at
the same relative paths so --fix can mutate it without touching anything
git tracks.

Reproduces a real bug (found live on cover.py:144's two citations into
__init__.py, hand-repaired once already): when two stale citations on the
SAME citing line both get rewritten in one --fix pass, the per-citation
loop captured the line's "old hash" (for sidecar hash-propagation)
unconditionally on every citation, so the second citation's capture
overwrote the first with an intermediate, already-half-edited hash that
never matched anything in the sidecar. Neither row could then be
propagated to the new hash, so a subsequent --check reported "no sidecar
row for this citing line" -- --fix looked like it worked (the citation
text WAS corrected) but silently broke the very rows it was supposed to
keep in sync.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys

CITATIONS_PY = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "gates"
    / "helpers"
    / "citations.py"
)


def _line_hash(text: str) -> str:
    """Mirror citations.py's line_hash() without importing the module."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _run(args: list[str], repo_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CITATIONS_PY), *args],
        cwd=repo_root,
        env={"F11_REPO_ROOT": str(repo_root), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_fix_repairs_two_stale_citations_sharing_one_line(tmp_path: Path) -> None:
    """Two stale citations to the same file, on one line: --fix then --check must be clean."""
    repo = tmp_path
    corpus = repo / "custom_components"
    corpus.mkdir(parents=True)

    # The cited file: what the two citations are ABOUT has moved since the
    # citations were written. Real content is now at :4 and :7.
    target = corpus / "target.py"
    target.write_text(
        "line1\n"
        "line2\n"
        "line3\n"
        "FOO_MARKER = 1\n"
        "line5\n"
        "line6\n"
        "BAR_MARKER = 2\n"
        "line8\n"
        "line9\n"
    )

    # The citing file: ONE comment line carries BOTH stale citations
    # (target.py:2 and target.py:6 -- both wrong; real content is :4 and :7).
    citing_line = "# See target.py:2 and target.py:6 for details."
    citing = corpus / "citing.py"
    citing.write_text(f'"""Module docstring."""\n{citing_line}\nCODE = 1\n')

    citing_hash = _line_hash(citing_line)

    gates_helpers = repo / "scripts" / "gates" / "helpers"
    gates_helpers.mkdir(parents=True)
    anchors_tsv = gates_helpers / "code_anchors.tsv"
    # Row order matches left-to-right citation order in the line (:2 then
    # :6), matching how AnchorIndex.take() disambiguates two citations to
    # the SAME cited_file sharing one hash.
    anchors_tsv.write_text(
        "# test fixture\n"
        "# Columns: cited-file\tanchor\tciting-file\tciting-line-sha256[:12]\tnote\n"
        f"custom_components/target.py\tFOO_MARKER\tcustom_components/citing.py\t{citing_hash}\tfirst citation on the shared line\n"
        f"custom_components/target.py\tBAR_MARKER\tcustom_components/citing.py\t{citing_hash}\tsecond citation on the shared line\n"
    )

    fix = _run(["--fix"], repo)
    assert fix.returncode == 0, fix.stderr
    assert citing_line not in citing.read_text(), (
        "citing.py should have been rewritten to the real locations"
    )

    check = _run(["--check"], repo)
    assert check.returncode == 0, (
        "a second --check after --fix must be clean -- 'no sidecar row for "
        f"this citing line' means --fix orphaned a row instead of updating it.\n"
        f"stdout:\n{check.stdout}"
    )
    assert "no-anchor" not in check.stdout
    assert "FAIL" not in check.stdout

    fixed_text = citing.read_text()
    assert "target.py:4" in fixed_text
    assert "target.py:7" in fixed_text
