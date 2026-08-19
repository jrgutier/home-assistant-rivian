#!/usr/bin/env python3
"""Print a Python file's CODE, with comments and docstrings removed.

Gates that grep a source file's raw text read its comments too. Every comment
this project writes about a removed flag names the flag -- "keyed on the field,
not on TONNEAU_CMD" -- so a raw grep for the flag finds the note explaining its
removal and reports it is still in use. That has now defeated gates in this repo
twice: once on the workflows (see workflow_runs.py) and once on cover.py.

Docstrings go too, for the same reason: a module docstring explaining why a name
was dropped is prose, not a reference.

Usage: py_code_only.py <file.py> [<file.py> ...]
"""

from __future__ import annotations

import io
import sys
import tokenize

# A STRING token following one of these, at bracket depth 0, is a statement on
# its own -- a docstring -- rather than part of an expression.
#
# NL is deliberately NOT in this set. NL is the non-logical newline that appears
# INSIDE brackets, so including it strips every quoted dict key and list element
# that sits on its own line -- which is the shape of every gate table in this
# codebase. The first draft did include it and silently reported that cover.py
# contains no LIFTGATE_CMD.
_STATEMENT_START = frozenset(
    {
        tokenize.ENCODING,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.NEWLINE,
    }
)


def code_only(path: str) -> str:
    """Return `path`'s source with comments and docstrings stripped."""
    with open(path, "rb") as fh:
        source = fh.read()
    try:
        tokens = list(tokenize.tokenize(io.BytesIO(source).readline))
    except (tokenize.TokenError, SyntaxError):
        # Unparseable: hand back the raw text rather than an empty string. A gate
        # must never read a file it could not parse as "clean" -- that is the
        # grep-exits-2 failure in another costume.
        return source.decode("utf-8", "replace")

    kept: list[str] = []
    prev = tokenize.ENCODING
    depth = 0
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.OP:
            if tok.string in "([{":
                depth += 1
            elif tok.string in ")]}":
                depth = max(0, depth - 1)
        # Inside brackets there are no statements, so no docstrings either.
        if tok.type == tokenize.STRING and depth == 0 and prev in _STATEMENT_START:
            continue
        kept.append(tok.string)
        prev = tok.type
    return "\n".join(kept)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: py_code_only.py <file.py> [<file.py> ...]")
    for arg in sys.argv[1:]:
        print(code_only(arg))
