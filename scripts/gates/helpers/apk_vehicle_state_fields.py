"""Top-level VehicleState field names, from the app's five compiled documents.

A regex over `name { timeStamp value }` is wrong: the five documents do not share
a shape. wcm/cdm/apj use that form, h9l is `activeDriverName { value }`, and lel
is `gnssLocation { consentStatus }`. Matching one shape silently drops two whole
documents -- measured: wcm 125, cdm 122, apj 8, h9l 0, lel 0.

So this walks the selection set instead, resolving fragment spreads, and takes
the names at depth 1 of anything selected on VehicleState.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys


def _extract_documents(java: str) -> list[str]:
    return re.findall(r'return "(subscription [^"]*)";', java)


def _split_top_level(body: str) -> list[str]:
    """Yield the depth-1 tokens of a selection-set body."""
    out, depth, current = [], 0, []
    for ch in body:
        if ch == "{":
            depth += 1
            current.append(ch)
        elif ch == "}":
            depth -= 1
            current.append(ch)
            if depth == 0:
                out.append("".join(current).strip())
                current = []
        elif depth == 0 and ch.isspace():
            if current:
                out.append("".join(current).strip())
                current = []
        else:
            current.append(ch)
    if current:
        out.append("".join(current).strip())
    return [t for t in out if t]


def _selection_names(body: str, fragments: dict[str, str]) -> set[str]:
    """Depth-1 field names of a selection set, resolving spreads."""
    names: set[str] = set()
    for tok in _split_top_level(body):
        if tok.startswith("..."):
            if tok[3:] in fragments:
                names |= _selection_names(fragments[tok[3:]], fragments)
        # A `{...}` token is the nested selection set of the previous field.
        elif not tok.startswith("{") and tok != "__typename":
            names.add(tok)
    return names


def _balanced_body(doc: str, start: int) -> str:
    """The selection set whose opening `{` ends just before `start`.

    Brace-matched, because a lazy regex stops at the first `}`, which is wrong
    for nested selections.
    """
    depth, i = 1, start
    while depth:
        if doc[i] == "{":
            depth += 1
        elif doc[i] == "}":
            depth -= 1
        i += 1
    return doc[start : i - 1]


def fields_for(java_path: Path) -> set[str]:
    java = java_path.read_text()
    names: set[str] = set()
    for doc in _extract_documents(java):
        fragments = {
            m.group(1): _balanced_body(doc, m.end())
            for m in re.finditer(r"fragment (\w+) on VehicleState \{", doc)
        }
        for m in re.finditer(r"vehicleState\(id: \$vehicleID\) \{", doc):
            names |= _selection_names(_balanced_body(doc, m.end()), fragments)
    return names


if __name__ == "__main__":
    apk = Path(sys.argv[1])
    union: set[str] = set()
    for name in ("wcm", "cdm", "apj", "h9l", "lel"):
        got = fields_for(apk / f"{name}.java")
        print(f"{name}: {len(got)}", file=sys.stderr)
        union |= got
    print(f"union: {len(union)}", file=sys.stderr)
    for f in sorted(union):
        print(f)
