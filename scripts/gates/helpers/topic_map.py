"""Topic -> protobuf message class, by pairing each l6e guard with the parse call
in the same brace-delimited method body."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

TOPIC = re.compile(r"l6e\.([A-Z][A-Z0-9_]+)")
PARSE = re.compile(r"\b(\w+)\.\w+\(Base64\.decode\(")


def methods(text: str):
    """Yield each top-level method body (indent 4, brace matched)."""
    for m in re.finditer(r"^    [\w<>\[\], .]+ \w+\([^)]*\) \{", text, re.MULTILINE):
        i = m.end() - 1
        depth = 0
        j = i
        while j < len(text):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        yield text[m.start() : j + 1]


def main(paths):
    out: dict[str, set[str]] = {}
    for p in paths:
        text = Path(p).read_text(errors="replace")
        for body in methods(text):
            topics = {t for t in TOPIC.findall(body) if t not in {"Companion"}}
            classes = set(PARSE.findall(body))
            if len(topics) == 1 and classes:
                out.setdefault(next(iter(topics)), set()).update(classes)
    return {k: sorted(v) for k, v in sorted(out.items())}


if __name__ == "__main__":
    mapping = main(sys.argv[1:])
    print(f"{len(mapping)} topics mapped", file=sys.stderr)
    json.dump(mapping, sys.stdout, indent=1)
