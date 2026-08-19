"""Full schema for one protobuf message class: fields, wire kinds, enum values.

R8 keeps three things intact in protobuf-generated code, which is the whole
reason this is recoverable: `<FIELD>_FIELD_NUMBER` constants, the `<field>_`
instance members with their Java types, and enum constants with their numbers.
It renames the CLASS (`hk8`) and the enum (`gk8`), so those come from the app's
decoder dispatch instead.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

FIELD_NUM = re.compile(r"public static final int ([A-Z0-9_]+)_FIELD_NUMBER = (\d+);")
MEMBER = re.compile(
    r"^\s+private (?:volatile )?([\w.<>\[\], ]+?) (\w+)_;", re.MULTILINE
)
ENUMVAL = re.compile(r"^    ([A-Z][A-Z0-9_]*)\((-?\d+)\)[,;]?$", re.MULTILINE)
# `public gk8 D() { ... gk8.a(this.gear_) ... }` links a field to its enum class
ENUMLINK = re.compile(r"(\w+)\.\w+\(this\.(\w+)_\)")


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def schema(root: Path, cls: str) -> dict:
    text = (root / f"{cls}.java").read_text(errors="replace")
    members = {snake(n): t for t, n in MEMBER.findall(text)}
    enum_of = {snake(field): enum for enum, field in ENUMLINK.findall(text)}
    fields = {}
    for name, num in FIELD_NUM.findall(text):
        key = name.lower()
        entry = {"number": int(num), "java_type": members.get(key)}
        if enum := enum_of.get(key):
            path = root / f"{enum}.java"
            if path.is_file():
                vals = ENUMVAL.findall(path.read_text(errors="replace"))
                if vals:
                    entry["enum"] = enum
                    entry["values"] = {int(v): n for n, v in vals if int(v) >= 0}
        fields[key] = entry
    return {
        "class": cls,
        "fields": dict(sorted(fields.items(), key=lambda kv: kv[1]["number"])),
    }


if __name__ == "__main__":
    root = Path(sys.argv[1])
    out = {c: schema(root, c) for c in sys.argv[2:]}
    json.dump(out, sys.stdout, indent=1)
