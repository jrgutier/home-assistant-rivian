"""Per-version Parallax schema and topic bindings, read off a jadx tree.

Where `topic_map.py` pairs a topic guard with a `Base64.decode` parse in the same
method, this finds every caller of every generated parse wrapper, so a site that
decodes into a local first (`fgk.F(bArrDecode)`) is not missed. Wire kinds come
from the protobuf-lite RawMessageInfo string each message class carries, which is
exact where the Java member type is not (`int` is int32, uint32, sint32 or enum).

A parse site is bound to a topic one of three ways, and the output says which:

    direct           the enclosing method names exactly one RVM enum member
    via_caller       it names none, and its callers between them name exactly one
    lambda_registry  it is one `case N:` of a synthetic lambda class, and the
                     `new Lambda(N)` that selects it sits after exactly one RVM
                     member in the constructing method (nearest preceding wins)

Everything else lands in `unbound_parse_sites_*.json` rather than being guessed.

usage: apk_parallax_schema.py <jadx sources root> <version> <out dir>
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

# FieldType ids from protobuf-java's com.google.protobuf.FieldType.
SCALAR = [
    "double", "float", "int64", "uint64", "int32", "fixed64", "fixed32", "bool",
    "string", "message", "bytes", "uint32", "enum", "sfixed32", "sfixed64",
    "sint32", "sint64", "group",
]  # fmt: skip
PACKED = [
    "double", "float", "int64", "uint64", "int32", "fixed64", "fixed32", "bool",
    "uint32", "enum", "sfixed32", "sfixed64", "sint32", "sint64",
]  # fmt: skip

INFO = re.compile(
    r'e\.\w+\(DEFAULT_INSTANCE, "((?:[^"\\]|\\.)*)", (null|new Object\[\]\{(.*?)\})\);',
    re.DOTALL,
)
FIELD_NUM = re.compile(r"public static final int ([A-Z0-9_]+)_FIELD_NUMBER = (\d+);")
MEMBER = re.compile(
    r"^\s+private (?:volatile )?([\w.<>\[\], ?]+?) (\w+)_(?: = [^;]+)?;", re.MULTILINE
)
ENUMLINK = re.compile(r"(\w+)\.\w+\(this\.(\w+)_\)")
ENUMVAL = re.compile(r"^    ([A-Z][A-Z0-9_]*)\((-?\d+)\)[,;]?$", re.MULTILINE)
WRAPPER = re.compile(
    r"public static (\w+) (\w+)\(([^)]*)\)[^{;]*\{\s*return \(\1\) e\.\w+\(DEFAULT_INSTANCE, "
)
METHOD = re.compile(
    r"^[ \t]+(?:[\w<>\[\], .?@]+ )?(\w+)\([^;{}]*\)[^;{}]*\{[ \t]*$", re.MULTILINE
)
RVM_ENTRY = re.compile(
    r'\b([A-Z][A-Z0-9_]*)(?: = new \w+)?\((?:"\1", \d+, )?"([a-zA-Z_]+\.[\w.]+)"'
)
ESC = {
    "b": "\b",
    "t": "\t",
    "n": "\n",
    "f": "\f",
    "r": "\r",
    '"': '"',
    "'": "'",
    "\\": "\\",
}


def unescape(lit: str) -> str:
    out, i = [], 0
    while i < len(lit):
        c = lit[i]
        if c != "\\":
            out.append(c)
            i += 1
        elif lit[i + 1] == "u":
            out.append(chr(int(lit[i + 2 : i + 6], 16)))
            i += 6
        else:
            out.append(ESC[lit[i + 1]])
            i += 2
    return "".join(out)


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def split_objects(src: str | None) -> list[str]:
    return [o.strip() for o in src.split(",")] if src else []


def decode_info(info: str, objects: list[str]) -> list[dict]:
    """RawMessageInfo -> [{number, wire_kind, repeated, packed, member, ref, oneof}]."""
    pos = 0

    def nxt() -> int:
        nonlocal pos
        value = shift = 0
        while True:
            c = ord(info[pos])
            pos += 1
            if c < 0xD800:
                return value | (c << shift)
            value |= (c & 0x1FFF) << shift
            shift += 13

    flags, count = nxt(), nxt()
    if count == 0:
        return []
    oneofs, hasbits = nxt(), nxt()
    for _ in range(6):  # min, max, entries, map count, repeated count, check-init
        nxt()
    proto2 = bool(flags & 1)
    obj = oneofs * 2 + hasbits
    oneof_names = [objects[i * 2].strip('"').rstrip("_") for i in range(oneofs)]
    fields = []
    while pos < len(info):
        number, typ = nxt(), nxt()
        kind = typ & 0xFF
        closed_enum = proto2 or bool(typ & 0x800)
        f = {"number": number, "repeated": False, "packed": False}
        if kind >= 51:
            base = kind - 51
            f["wire_kind"] = SCALAR[base]
            f["oneof"] = oneof_names[nxt()]
            if base in (9, 17) or (base == 12 and closed_enum):
                f["ref"] = objects[obj]
                obj += 1
        else:
            f["member"] = objects[obj].strip('"')
            obj += 1
            if kind <= 17:
                f["wire_kind"] = SCALAR[kind]
                if kind == 12 and closed_enum:
                    f["ref"] = objects[obj]
                    obj += 1
            elif kind <= 34:
                f["wire_kind"], f["repeated"] = SCALAR[kind - 18], True
                if kind in (27,) or (kind == 30 and closed_enum):
                    f["ref"] = objects[obj]
                    obj += 1
            elif kind <= 48:
                f["wire_kind"], f["repeated"], f["packed"] = (
                    PACKED[kind - 35],
                    True,
                    True,
                )
                if kind == 44 and closed_enum:
                    f["ref"] = objects[obj]
                    obj += 1
            elif kind == 49:
                f["wire_kind"], f["repeated"] = "group", True
                f["ref"] = objects[obj]
                obj += 1
            else:
                f["wire_kind"] = "map"
                f["ref"] = objects[obj]
                obj += 1
                if typ & 0x800:  # map value enum verifier
                    obj += 1
            if kind <= 17 and typ & 0x1000:
                nxt()  # has-bit index
        fields.append(f)
    return fields


class Tree:
    def __init__(self, root: Path):
        self.root = root
        self.text: dict[str, str] = {}
        self.by_stem: dict[str, str] = {}
        for path in sorted(root.rglob("*.java")):
            rel = str(path.relative_to(root))
            self.text[rel] = path.read_text(errors="replace")
            if rel.startswith("defpackage/") or path.stem not in self.by_stem:
                self.by_stem[path.stem] = rel
        self.messages = {
            Path(rel).stem: rel for rel, t in self.text.items() if INFO.search(t)
        }
        self._enum: dict[str, dict | None] = {}

    def enum(self, cls: str) -> dict | None:
        if cls not in self._enum:
            rel = self.by_stem.get(cls)
            vals = ENUMVAL.findall(self.text[rel]) if rel else []
            if rel and not vals:  # jadx could not restore the enum modifier
                vals = re.findall(
                    rf'new {cls}\("([A-Z][A-Z0-9_]*)", \d+, (-?\d+)\)', self.text[rel]
                )
            self._enum[cls] = {n: int(v) for n, v in vals if int(v) >= 0} or None
        return self._enum[cls]

    def message(self, cls: str, seen: tuple = ()) -> dict:
        text = self.text[self.messages[cls]]
        m = INFO.search(text)
        names = {int(n): name.lower() for name, n in FIELD_NUM.findall(text)}
        members = {n: t for t, n in MEMBER.findall(text)}
        enum_of = {field: enum for enum, field in ENUMLINK.findall(text)}
        fields = {}
        for f in decode_info(unescape(m.group(1)), split_objects(m.group(3))):
            member = f.get("member", "").rstrip("_")
            entry = {
                "number": f["number"],
                "java_type": members.get(member),
                "wire_kind": f["wire_kind"],
            }
            if f["repeated"]:
                entry["repeated"] = True
            if "oneof" in f:
                entry["oneof"] = f["oneof"]
            ref = f.get("ref", "").removesuffix(".class")
            if f["wire_kind"] == "enum":
                enum_cls = enum_of.get(member)
                entry["enum_class"] = enum_cls
                entry["enum"] = self.enum(enum_cls) if enum_cls else None
            elif f["wire_kind"] in ("message", "group"):
                target = ref or (members.get(member) or "").split(".")[-1]
                entry["message_class"] = target or None
                if target in self.messages and target not in seen and target != cls:
                    entry["message"] = self.message(target, (*seen, cls))["fields"]
            elif f["wire_kind"] == "map":
                entry["map_entry"] = ref
            name = names.get(f["number"]) or snake(member) or f"field_{f['number']}"
            fields[name] = entry
        return {"class": cls, "fields": fields}

    def enclosing(self, rel: str, offset: int) -> tuple[str, str, int]:
        """(method name, brace-matched body, body start) of the method at offset."""
        text = self.text[rel]
        best = None
        for m in METHOD.finditer(text, 0, offset):
            if m.group(1) not in {
                "if",
                "for",
                "while",
                "switch",
                "catch",
                "synchronized",
            }:
                best = m
        if best is None:
            return "", "", 0
        depth, j = 0, best.end() - 1
        while j < len(text):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        return best.group(1), text[best.start() : j + 1], best.start()


def rvm_enums(tree: Tree) -> dict[str, dict[str, str]]:
    """Every class declaring 2+ members whose string argument is a dotted RVM name."""
    out = {}
    for rel, text in tree.text.items():
        if "getRvmName" not in text and "rvmName" not in text:
            continue
        entries = {n: v for n, v in RVM_ENTRY.findall(text) if v.count(".") >= 2}
        if len(entries) >= 2:
            out[Path(rel).stem] = entries
    return out


def call_sites(tree: Tree, enums: dict[str, dict[str, str]]) -> list[dict]:
    wrappers = set()
    for cls, rel in tree.messages.items():
        for _, method, _args in WRAPPER.findall(tree.text[rel]):
            wrappers.add((cls, method))
    if not wrappers:
        return []
    call = re.compile(
        r"\b(" + "|".join(sorted(f"{c}\\.{m}" for c, m in wrappers)) + r")\("
    )
    topic_ref = re.compile(r"\b(" + "|".join(enums) + r")\.([A-Z][A-Z0-9_]+)\b")

    def topics(body: str) -> list[str]:
        return sorted(
            {enums[e][n] for e, n in topic_ref.findall(body) if n in enums[e]}
        )

    sites = []
    for rel, text in tree.text.items():
        stem = Path(rel).stem
        for m in call.finditer(text):
            cls = m.group(1).split(".")[0]
            if stem == cls or rel.startswith(("com/google/", "androidx/")):
                continue
            name, body, start = tree.enclosing(rel, m.start())
            site = {
                "class": cls,
                "site": f"{rel}:{text.count(chr(10), 0, m.start()) + 1}",
                "method": f"{stem}.{name}",
                "base64": "Base64.decode" in body,
                "topics": topics(body),
                "caller_topics": {},
                "registry_topics": {},
            }
            if not site["topics"] and name:
                caller = re.compile(rf"\b{re.escape(stem)}\.{re.escape(name)}\(")
                for rel2, text2 in tree.text.items():
                    for c in caller.finditer(text2):
                        _, body2, _ = tree.enclosing(rel2, c.start())
                        for t in topics(body2):
                            line = text2.count(chr(10), 0, c.start()) + 1
                            site["caller_topics"].setdefault(t, f"{rel2}:{line}")
            cases = re.findall(r"case (\d+):", body[: m.start() - start])
            if not site["topics"] and name.startswith("invoke") and cases:
                ctor = re.compile(rf"new {re.escape(stem)}\((?:[^()]*, )?{cases[-1]}\)")
                for rel2, text2 in tree.text.items():
                    for c in ctor.finditer(text2):
                        _, body2, start2 = tree.enclosing(rel2, c.start())
                        before = [
                            enums[e][n]
                            for e, n in topic_ref.findall(body2[: c.start() - start2])
                            if n in enums[e]
                        ]
                        if before:
                            line = text2.count(chr(10), 0, c.start()) + 1
                            site["registry_topics"].setdefault(
                                before[-1], f"{rel2}:{line}"
                            )
            sites.append(site)
    return sorted(sites, key=lambda s: s["site"])


def main(root: Path, version: str, out: Path, wanted: list[str]) -> None:
    tree = Tree(root)
    enums = rvm_enums(tree)
    sites = call_sites(tree, enums)

    schema, unbound = {}, []
    for s in sites:
        if len(s["topics"]) == 1:
            topic, how, where = s["topics"][0], "direct", s["site"]
        elif not s["topics"] and len(s["caller_topics"]) == 1:
            topic, how, where = next(iter(s["caller_topics"])), "via_caller", s["site"]
        elif not s["topics"] and len(s["registry_topics"]) == 1:
            topic, how, where = (
                next(iter(s["registry_topics"])),
                "lambda_registry",
                s["site"],
            )
        else:
            unbound.append({**s, **tree.message(s["class"])})
            continue
        entry = {
            "class": s["class"],
            "dispatch_site": where,
            "binding": how,
            **(
                {"caller_site": s["caller_topics"][topic]}
                if how == "via_caller"
                else {}
            ),
            **(
                {"registry_site": s["registry_topics"][topic]}
                if how == "lambda_registry"
                else {}
            ),
            "fields": tree.message(s["class"])["fields"],
        }
        schema.setdefault(topic, []).append(entry)
    flat = {t: (v[0] if len(v) == 1 else v) for t, v in sorted(schema.items())}

    all_topics = {v: (e, n) for e, d in enums.items() for n, v in d.items()}
    check = {}
    for t in wanted:
        hits = sorted(rel for rel, text in tree.text.items() if f'"{t}"' in text)
        if t in flat:
            b = flat[t] if isinstance(flat[t], dict) else flat[t][0]
            row = {"status": "bound", "class": b["class"], "site": b["dispatch_site"],
                   "binding": b["binding"]}  # fmt: skip
        elif hits:
            row = {"status": "referenced_only"}
        else:
            row = {"status": "absent"}
        if t in all_topics:
            row["rvm_enum"], row["member"] = all_topics[t]
        row["string_in"] = hits
        check[t] = row

    out.mkdir(parents=True, exist_ok=True)

    def dump(name: str, data) -> None:
        (out / name).write_text(json.dumps(data, indent=1) + "\n")

    dump(f"apk_parallax_schema_{version}.json", flat)
    dump(
        f"bindings_check_{version}.json",
        {"version": version, "topics": check, "rvm_enums": enums},
    )
    dump(f"unbound_parse_sites_{version}.json", unbound)
    parsed = {s["class"] for s in sites}
    dump(
        f"uncalled_parse_wrappers_{version}.json",
        {
            c: tree.message(c)["fields"]
            for c in sorted(tree.messages)
            if c not in parsed and WRAPPER.search(tree.text[tree.messages[c]])
        },
    )
    dump(
        f"message_index_{version}.json",
        {
            c: {
                n: [f["number"], f["wire_kind"] + ("[]" if f.get("repeated") else "")]
                for n, f in tree.message(c, (c,))["fields"].items()
            }
            for c in sorted(tree.messages)
        },
    )
    print(
        f"{version}: {len(tree.messages)} message classes, {len(sites)} parse sites, "
        f"{len(flat)} topics bound, {len(unbound)} unbound sites, "
        f"enums { ({e: len(d) for e, d in enums.items()}) }",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main(
        Path(sys.argv[1]),
        sys.argv[2],
        Path(sys.argv[3]),
        Path(sys.argv[4]).read_text().split() if len(sys.argv) > 4 else [],
    )
