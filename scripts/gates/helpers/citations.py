#!/usr/bin/env python3
"""f11 citation-drift engine.

Parses `file.py:N`, `file.py:N-M` and `file.py:symbol` citations out of
comments and docstrings, resolves each one against the file it actually
points at, and reports drift. See scripts/gates/f11.sh for the pre-commit
wrapper and CODE_ANCHORS below for the hand-reviewed sidecar this reads.

Two citation forms
-------------------
Full-form:  `path/to/file.py:1234`, `file.py:1234-1240`, `file.py:some_symbol`
Shorthand:  a bare `:1234` or `:1234-1240` that continues the MOST RECENT
            full-form citation's file, tracked across an entire comment run
            or docstring (a "block") -- not just the same line. Two
            exclusions keep this from over-matching (see BARE_RE below):
            never match a `:N` immediately preceded by `[` (slice syntax,
            e.g. `sha256[:12]`), and never resolve to a line past the end of
            the cited file.

Symbol citations (`file.py:NAME`) are resolved fresh every run against a
top-level `def NAME`, `class NAME` or `NAME = `/`NAME: ` in the cited file --
they can never drift as long as the symbol exists, so they carry no sidecar
row at all.

Line citations (`file.py:N` / `file.py:N-M`) are checked against
CODE_ANCHORS: a hand-authored table, one row per citation, recording what
the citation is SUPPOSED to point at (a short, grep-unique snippet of the
target's actual content) rather than trusting whatever line number happens
to be written today. That is what lets --check catch a citation that was
already wrong the day it was established, not just future drift -- and it
is also why populating this table is a hand-reviewed step (see f11.sh),
never something the gate invents by trusting its own input.

The row key is (citing_file, sha256 of the citing line's exact text)[:12] --
never citing_file:line -- so an unrelated edit elsewhere in the file never
invalidates it (rule: the gate's own input must not be an instance of the
disease it exists to cure).
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import sys

GATES_DIR = Path(__file__).resolve().parent.parent
# F11_REPO_ROOT exists ONLY for the deliberate-drift test (scripts/gates/f11.sh
# --self-test), which mirrors a citing file into a scratch tree at the same
# relative path so the mutation can be checked WITHOUT touching anything git
# tracks. Never set in normal use -- --check and --fix always resolve
# REPO_ROOT from this file's own location.
REPO_ROOT = (
    Path(os.environ["F11_REPO_ROOT"])
    if os.environ.get("F11_REPO_ROOT")
    else GATES_DIR.parent.parent
)
CODE_CORPUS_ROOT = REPO_ROOT / "custom_components"

# ---------------------------------------------------------------------------
# Hand-reviewed sidecar: loaded from code_anchors.tsv, one row per LINE-form
# citation currently in the code corpus that is meant to be tracked.
#
# Columns: cited-file, anchor, citing-file, citing-line-sha256[:12], note.
# Keyed by (citing_file, sha256[:12] of the citing line's exact current
# text) -- never citing_file:line -- so an unrelated edit elsewhere in the
# file never invalidates a row (rule: the gate's own input must not be an
# instance of the disease it exists to cure). `anchor` is a fixed substring
# (re.escape()d at load time, not a live regex) of the TRUE target content,
# verified grep -cF unique in `cited_file` at establishment time.
#
# This table is the establishment pass's output: populated by reading every
# citation N28 found and re-verifying its target against the tree, not by
# trusting whatever line number happened to already be written -- that is
# what lets --check catch a citation that was already wrong the day it was
# established, not just future drift.
#
# lock.py:42 is deliberately absent: both its citations were collapsed into
# a single `const.py:BINARY_SENSORS` symbol citation by the f11 repair pass
# instead of being tracked as two line anchors -- symbol citations never
# need an anchor row at all.
# ---------------------------------------------------------------------------

# Derived from REPO_ROOT (which F11_REPO_ROOT can override for the
# deliberate-drift test), NOT from GATES_DIR (this script's own,
# never-overridden location) -- otherwise --fix run against a scratch
# mirror would still write the REAL sidecar, silently corrupting it with
# hashes computed from the scratch copy's (possibly mutated) content. A
# scratch mirror used with --fix must carry its own copy of this file at
# the same relative path.
ANCHORS_TSV = REPO_ROOT / "scripts" / "gates" / "helpers" / "code_anchors.tsv"


@dataclass(frozen=True)
class AnchorRow:
    cited_file: str
    anchor: str
    citing_file: str
    citing_hash: str
    note: str


def load_anchors(path: Path = ANCHORS_TSV) -> tuple[AnchorRow, ...]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cited_file, anchor, citing_file, citing_hash, note = line.split("\t", 4)
        rows.append(AnchorRow(cited_file, anchor, citing_file, citing_hash, note))
    return tuple(rows)


def write_anchors(rows: tuple[AnchorRow, ...], path: Path = ANCHORS_TSV) -> None:
    header = [
        "# f11 sidecar -- see scripts/gates/helpers/citations.py module docstring.\n",
        "# Columns: cited-file\tanchor\tciting-file\tciting-line-sha256[:12]\tnote\n",
        '# "anchor" is matched as a literal substring (re.escape()d at load time), not a live regex.\n',
    ]
    body = [
        f"{r.cited_file}\t{r.anchor}\t{r.citing_file}\t{r.citing_hash}\t{r.note}\n"
        for r in rows
    ]
    path.write_text("".join(header + body), encoding="utf-8")


CODE_ANCHORS: tuple[AnchorRow, ...] = load_anchors()

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# `path/parts/file.py:1234`, `file.py:1234-1240`, or `file.py:symbol_name`.
FULL_RE = re.compile(
    r"(?P<file>[A-Za-z_][A-Za-z0-9_./]*\.py):(?P<spec>[A-Za-z_]\w*|\d+(?:-\d+)?)"
)
# A bare `:1234` or `:1234-1240`, for shorthand continuations. The `[^\[]`
# lookbehind-equivalent (checked manually below) excludes slice syntax like
# `sha256[:12]`.
BARE_RE = re.compile(r":(\d+)(?:-(\d+))?")


@dataclass
class Citation:
    citing_file: Path  # relative to repo root
    citing_line_no: int  # 1-indexed
    citing_line_text: str
    cited_file_token: (
        str  # as written, e.g. "coordinator.py" or "rivian_client/rivian.py"
    )
    spec: str  # "1234", "1234-1240", or a symbol name
    is_shorthand: bool


def _is_symbol_spec(spec: str) -> bool:
    return not spec[0].isdigit()


def _iter_source_files(root: Path):
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        yield p


def _block_state_machine(lines: list[str]):
    """Yield (line_no, in_block) for every line, where in_block is True for
    `#`-comment lines and lines inside a triple-quoted string.

    Deliberately simple: toggles on `\"\"\"`/`'''` counts per line. Good
    enough for this corpus (verified against every citation site by hand at
    establishment) but not a general Python tokenizer -- a `\"\"\"` inside an
    f-string or a comment would confuse it. None occur in custom_components/.
    """
    in_triple: str | None = None  # '"""' or "'''" or None
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if in_triple:
            close = in_triple
            if close in line:
                # crude: assume the block closes on the first occurrence
                in_triple = None
            yield i, True
            continue
        if stripped.startswith("#"):
            yield i, True
            continue
        # Not already in a triple-quote and not a comment: does this line
        # OPEN one (typically a docstring opener, possibly closing on the
        # same line)?
        for q in ('"""', "'''"):
            if q in line:
                count = line.count(q)
                if count % 2 == 1:
                    in_triple = q
                    yield i, True
                    break
        else:
            yield i, False
            continue
        continue


def parse_file(path: Path) -> list[Citation]:
    rel = path.relative_to(REPO_ROOT)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    citations: list[Citation] = []
    current_file_token: str | None = None
    for line_no, in_block in _block_state_machine(lines):
        line = lines[line_no - 1]
        if not in_block:
            current_file_token = None
            continue
        consumed_spans: list[tuple[int, int]] = []
        for m in FULL_RE.finditer(line):
            consumed_spans.append(m.span())
            token = m.group("file")
            spec = m.group("spec")
            citations.append(
                Citation(rel, line_no, line, token, spec, is_shorthand=False)
            )
            current_file_token = token
        if current_file_token is None:
            continue
        for m in BARE_RE.finditer(line):
            start, _end = m.span()
            if any(s <= start < e for s, e in consumed_spans):
                continue
            if start > 0 and line[start - 1] == "[":
                continue  # slice syntax, e.g. sha256[:12]
            n1, n2 = m.group(1), m.group(2)
            spec = f"{n1}-{n2}" if n2 else n1
            citations.append(
                Citation(
                    rel, line_no, line, current_file_token, spec, is_shorthand=True
                )
            )
    return citations


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_cited_file(
    citing_file: Path, token: str, spec: str | None = None
) -> Path | None:
    """Resolve a cited file TOKEN (e.g. "const.py" or "rivian_client/rivian.py")
    against the citing file's own location, then by unique basename search
    under the code corpus. Returns an absolute Path, or None if unresolved
    or ambiguous.

    `spec` (a citation's line spec, e.g. "1600-1610") disambiguates a
    same-dir match that can't possibly be right: `rivian_client/const.py`
    and `custom_components/rivian/const.py` share a basename, and a comment
    inside the vendored client that cites "const.py:1600" almost always
    means the top-level one -- rivian_client/const.py is only 370 lines. If
    the same-dir candidate can't hold `spec` but exactly one OTHER
    same-basename file in the corpus can, prefer that one instead of
    reporting a same-dir match that is out of bounds by construction.
    """
    token_path = Path(token)
    same_dir = (REPO_ROOT / citing_file).parent / token_path
    root_relative = REPO_ROOT / token_path

    def in_bounds(p: Path) -> bool:
        if spec is None or _is_symbol_spec(spec):
            return True
        _lo, hi = _spec_to_range(spec)
        return hi <= len(p.read_text(encoding="utf-8").splitlines())

    same_dir_ok = same_dir.is_file() and in_bounds(same_dir)
    if same_dir_ok:
        return same_dir.resolve()
    if root_relative.is_file() and in_bounds(root_relative):
        return root_relative.resolve()

    matches = [
        p for p in _iter_source_files(CODE_CORPUS_ROOT) if p.name == token_path.name
    ]
    # Prefer a match whose trailing path components equal the token exactly
    # (handles "rivian_client/rivian.py" tokens).
    exact = [p for p in matches if str(p).replace("\\", "/").endswith(str(token_path))]
    candidates = exact if exact else matches
    in_bounds_candidates = [p for p in candidates if in_bounds(p)]
    if len(in_bounds_candidates) == 1:
        return in_bounds_candidates[0].resolve()
    if len(candidates) == 1:
        return candidates[0].resolve()
    # Nothing in-bounds and still ambiguous: fall back to the same-dir/
    # root-relative file if either exists, even out of bounds -- callers
    # report the out-of-bounds condition themselves.
    if same_dir.is_file():
        return same_dir.resolve()
    if root_relative.is_file():
        return root_relative.resolve()
    return None


SYMBOL_RE_TMPL = r"^(?:async\s+def|def|class)\s+{name}\b|^{name}\s*[:=]"


def resolve_symbol(cited_file: Path, name: str) -> int | None:
    """Return the 1-indexed line of a top-level def/class/assignment named
    NAME in cited_file, or None if zero or more than one match.
    """
    pattern = re.compile(SYMBOL_RE_TMPL.format(name=re.escape(name)))
    hits = []
    for i, line in enumerate(cited_file.read_text(encoding="utf-8").splitlines(), 1):
        if pattern.match(line):
            hits.append(i)
    return hits[0] if len(hits) == 1 else None


def line_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _spec_to_range(spec: str) -> tuple[int, int]:
    if "-" in spec:
        a, b = spec.split("-", 1)
        return int(a), int(b)
    n = int(spec)
    return n, n


# ---------------------------------------------------------------------------
# Checking
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    citation: Citation
    status: str  # "ok", "stale", "broken", "unresolved", "no-anchor"
    detail: str


class AnchorIndex:
    """Looks up CODE_ANCHORS rows by (citing_file, citing-line-sha256[:12]),
    consuming each row at most once per run.

    Multiple citations can share one citing line -- either two DIFFERENT
    `.py:` refs in the same sentence (helpers.py:27, switch.py:86), or two
    citations to the SAME file (cover.py:144's full-form :108 and its
    shorthand :130). The first case is disambiguated by matching the
    row's cited_file against this citation's resolved target; the second
    can't be (both rows share cited_file AND the same hash, since they're
    the same line), so rows are additionally taken in the order
    CODE_ANCHORS lists them -- which is the order the citations
    themselves appear in the line, left to right. A fresh AnchorIndex must
    be built per run so state never leaks between calls.
    """

    def __init__(self, rows: tuple[AnchorRow, ...] = CODE_ANCHORS) -> None:
        self._rows: dict[tuple[str, str], list[AnchorRow]] = {}
        for r in rows:
            self._rows.setdefault((r.citing_file, r.citing_hash), []).append(r)

    def take(
        self, citing_file: str, citing_hash: str, cited_rel: str
    ) -> AnchorRow | None:
        bucket = self._rows.get((citing_file, citing_hash))
        if not bucket:
            return None
        for i, row in enumerate(bucket):
            if row.cited_file == cited_rel:
                return bucket.pop(i)
        return None


def check_citation(c: Citation, anchors: AnchorIndex) -> Finding:
    cited_path = resolve_cited_file(c.citing_file, c.cited_file_token, c.spec)
    if cited_path is None:
        return Finding(
            c, "unresolved", f"cannot resolve cited file {c.cited_file_token!r}"
        )
    cited_rel = str(cited_path.relative_to(REPO_ROOT))

    if _is_symbol_spec(c.spec):
        line = resolve_symbol(cited_path, c.spec)
        if line is None:
            return Finding(
                c,
                "broken",
                f"symbol {c.spec!r} not found (or ambiguous) in {c.cited_file_token}",
            )
        return Finding(
            c, "ok", f"symbol {c.spec!r} resolved at {c.cited_file_token}:{line}"
        )

    h = line_hash(c.citing_line_text)
    row = anchors.take(str(c.citing_file), h, cited_rel)
    if row is None:
        return Finding(
            c,
            "no-anchor",
            f"no sidecar row for this citing line -> {cited_rel} -- run establishment (citing_line_hash={h})",
        )
    anchor_re = re.compile(re.escape(row.anchor))
    target_lines = cited_path.read_text(encoding="utf-8").splitlines()
    hits = [i for i, line in enumerate(target_lines, 1) if anchor_re.search(line)]
    if len(hits) != 1:
        return Finding(
            c,
            "broken",
            f"anchor content ({row.anchor!r}) not uniquely found in {row.cited_file} (hits={len(hits)}) -- {row.note}",
        )
    true_line = hits[0]
    lo, hi = _spec_to_range(c.spec)
    if lo <= true_line <= hi:
        return Finding(
            c,
            "ok",
            f"{c.cited_file_token}:{c.spec} matches content now at :{true_line}",
        )
    return Finding(
        c,
        "stale",
        f"cites {c.cited_file_token}:{c.spec} but content is now at :{true_line} -- {row.note}",
    )


def collect_citations(root: Path) -> list[Citation]:
    out: list[Citation] = []
    for f in _iter_source_files(root):
        out.extend(parse_file(f))
    return out


def run_check() -> tuple[list[Finding], dict[str, int]]:
    anchors = AnchorIndex()
    citations = collect_citations(CODE_CORPUS_ROOT)
    findings = [check_citation(c, anchors) for c in citations]

    files = {str(c.citing_file) for c in citations}
    lines = {(str(c.citing_file), c.citing_line_no) for c in citations}
    full = sum(1 for c in citations if not c.is_shorthand)
    shorthand = sum(1 for c in citations if c.is_shorthand)
    symbol = sum(1 for c in citations if _is_symbol_spec(c.spec))
    census = {
        "full_form": full,
        "shorthand": shorthand,
        "lines": len(lines),
        "files": len(files),
        "symbol": symbol,
        "total": len(citations),
        "ok": sum(1 for f in findings if f.status == "ok"),
        "stale": sum(
            1
            for f in findings
            if f.status in ("stale", "broken", "unresolved", "no-anchor")
        ),
    }
    return findings, census


def run_fix() -> int:
    """Rewrite every STALE line-form citation in place to the anchor's
    current true location, AND rewrite that row's citing-line-sha256 in
    code_anchors.tsv in the same pass -- atomically, per R22: a `--fix`
    that only rewrote the citation would change the citing line's text
    (and therefore its hash) without updating the row keyed on that hash,
    orphaning its own row and making a second --check fail with
    "no sidecar row" instead of passing. Never touches symbol citations.
    Returns the number of citation edits made.
    """

    # Identity of a row minus its hash: unique in this table (no two rows
    # share cited_file+anchor+citing_file+note), so it survives the row's
    # own hash being replaced below.
    def identity_of(row: AnchorRow) -> tuple[str, str, str, str]:
        return (row.cited_file, row.anchor, row.citing_file, row.note)

    scan_anchors = AnchorIndex()
    citations = collect_citations(CODE_CORPUS_ROOT)
    by_file: dict[Path, list[tuple[Citation, AnchorRow]]] = {}
    for c in citations:
        if _is_symbol_spec(c.spec):
            continue
        cited_path = resolve_cited_file(c.citing_file, c.cited_file_token, c.spec)
        if cited_path is None:
            continue
        cited_rel = str(cited_path.relative_to(REPO_ROOT))
        row = scan_anchors.take(
            str(c.citing_file), line_hash(c.citing_line_text), cited_rel
        )
        if row is None:
            continue
        finding = check_citation(c, AnchorIndex((row,)))
        if finding.status == "stale":
            by_file.setdefault(REPO_ROOT / c.citing_file, []).append((c, row))

    edits = 0
    new_hash_by_identity: dict[tuple[str, str, str, str], str] = {}
    for path, items in by_file.items():
        citing_rel = str(path.relative_to(REPO_ROOT))
        text_lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        old_hash_by_idx: dict[int, str] = {}
        touched_idx: set[int] = set()
        for c, row in items:
            cited_path = resolve_cited_file(c.citing_file, c.cited_file_token, c.spec)
            anchor_re = re.compile(re.escape(row.anchor))
            target_lines = cited_path.read_text(encoding="utf-8").splitlines()
            hits = [
                i for i, line in enumerate(target_lines, 1) if anchor_re.search(line)
            ]
            if len(hits) != 1:
                continue  # anchor content vanished or duplicated -- needs a human, not --fix
            true_line = hits[0]
            old = (
                f"{c.cited_file_token}:{c.spec}" if not c.is_shorthand else f":{c.spec}"
            )
            new = (
                f"{c.cited_file_token}:{true_line}"
                if not c.is_shorthand
                else f":{true_line}"
            )
            idx = c.citing_line_no - 1
            if old not in text_lines[idx]:
                continue
            old_hash_by_idx[idx] = line_hash(text_lines[idx].rstrip("\n"))
            text_lines[idx] = text_lines[idx].replace(old, new, 1)
            touched_idx.add(idx)
            edits += 1
        path.write_text("".join(text_lines), encoding="utf-8")
        # A touched line can carry OTHER citations that were not themselves
        # stale (e.g. helpers.py:27 has two citations; fixing one changes
        # the line both share). Every row -- stale or not -- keyed on that
        # line's OLD hash must move to its new one, or the untouched
        # citation's row orphans even though nothing about IT was wrong.
        for idx in touched_idx:
            final_hash = line_hash(text_lines[idx].rstrip("\n"))
            old_hash = old_hash_by_idx[idx]
            for row in CODE_ANCHORS:
                if row.citing_file == citing_rel and row.citing_hash == old_hash:
                    new_hash_by_identity[identity_of(row)] = final_hash

    if edits:
        final_rows = tuple(
            AnchorRow(
                r.cited_file,
                r.anchor,
                r.citing_file,
                new_hash_by_identity[identity_of(r)],
                r.note,
            )
            if identity_of(r) in new_hash_by_identity
            else r
            for r in CODE_ANCHORS
        )
        write_anchors(final_rows)
    return edits


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--check"
    if mode == "--list":
        for c in collect_citations(CODE_CORPUS_ROOT):
            kind = (
                "symbol"
                if _is_symbol_spec(c.spec)
                else ("shorthand" if c.is_shorthand else "full")
            )
            print(
                f"{c.citing_file}:{c.citing_line_no}\t{kind}\t{c.cited_file_token}:{c.spec}"
            )
        return 0
    if mode == "--fix":
        n = run_fix()
        print(f"FIXED\t{n}")
        return 0
    # --check (default)
    findings, census = run_check()
    for f in findings:
        tag = "PASS" if f.status == "ok" else "FAIL"
        loc = f"{f.citation.citing_file}:{f.citation.citing_line_no}"
        print(
            f"{tag}\t{loc}\t{f.citation.cited_file_token}:{f.citation.spec}\t{f.detail}"
        )
    print(
        "CENSUS\t"
        f"full={census['full_form']} shorthand={census['shorthand']} "
        f"lines={census['lines']} files={census['files']} symbol={census['symbol']} "
        f"total={census['total']} ok={census['ok']} stale={census['stale']}"
    )
    return 0 if census["stale"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
