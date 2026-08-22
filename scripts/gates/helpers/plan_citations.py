#!/usr/bin/env python3
"""f11 --corpus plan: a LOCAL-ONLY audit of `file.py:N` style citations inside
one or more plan markdown documents.

Two check layers
-----------------
1. Bounds-checking (`audit_one`/`audit`, unchanged since this module's first
   version): the cited file can be found and the cited line/range is within
   it. Fast, needs no sidecar, but a STALE-but-in-bounds citation is invisible
   to it by construction -- a line number that used to be right and drifted
   because the file only grew still looks "in bounds".

2. Real content verification (`check_with_anchors`, s19), via a
   `plan_anchors.tsv` sidecar -- the SAME anchor-sidecar design citations.py
   uses for the in-code corpus: cited-file, an anchor (grep-unique substring
   of what the citation is SUPPOSED to point at), citing-file, and a
   sha256[:12] of the citing LINE's exact text (never citing_file:line, so an
   unrelated edit elsewhere in the plan doc never invalidates a row). Reuses
   citations.py's AnchorRow/AnchorIndex/line_hash/`_spec_to_range` directly --
   the mechanism never needed an AST of the citing document, so prose hashes
   exactly as well as code did.

   A citation WITHOUT an anchor row still only gets bounds-checking (reported
   UNRESOLVED/OUT-OF-BOUNDS/UNVERIFIED, same as before) -- coverage is
   whatever `--establish` has populated, not automatically total. A citation
   IN A FROZEN DOCUMENT (see FROZEN_PLANS) that would otherwise report FAIL
   reports FROZEN instead, and does not count toward the fail total -- the
   citation is dated, not broken, and the two must not read the same.

`--establish` (s19, run BY HAND, never by f11.sh or CI) populates
plan_anchors.tsv. It does not trust whatever line number is currently
written: for each citation it mines the CITING prose for a quoted string
literal (`field="x"`) or a backtick-quoted symbol name, and searches the
CITED file for where that content REALLY is -- the same "read the target,
don't bless the number" rule the code corpus's establishment pass used,
which is what let it catch citations that were already wrong the day they
were established, not just future drift. Only when no such signal exists in
the citing prose does it fall back to the content actually AT the cited
spec today (never a bare punctuation/brace line -- see MIN_ANCHOR_LEN). When
neither works it prints NEEDS-HUMAN and establishes nothing: prose sometimes
cites a concept rather than any specific line, and forcing an anchor onto
that would be exactly the "bless whatever is currently written" failure this
mechanism exists to avoid.

Not run by CI or pre-commit -- see f11.sh's "--corpus plan" branch. Neither
plan file lives in the repo's committed tree (one under ~/.claude/plans/, one
under the gitignored .omc/plans/), so this corpus cannot be CI-bound.
`--fix` (repairing a plan document's own citations) is deliberately NOT
implemented here: these files have an owner, and only they edit them --
this module reports, it does not repair.

Operating note -- this corpus is NOT a gate.
-------------------------------------------
The in-code corpus (scripts/gates/f11.sh --check, default) is CI-bound and
pre-commit-enforced, and must stay at zero. THIS corpus is a local audit tool
over the plan documents: run it when you are about to trust a citation, not as
a pass/fail gate.

A nonzero failure count here is its normal resting state, not a regression.
Measured: the corpus went from 26 to 60 stale citations in roughly thirty
minutes of ordinary commits, and one repair pass produced citations that had
drifted again before the same pass finished checking them. Chasing zero is
unbounded. Curate periodically; do not iterate toward zero, and do not wire
this half into CI -- it will go red and then be disabled, which is worse than
leaving it honest.

Do not anchor a citation inside frozen prose.
---------------------------------------------
Ledger entries and other append-only historical records are deliberately not
updated when code moves. An anchor on such a line resolves correctly and then
reports FAIL forever, because the prose it is attached to will never be
repaired. At a glance that is indistinguishable from a real defect, so it
trains readers to ignore red. Prune those rows rather than fixing them -- the
citation is not wrong, it is dated, and dated is the intended state.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import citations as C

FULL_RE = re.compile(r"(?P<file>[A-Za-z_][A-Za-z0-9_./]*\.py):(?P<spec>\d+(?:-\d+)?)")

# ---------------------------------------------------------------------------
# Shorthand continuation citations (s19) -- a bare `:N` that continues the
# most recently mentioned .py file, the plan-corpus equivalent of
# citations.py's BARE_RE/block tracking. Reusing that mechanism unmodified
# does not work here: citations.py updates `current_file_token` by scanning
# ALL full-form matches on a line FIRST and only then walking bare matches,
# so on a line mentioning several files it silently attributes every bare
# citation to whichever full-form file happened to be LAST on the line --
# never exposed in the code corpus (a comment run rarely names more than one
# file), but immediately wrong here: N25's own citation-drift finding names
# coordinator.py, then diagnostics.py, then cover.py and __init__.py, all on
# one line, and naive last-wins attribution puts EVERY bare citation in that
# chain on __init__.py. Fixed below by interleaving full-form and bare
# matches in true left-to-right ORDER, so a bare citation always continues
# the NEAREST PRECEDING file, not the line's last one.
#
# Two more properties prose needs that code did not:
#
# - ANY_FILE_RE, not just .py. A bare `:N` following a NON-.py reference
#   (`C18463s.java:123`, `MODEL_SPECIFIC_ENTITIES.md:9-15`) must not inherit
#   a stale .py file from earlier in the same block -- citations.py's
#   FULL_RE-is-.py-only design never needed this because code comments don't
#   cite Java or Markdown. Extensions below are every one actually cited in
#   the corpus as of 2026-08-22 (py, java, sh, md, graphql, txt) -- re-verify
#   this list at the next establishment pass rather than assuming it's still
#   exhaustive.
# - Markdown block boundaries, not comment/docstring boundaries. Bullet
#   lists here have NO blank line between items (` - foo\n- bar`), so a
#   naive "same paragraph" (blank-line-delimited) scope would leak a
#   full-form citation from bullet 1 into bullet 3's bare citation. Each
#   list-item marker, table row (`|...|`), and header is therefore its own
#   reset boundary; a bullet's own WRAPPED CONTINUATION lines (indented, no
#   marker) are not boundaries, so a citation can still span them -- verified
#   against a real case in the corpus (`- **Repoint coordinator.py:1000**
#   (now :1197...` wrapping onto an indented continuation line two lines
#   later, still `:1197`).
ANY_FILE_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_./-]*\.(?:py|java|sh|md|graphql|txt):\d+(?:-\d+)?"
)
BARE_RE = re.compile(r":(\d+)(?:-(\d+))?")
_LIST_ITEM_RE = re.compile(r"^\s*([-*+]|\d+\.)\s")
_TABLE_ROW_RE = re.compile(r"^\s*\|")
_HEADER_RE = re.compile(r"^#+\s")


def _is_block_boundary(line: str) -> bool:
    """True if LINE starts a fresh shorthand-tracking scope."""
    if not line.strip():
        return True
    return bool(
        _LIST_ITEM_RE.match(line)
        or _TABLE_ROW_RE.match(line.strip())
        or _HEADER_RE.match(line)
    )


def _iter_line_citations(lines: list[str]):
    """Yield (line_no, line_text, token, spec, is_shorthand, start) for every
    full-form AND shorthand .py citation in LINES, in document order. START
    is the citation's own character offset in line_text, for
    establish_one's proximity-based candidate ordering.
    """
    current_file: str | None = None
    for i, line in enumerate(lines, 1):
        if _is_block_boundary(line):
            current_file = None
        events = [("any", m.start(), m) for m in ANY_FILE_RE.finditer(line)]
        events += [("bare", m.start(), m) for m in BARE_RE.finditer(line)]
        events.sort(key=lambda e: e[1])
        any_spans = [m.span() for kind, _, m in events if kind == "any"]
        for kind, start, m in events:
            if kind == "any":
                token = m.group(0).rsplit(":", 1)[0]
                spec = m.group(0).rsplit(":", 1)[1]
                if token.endswith(".py"):
                    current_file = token
                    yield i, line, token, spec, False, start
                else:
                    current_file = None
                continue
            if any(s <= start < e for s, e in any_spans):
                continue  # already yielded as part of an "any" match above
            if start > 0 and line[start - 1] == "[":
                continue  # slice syntax, e.g. sha256[:12]
            if current_file is None:
                continue
            spec = f"{m.group(1)}-{m.group(2)}" if m.group(2) else m.group(1)
            yield i, line, current_file, spec, True, start


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
    for i, line, token, spec, _is_shorthand, _start in _iter_line_citations(lines):
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


# ---------------------------------------------------------------------------
# Anchor sidecar (s19) -- extends citations.py's mechanism to this corpus.
# ---------------------------------------------------------------------------

PLAN_ANCHORS_TSV = C.REPO_ROOT / "scripts" / "gates" / "helpers" / "plan_anchors.tsv"

DEFAULT_PLANS = (
    Path.home() / ".claude" / "plans" / "lets-emulate-the-apk-memoized-summit.md",
    C.REPO_ROOT / ".omc" / "plans" / "ralplan-audit-apk-parity-plan.md",
)

# Frozen documents (s19) -- declared here, not inferred, so the next person
# adding a plan file knows which bucket it belongs in and why.
#
# The criterion is append-only historical record vs. living spec. A frozen
# document is a record of a completed decision process (an audit, a review,
# a consensus write-up) whose citations were verified against the tree AS OF
# a specific commit and are deliberately never repaired afterward --
# repairing one would rewrite it against a tree that did not exist when the
# decision was made, misrepresenting what the evidence looked like at
# decision time (see this module's "Do not anchor a citation inside frozen
# prose" docstring section). A living document -- the plan of record itself,
# a spec still being executed against -- is expected to stay current, and a
# citation drifting there IS a defect worth fixing.
#
# Consequence: a frozen document's citations report FROZEN, not FAIL --
# never counted toward the fail total -- because a correctly-resolving
# anchor on prose that will never be repaired reports red FOREVER, which is
# indistinguishable at a glance from a live defect and trains readers to
# ignore red. Genuinely unresolvable citations (UNRESOLVED/OUT-OF-BOUNDS,
# from the bounds-checking layer) are NOT covered by this -- a frozen
# document's citations were in-bounds when written, so one that is not
# in-bounds now is more likely a tool parsing artifact (e.g. a shorthand
# citation misattributed to the wrong file) than expected staleness, and
# stays visible under its own existing tag rather than being folded into
# either FROZEN or FAIL.
FROZEN_PLANS: frozenset[str] = frozenset(
    {
        "ralplan-audit-apk-parity-plan.md",
    }
)

# Bare (unqualified) file tokens that are ambiguous by basename alone --
# multiple files in the repo share the name, and the plan corpus always
# means one specific one when it writes the SHORT form (it fully qualifies
# the other, e.g. "rivian_client/const.py", whenever it means that one).
# Verified by hand against every occurrence in the corpus at establishment
# time (2026-08-22): INVALID_SENSOR_STATES / SENSORS / BINARY_SENSORS only
# exist in the top-level const.py; every bare "rivian.py" citation concerns
# the vendored client (custom_components/rivian/rivian.py does not exist);
# every bare "__init__.py" citation concerns entry setup (entry.options,
# PLATFORMS, coordinators); "conftest.py" bare always means the main fixture
# file, not tests/client/conftest.py's much smaller helper.
BARE_TOKEN_DEFAULTS: dict[str, str] = {
    "const.py": "custom_components/rivian/const.py",
    "rivian.py": "custom_components/rivian/rivian_client/rivian.py",
    "conftest.py": "tests/conftest.py",
    "__init__.py": "custom_components/rivian/__init__.py",
    "diagnostics.py": "custom_components/rivian/diagnostics.py",
}


def load_plan_anchors(path: Path = PLAN_ANCHORS_TSV) -> tuple[C.AnchorRow, ...]:
    if not path.is_file():
        return ()
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cited_file, anchor, citing_file, citing_hash, note = line.split("\t", 4)
        rows.append(C.AnchorRow(cited_file, anchor, citing_file, citing_hash, note))
    return tuple(rows)


def write_plan_anchors(
    rows: tuple[C.AnchorRow, ...], path: Path = PLAN_ANCHORS_TSV
) -> None:
    header = [
        "# f11 --corpus plan sidecar -- see this file's module docstring.\n",
        "# Columns: cited-file\tanchor\tciting-file\tciting-line-sha256[:12]\tnote\n",
        '# "anchor" is matched as a literal substring (re.escape()d at load time), not a live regex.\n',
        "# citing-file is the plan document's basename (these files live outside\n",
        "# the repo, so a repo-relative path would not mean anything).\n",
    ]
    # NOT sorted: two citations to the SAME file on the SAME citing line share
    # (citing_file, citing_hash) and cannot be told apart by cited_file, so
    # AnchorIndex.take() disambiguates by row order == left-to-right
    # appearance order in the citing line (see AnchorIndex's docstring in
    # citations.py). Sorting here would scramble that and silently swap two
    # citations' anchors -- caught in establishment review (s19) when it did
    # exactly that to __init__.py:132/:303-305 and a coordinator.py pair.
    body = [
        f"{r.cited_file}\t{r.anchor}\t{r.citing_file}\t{r.citing_hash}\t{r.note}\n"
        for r in rows
    ]
    path.write_text("".join(header + body), encoding="utf-8")


def resolve_cited_file_broad(token: str, spec: str, all_py: list[Path]) -> Path | None:
    """Like citations.py's resolve_cited_file, but repo-wide (plan citations
    reach tests/, scripts/, rivian_client/ -- not just custom_components/)
    and with BARE_TOKEN_DEFAULTS consulted first for the tokens hand-verified
    ambiguous above.
    """
    if token in BARE_TOKEN_DEFAULTS:
        p = C.REPO_ROOT / BARE_TOKEN_DEFAULTS[token]
        if p.is_file():
            return p

    token_path = Path(token)
    root_relative = C.REPO_ROOT / token_path

    def in_bounds(p: Path) -> bool:
        _lo, hi = C._spec_to_range(spec)
        try:
            return hi <= len(
                p.read_text(encoding="utf-8", errors="replace").splitlines()
            )
        except OSError:
            return False

    if root_relative.is_file() and in_bounds(root_relative):
        return root_relative.resolve()

    matches = [p for p in all_py if p.name == token_path.name]
    exact = [p for p in matches if str(p).replace("\\", "/").endswith(str(token_path))]
    candidates = exact if exact else matches
    in_bounds_candidates = [p for p in candidates if in_bounds(p)]
    if len(in_bounds_candidates) == 1:
        return in_bounds_candidates[0].resolve()
    if len(candidates) == 1:
        return candidates[0].resolve()
    if root_relative.is_file():
        return root_relative.resolve()
    return None


# ---- establishment: mine the citing prose for what it actually claims ----

# `field="x"` / `key="x"` / any_word="literal" -- the single strongest signal
# a citation carries, because it names EXACT source text rather than a
# concept. Kept ahead of bare symbol names in priority for that reason.
KV_RE = re.compile(r'(\w+)="([^"]+)"')
BACKTICK_RE = re.compile(r"`([^`]+)`")
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MIN_ANCHOR_LEN = 8  # shorter than this and a fallback-to-spec anchor is too
# likely to be a bare `)`  or `else []`-style line with no real identity --
# several of those are attested as false "sound" citations in this exact
# corpus (coordinator.py:1488 -> ":1135 -- a bare )").


def _candidate_tokens(
    context_text: str, self_token: str, self_spec: str, near: int | None = None
) -> list[tuple[str, str]]:
    """Extract ('kv', literal) and ('sym', name) candidates from CITING
    prose. Filters out the citation's own `file.py:spec` (that names ITSELF,
    not content inside the cited file) and any OTHER `file.py:spec` span
    (those describe a DIFFERENT file's content, and searching for e.g.
    "async_setup_entry" -- named because it's what a DIFFERENT outbound
    citation points at -- inside THIS cited file would be a coincidence, not
    a signal; the uniqueness check below is what keeps a false one from being
    trusted, but it is cleaner not to offer it).

    Ordered by proximity to NEAR (the position, in context_text, of the
    citation actually being resolved) when given, nearest first, kv before
    sym at equal distance. A dense multi-citation line -- N25's drift finding
    alone names four files and one generic symbol ("VehicleCoordinator")
    across ~700 characters -- otherwise lets one candidate mentioned ANYWHERE
    on the line "win" for every citation on it, regardless of which citation
    it actually describes; sorting by distance from the citation's own
    position is what keeps a symbol named near citation 3 from resolving
    citation 1. NEAR=None keeps left-to-right document order (only used by
    callers that do not know their own position, if any remain).
    """
    self_full = f"{self_token}:{self_spec}"
    out: list[tuple[int, str, str]] = []
    for m in KV_RE.finditer(context_text):
        out.append((m.start(), "kv", f'{m.group(1)}="{m.group(2)}"'))
    for m in BACKTICK_RE.finditer(context_text):
        inner = m.group(1).strip()
        if inner == self_full or FULL_RE.fullmatch(inner):
            continue
        core = inner.split("(")[0].strip().rstrip(":")
        if IDENT_RE.match(core) and len(core) >= 4:
            out.append((m.start(), "sym", core))
    if near is not None:
        out.sort(key=lambda t: (abs(t[0] - near), 0 if t[1] == "kv" else 1))
    return [(kind, cand) for _pos, kind, cand in out]


def _grep_unique(text_lines: list[str], needle: str) -> int | None:
    pat = re.compile(re.escape(needle))
    hits = [i for i, line in enumerate(text_lines, 1) if pat.search(line)]
    return hits[0] if len(hits) == 1 else None


def _find_in_range(text_lines: list[str], lo: int, hi: int, needle: str) -> int | None:
    pat = re.compile(re.escape(needle))
    for i in range(lo, min(hi, len(text_lines)) + 1):
        if pat.search(text_lines[i - 1]):
            return i
    return None


def establish_one(
    plan_path: Path,
    line_no: int,
    line_text: str,
    token: str,
    spec: str,
    all_py: list[Path],
    near: int | None = None,
) -> tuple[str, C.AnchorRow | None, str]:
    """Returns (status, row_or_None, detail). status is one of:
    "established" (anchor found and verified unique), "needs-human" (nothing
    confident found -- prose cites a concept, not extractable content).

    NEAR is this citation's own character offset in LINE_TEXT (see
    _candidate_tokens) -- pass it whenever the caller has it, which is
    always, now that _iter_line_citations tracks match positions; omitting
    it falls back to document order, which is wrong on any line citing more
    than one file.
    """
    cited_path = resolve_cited_file_broad(token, spec, all_py)
    if cited_path is None:
        return "needs-human", None, f"cannot resolve cited file {token!r}"
    cited_rel = str(cited_path.relative_to(C.REPO_ROOT))
    target_lines = cited_path.read_text(encoding="utf-8", errors="replace").splitlines()

    lo, hi = C._spec_to_range(spec)
    for kind, cand in _candidate_tokens(line_text, token, spec, near=near):
        # Priority 0: does the CURRENTLY CITED range already contain what the
        # prose names? If so, trust that over any whole-file search --
        # otherwise a candidate like "update_listener" (present at its own
        # call site :132, but ALSO the name of a def elsewhere at :303)
        # gets dragged to the def site by symbol resolution below, reporting
        # false drift on a citation that was never wrong. Widen to the full
        # line for a stronger anchor once a real match is confirmed.
        in_range = _find_in_range(target_lines, lo, hi, cand)
        if in_range is not None:
            full_line = target_lines[in_range - 1].strip()
            if (
                len(full_line) >= MIN_ANCHOR_LEN
                and _grep_unique(target_lines, full_line) == in_range
            ):
                anchor, true_line = full_line, in_range
            elif _grep_unique(target_lines, cand) == in_range:
                anchor, true_line = cand, in_range
            else:
                continue  # matched in-range but can't build a file-unique anchor from it
        elif kind == "sym":
            sym_line = C.resolve_symbol(cited_path, cand)
            if sym_line is not None:
                anchor_line_text = target_lines[sym_line - 1].strip()
                anchor = (
                    anchor_line_text
                    if len(anchor_line_text) >= MIN_ANCHOR_LEN
                    else cand
                )
                if _grep_unique(target_lines, anchor) == sym_line:
                    true_line = sym_line
                else:
                    true_line = _grep_unique(target_lines, cand)
                    anchor = cand
                if true_line is None:
                    continue
            else:
                true_line = _grep_unique(target_lines, cand)
                anchor = cand
                if true_line is None:
                    continue
        else:  # kv, not found in-range
            true_line = _grep_unique(target_lines, cand)
            anchor = cand
            if true_line is None:
                continue

        note = (
            f"established from citing prose ({kind}:{anchor!r}); "
            f"{'matches cited spec' if lo <= true_line <= hi else f'DRIFTED -- cited :{spec}, real content at :{true_line}'}"
        )
        row = C.AnchorRow(
            cited_rel, anchor, plan_path.name, C.line_hash(line_text), note
        )
        status = "established"
        detail = f"{token}:{spec} -> {kind} {anchor!r} at :{true_line}" + (
            "" if lo <= true_line <= hi else f" (DRIFT: cited :{spec})"
        )
        return status, row, detail

    # No signal in the citing prose. Fall back to content actually at the
    # cited spec, IF it looks like real content rather than punctuation.
    if hi <= len(target_lines):
        raw = target_lines[lo - 1].strip()
        if len(raw) >= MIN_ANCHOR_LEN and _grep_unique(target_lines, raw) == lo:
            row = C.AnchorRow(
                cited_rel,
                raw,
                plan_path.name,
                C.line_hash(line_text),
                "established from content AT the cited spec (no extractable "
                "signal in citing prose) -- verify this is really what the "
                "citation means, not just what happens to be there",
            )
            return (
                "established",
                row,
                f"{token}:{spec} -> fallback-to-spec {raw!r}",
            )

    return (
        "needs-human",
        None,
        (
            f"{token}:{spec} -- no kv/symbol signal in citing prose, and content "
            "at the cited spec is not a distinctive enough anchor on its own"
        ),
    )


def run_establish(plan_paths: list[Path]) -> int:
    all_py = _repo_python_files()
    # Keyed on the full (citing_file, citing_hash, cited_file) triple, NOT
    # just (citing_file, citing_hash): a shared citing line can carry several
    # citations to DIFFERENT cited files (N25's finding alone spans
    # coordinator.py, diagnostics.py, cover.py and __init__.py on one line),
    # and keying on the pair alone would make establishing the FIRST citation
    # on such a line silently mark every OTHER citation on it as "already
    # covered" too.
    existing = {
        (r.citing_file, r.citing_hash, r.cited_file): r for r in load_plan_anchors()
    }
    new_rows: list[C.AnchorRow] = []
    established = 0
    needs_human = 0
    kept = 0
    for plan_path in plan_paths:
        lines = plan_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line, token, spec, _is_shorthand, start in _iter_line_citations(lines):
            h = C.line_hash(line)
            cited_path = resolve_cited_file_broad(token, spec, all_py)
            cited_rel = str(cited_path.relative_to(C.REPO_ROOT)) if cited_path else None
            if cited_rel is not None and (plan_path.name, h, cited_rel) in existing:
                kept += 1
                continue
            status, row, detail = establish_one(
                plan_path, i, line, token, spec, all_py, near=start
            )
            loc = f"{plan_path.name}:{i}"
            if status == "established" and row is not None:
                print(f"ESTABLISHED\t{loc}\t{detail}")
                new_rows.append(row)
                established += 1
            else:
                print(f"NEEDS-HUMAN\t{loc}\t{detail}")
                needs_human += 1
    all_rows = tuple(existing.values()) + tuple(new_rows)
    write_plan_anchors(all_rows)
    print(
        f"CENSUS\testablished={established} needs_human={needs_human} "
        f"already_present={kept} total_rows_written={len(all_rows)}"
    )
    return 0


def check_with_anchors(plan_paths: list[Path]) -> int:
    """Real content verification for every citation an anchor row covers;
    bounds-only UNVERIFIED (as before) for everything else.

    A citation in a FROZEN_PLANS document that would otherwise FAIL prints
    FROZEN instead and does not count toward fail_ct -- see FROZEN_PLANS'
    docstring for why. PASS is unaffected: a frozen document's citations
    that still happen to resolve correctly are still worth showing as such.
    """
    anchors = C.AnchorIndex(load_plan_anchors())
    all_py = _repo_python_files()
    total = 0
    pass_ct = 0
    fail_ct = 0
    frozen_ct = 0
    unanchored = 0
    for plan_path in plan_paths:
        frozen = plan_path.name in FROZEN_PLANS
        fail_tag = "FROZEN" if frozen else "FAIL"
        lines = plan_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line, token, spec, _is_shorthand, _start in _iter_line_citations(lines):
            total += 1
            loc = f"{plan_path.name}:{i}"
            cited_path = resolve_cited_file_broad(token, spec, all_py)
            if cited_path is None:
                print(f"{fail_tag}\t{loc}\t{token}:{spec}\tcannot resolve cited file")
                frozen_ct += 1 if frozen else 0
                fail_ct += 0 if frozen else 1
                continue
            cited_rel = str(cited_path.relative_to(C.REPO_ROOT))
            row = anchors.take(plan_path.name, C.line_hash(line), cited_rel)
            if row is None:
                unanchored += 1
                continue
            target_lines = cited_path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
            hits = [
                j
                for j, tl in enumerate(target_lines, 1)
                if re.search(re.escape(row.anchor), tl)
            ]
            lo, hi = C._spec_to_range(spec)
            if len(hits) != 1:
                print(
                    f"{fail_tag}\t{loc}\t{token}:{spec}\tanchor {row.anchor!r} not "
                    f"uniquely found in {row.cited_file} (hits={len(hits)}) -- {row.note}"
                )
                frozen_ct += 1 if frozen else 0
                fail_ct += 0 if frozen else 1
            elif lo <= hits[0] <= hi:
                print(f"PASS\t{loc}\t{token}:{spec}\tmatches content at :{hits[0]}")
                pass_ct += 1
            else:
                print(
                    f"{fail_tag}\t{loc}\t{token}:{spec}\tcites :{spec} but content is "
                    f"now at :{hits[0]} -- {row.note}"
                )
                frozen_ct += 1 if frozen else 0
                fail_ct += 0 if frozen else 1
    print(
        f"CENSUS\ttotal={total} pass={pass_ct} fail={fail_ct} "
        f"frozen={frozen_ct} unanchored={unanchored}"
    )
    if frozen_ct:
        # Tag differs from the per-citation "FROZEN" rows above (which carry
        # loc/target/detail) so a naive tab-split parser -- f11.sh's -- does
        # not mistake this summary line for one more citation.
        print(
            f"FROZEN-SUMMARY\t{frozen_ct} citation(s) are in a document "
            "declared in FROZEN_PLANS -- dated, not broken. Never repair "
            "these; see this file's 'Do not anchor a citation inside frozen "
            "prose' docstring."
        )
    if unanchored:
        print(
            f"UNVERIFIED\t{unanchored} citation(s) have no anchor row yet -- "
            "bounds-only for those (run --establish to add coverage). "
            "pass/fail above IS a real correctness signal for the rest."
        )
    return 0 if fail_ct == 0 else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(
            "usage: plan_citations.py [--check|--establish] <plan.md> [<plan2.md> ...]",
            file=sys.stderr,
        )
        raise SystemExit(2)
    mode = "--check"
    paths = args
    if args[0] in ("--check", "--establish"):
        mode = args[0]
        paths = args[1:]
    if not paths:
        paths = [str(p) for p in DEFAULT_PLANS if p.is_file()]
    plan_paths = [Path(p) for p in paths]
    if mode == "--establish":
        raise SystemExit(run_establish(plan_paths))
    # --check: bounds-only pass first (unchanged contract), then real
    # content verification for whatever plan_anchors.tsv covers.
    bounds_rc = audit(plan_paths)
    anchor_rc = check_with_anchors(plan_paths)
    raise SystemExit(bounds_rc or anchor_rc)
