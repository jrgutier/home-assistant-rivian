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
    tokens = _split_top_level(body)
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("..."):
            spread = tok[3:]
            if spread in fragments:
                names |= _selection_names(fragments[spread], fragments)
            i += 1
            continue
        if tok.startswith("{"):
            # a nested selection set belonging to the previous field; skip
            i += 1
            continue
        if tok == "__typename":
            i += 1
            continue
        # a field; its selection set, if any, is the next token
        names.add(tok)
        i += 1
    return names


def fields_for(java_path: Path) -> set[str]:
    java = java_path.read_text()
    names: set[str] = set()
    for doc in _extract_documents(java):
        fragments = {
            name: body
            for name, body in re.findall(
                r"fragment (\w+) on VehicleState \{(.*?)\}\s*(?=fragment |$)",
                doc,
                re.DOTALL,
            )
        }
        # Balance the fragment bodies: the lazy regex above stops at the first
        # `}`, which is wrong for nested selections. Re-extract by brace matching.
        fragments = {}
        for m in re.finditer(r"fragment (\w+) on VehicleState \{", doc):
            start = m.end()
            depth = 1
            i = start
            while depth:
                if doc[i] == "{":
                    depth += 1
                elif doc[i] == "}":
                    depth -= 1
                i += 1
            fragments[m.group(1)] = doc[start : i - 1]

        for m in re.finditer(r"vehicleState\(id: \$vehicleID\) \{", doc):
            start = m.end()
            depth = 1
            i = start
            while depth:
                if doc[i] == "{":
                    depth += 1
                elif doc[i] == "}":
                    depth -= 1
                i += 1
            names |= _selection_names(doc[start : i - 1], fragments)
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
