"""Index every protobuf message class in the decompiled app.

R8 renames the classes (`lol`, `dee`, …) and renames GeneratedMessageLite itself
to `com.google.protobuf.e`, which is why a grep for "GeneratedMessageLite" finds
nothing and the schema looks absent. What R8 does NOT rename is the generated
`<FIELD>_FIELD_NUMBER` constants or the `<field>_` instance fields, so every
message's field names, numbers and Java types survive intact.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

FIELD_NUM = re.compile(r"public static final int ([A-Z0-9_]+)_FIELD_NUMBER = (\d+);")
MEMBER = re.compile(
    r"^\s+(?:private|public|protected)?\s*(?:volatile\s+)?([\w.<>\[\]]+) (\w+)_;",
    re.MULTILINE,
)
EXTENDS = re.compile(r"public final class (\w+) extends (\S+)")


def index(root: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in root.rglob("*.java"):
        text = path.read_text(errors="replace")
        nums = FIELD_NUM.findall(text)
        if not nums:
            continue
        members = {name: typ for typ, name in MEMBER.findall(text)}
        m = EXTENDS.search(text)
        out[path.stem] = {
            "file": str(path),
            "extends": m.group(2) if m else None,
            "fields": {
                name.lower(): {
                    "number": int(num),
                    "java_type": members.get(name.lower()),
                }
                for name, num in nums
            },
        }
    return out


if __name__ == "__main__":
    idx = index(Path(sys.argv[1]))
    print(f"{len(idx)} message classes", file=sys.stderr)
    json.dump(idx, sys.stdout, indent=1, sort_keys=True)
