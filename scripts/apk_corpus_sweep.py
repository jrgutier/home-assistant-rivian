#!/usr/bin/env python3
"""Sweep every decompiled Rivian Android dump for commands, queries and features.

The integration's command list, its `vehicleState` field set and its capability
gates were all reconstructed from the app. Each was read out of ONE dump, by
hand, at the time it was needed -- which is why nobody can say when a name
appeared, when it changed spelling, or whether a name we ship was ever real.
This walks all of the dumps at once so those questions have a mechanical answer.

Three deliberate constraints, each of them a bug we already shipped:

CORPUS IS AN ALLOWLIST, NEVER A GLOB. `~/src/rivian*` also matches
`rivian-dump/`, which is ABRP telemetry JSON and not an app dump at all. The
directory names are irregular on purpose-of-history -- `rivian_2.0.0_beta` has
an underscore, `rivian_2.5.0 beta` has a SPACE, and 2.5.1 onward are named for
the package -- so they are spelled out below and every one is a `Path`, never a
string spliced into a shell word.

LAYOUT IS DISCOVERED, NOT DERIVED FROM THE VERSION. The sources sit under
`sources/` in the 1.x dumps AND in `rivian_2.0.0_beta`, under `java_src/` from
2.2.0 on, and directly under the root of the repo-local jadx tree. There is no
rule mapping version to layout, so nothing here builds a package subpath: it
walks from the root and matches on basename and file content. It also walks
`*.java` only -- a `.dex` blob under `resources/` carries the same byte
sequences and inflates every count that touches it.

MATCHES ARE WHOLE-WORD. `wiperFluidState` is a real field and also a prefix of
the Room column `wiperFluidStateUpdatedTimestamp`; substring matching silently
conflates the two. Every name match here is `\\b`-anchored.

A version that yields no commands is reported as an ERROR rather than skipped,
because "the parse broke" and "the app had no commands" look identical in a
summary line and only one of them is ever true.

Usage:
    python scripts/apk_corpus_sweep.py [--src-root ~/src] [--only VERSION ...] [--json]
    python scripts/apk_corpus_sweep.py --ledger    # one row per command
    python scripts/apk_corpus_sweep.py --sensors   # four sensor-surface deltas
"""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable
import json
from pathlib import Path
import re
import sys

# Version -> literal directory name under --src-root. Spelled out, never globbed.
# `2.5.0_beta` really does live in a directory with a space in it.
SRC_DUMPS: dict[str, str] = {
    "1.0.3": "rivian_1.0.3",
    "1.2.1": "rivian_1.2.1",
    "1.3.0": "rivian_1.3.0",
    "1.3.1": "rivian_1.3.1",
    "1.4.0": "rivian_1.4.0",
    "1.4.1": "rivian_1.4.1",
    "1.5.1": "rivian_1.5.1",
    "1.6.0": "rivian_1.6.0",
    "1.7.0": "rivian_1.7.0",
    "1.7.1": "rivian_1.7.1",
    "1.8.0": "rivian_1.8.0",
    "1.9.0": "rivian_1.9.0",
    "1.10.0": "rivian_1.10.0",
    "1.11.0": "rivian_1.11.0",
    "1.12.0": "rivian_1.12.0",
    "1.13.0": "rivian_1.13.0",
    "1.14.0": "rivian_1.14.0",
    "1.15.0": "rivian_1.15.0",
    "2.0.0_beta": "rivian_2.0.0_beta",
    "2.2.0": "rivian_2.2.0",
    "2.3.0": "rivian_2.3.0",
    "2.4.0": "rivian_2.4.0",
    "2.5.0_beta": "rivian_2.5.0 beta",
    "2.5.1": "com_rivian_android_consumer_v2.5.1",
    "2.6.0": "com_rivian_android_consumer_v2.6.0",
}

# The one dump that lives in the repo instead of ~/src.
REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_DUMPS: dict[str, Path] = {
    "2.6.1": REPO_ROOT / ".apk" / "2.6.1" / "jadx" / "sources",
    "2.7.0": REPO_ROOT / ".apk" / "2.7.0" / "jadx" / "sources",
    "2.8.0": REPO_ROOT / ".apk" / "2.8.0" / "jadx" / "sources",
    "2.10.0": REPO_ROOT / ".apk" / "2.10.0" / "jadx" / "sources",
    "2.10.1": REPO_ROOT / ".apk" / "2.10.1" / "jadx" / "sources",
    "2.19.1": REPO_ROOT / ".apk" / "2.19.1" / "jadx" / "sources",
    "2.20.0": REPO_ROOT / ".apk" / "2.20.0" / "jadx" / "sources",
    "2.21.0": REPO_ROOT / ".apk" / "2.21.0" / "jadx" / "sources",
    "3.0.0": REPO_ROOT / ".apk" / "3.0.0" / "jadx" / "sources",
    "3.1.0": REPO_ROOT / ".apk" / "3.1.0" / "jadx" / "sources",
    "3.1.1": REPO_ROOT / ".apk" / "3.1.1" / "jadx" / "sources",
    "3.3.0": REPO_ROOT / ".apk" / "3.3.0" / "jadx" / "sources",
    "3.4.0": REPO_ROOT / ".apk" / "3.4.0" / "jadx" / "sources",
    "3.5.0": REPO_ROOT / ".apk" / "3.5.0" / "jadx" / "sources",
    "3.5.1": REPO_ROOT / ".apk" / "3.5.1" / "jadx" / "sources",
    "3.6.0": REPO_ROOT / ".apk" / "3.6.0" / "jadx" / "sources",
    "3.6.1": REPO_ROOT / ".apk" / "3.6.1" / "jadx" / "sources",
    "3.7.0": REPO_ROOT / ".apk" / "3.7.0" / "jadx" / "sources",
    "3.8.0": REPO_ROOT / ".apk" / "3.8.0" / "jadx" / "sources",
    "3.9.0": REPO_ROOT / ".apk" / "3.9.0" / "jadx" / "sources",
    "3.10.0": REPO_ROOT / ".apk" / "3.10.0" / "jadx" / "sources",
    "3.11.0": REPO_ROOT / ".apk" / "3.11.0" / "jadx" / "sources",
    "3.12.0": REPO_ROOT / ".apk" / "3.12.0" / "jadx" / "sources",
    "3.12.1": REPO_ROOT / ".apk" / "3.12.1" / "jadx" / "sources",
    "3.13.0": REPO_ROOT / ".apk" / "3.13.0" / "jadx" / "sources",
    "3.13.1": REPO_ROOT / ".apk" / "3.13.1" / "jadx" / "sources",
    "3.14.0": REPO_ROOT / ".apk" / "3.14.0" / "jadx" / "sources",
    "3.15.0": REPO_ROOT / ".apk" / "3.15.0" / "jadx" / "sources",
    "3.16.0": REPO_ROOT / ".apk" / "3.16.0" / "jadx" / "sources",
}

# --- command extraction ------------------------------------------------------

VAS_COMMAND_FILES = ("VASCommand.java", "VASCommandKt.java")

# `public static final class OpenFrunk extends VASCommand {`
COMMAND_CLASS_RE = re.compile(r"\bclass\s+(\w+)\s+extends\s+VASCommand\b")

# The wrapper factories. `$default` is the Kotlin default-argument bridge; the
# first argument is always the companion, the second carries the name.
CLOUD_CALL_RE = re.compile(
    r"\bgenerateCloudDataWrapper(?:\$default)?\s*\(\s*[^,()]+,\s*"
    # `(?:get)?` matters: jadx renders the Kotlin property as
    # `VASCommandKt.getCABIN_HVAC_DEFROST_DEFOG()`. Without it the const group
    # cannot match at `get...`, so the engine backtracks, discards the
    # `VASCommandKt.` prefix and matches `VASC` -- silently renaming ten
    # climate commands after a fragment of the class name.
    r'(?:"(?P<literal>[^"]*)"|(?:VASCommandKt\.)?(?:get)?(?P<const>[A-Z][A-Z0-9_]{2,}))'
)
BLE_CALL_RE = re.compile(
    r"\bgenerateBLEDataWrapper(?:\$default)?\s*\(\s*[^,()]+,\s*"
    r"(?:VASCommandKt\.)?(?:get)?(?P<const>BLE_[A-Z0-9_]+)"
)
CLOUD_PRESENT_RE = re.compile(r"\bgenerateCloudDataWrapper\b")
BLE_PRESENT_RE = re.compile(r"\bgenerateBLEDataWrapper\b")

# 3.15.0 only, and a third form rather than a variant of the first: ten classes
# build their wrapper with `generateInvalidCloudDataWrapper("PET_COMFORT_ON")`
# -- the Parallax-routed and px-request-only commands, which carry a real name
# but are NOT sendable over the VAS cloud path. Folding these into `cloud` would
# overstate what the integration can send; dropping them would lose ten names,
# so they get their own column.
INVALID_CLOUD_CALL_RE = re.compile(
    r"\bgenerateInvalidCloudDataWrapper\s*\(\s*"
    r'(?:"(?P<literal>[^"]*)"|(?:VASCommandKt\.)?(?P<const>[A-Z][A-Z0-9_]{2,}))'
)
INVALID_CLOUD_PRESENT_RE = re.compile(r"\bgenerateInvalidCloudDataWrapper\b")

# `public static final String CLOUD_START_CHARGING = "START_CHARGING";`
STRING_CONST_RE = re.compile(r"\bstatic\s+final\s+String\s+(\w+)\s*=\s*\"([^\"]*)\"")

# jadx gives up on some constructors and emits a register dump instead of Java.
# The command name survives as a bare literal (`java.lang.String r3 = "..."`),
# so an all-caps literal inside the class block is the last-resort name.
SCREAMING_LITERAL_RE = re.compile(r'"([A-Z][A-Z0-9_]{2,})"')

# --- vehicleState document extraction ----------------------------------------

# The Apollo-generated operation text. Whole-word so a longer identifier ending
# in `vehicleState` cannot masquerade as the operation root.
VEHICLE_STATE_MARKER = re.compile(r"\bvehicleState\(id:")
JAVA_STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
GRAPHQL_TOKEN_RE = re.compile(r"\.{3}|[{}()]|\$?[A-Za-z_][A-Za-z0-9_]*|:|.")

# --- feature extraction ------------------------------------------------------

VEHICLE_FEATURE_FILE = "VehicleFeature.java"
# `TAILGATE_CMD("TAILGATE_CMD"),` -- member and server-facing featureName differ
# for 19 of the 64 members in 3.15.0, so both columns are kept.
ENUM_MEMBER_RE = re.compile(
    r"^\s*([A-Z][A-Z0-9_]*)\(\"([^\"]*)\"\)\s*[,;]", re.MULTILINE
)


# --- sensor-surface extraction -----------------------------------------------
#
# Four surfaces, four DIFFERENT metrics, because the four integration-side sets
# they are compared against are four different shapes. Sharing one "count every
# name" metric across them is the mistake this block exists to avoid: it makes
# every number look comparable and none of them actually is.

# (1) vehicleState. The metric here is NOT `graphql_field_names()`. That one
# unions names at ANY depth, which for wcm.java counts 138; the number that is
# comparable to `VEHICLE_STATE_API_FIELDS` -- a set of TOP-LEVEL subscribed
# names -- is the depth-1 count, which is 128. Both measurements are correct and
# only one answers the question, so this replicates the depth-1 walk from
# `scripts/gates/helpers/apk_vehicle_state_fields.py` rather than reusing the
# tokenizer. Its numbers reconcile with that helper exactly: wcm 128, cdm 122,
# apj 8, h9l 1, lel 1, union 137 -- the same 137 that `scripts/gates/f4.sh`
# asserts.
#
# The helper hard-codes `$vehicleID` because it only ever reads the nine
# pre-flight classes. The corpus spans 26 builds, so the variable name is a
# capture here, not a literal.
VEHICLE_STATE_ROOT_RE = re.compile(r"vehicleState\(id: \$\w+\) \{")
VEHICLE_STATE_FRAGMENT_RE = re.compile(r"fragment (\w+) on VehicleState \{")

# (2) Parallax RVMs. The table is a Kotlin enum whose CLASS name is obfuscated
# and build-specific (`l6e`, `iol` in 3.15.0), so the anchor is the property,
# which R8 leaves alone: `private final String rvmName;`. jadx renders the enum
# two ways depending on whether it could restore the `enum` modifier, so both
# forms are matched.
RVM_TABLE_MARKER_RE = re.compile(r"\bprivate final String rvmName;")
RVM_ENUM_CTOR_RE = re.compile(
    r'new \w+\(\s*"[A-Z][A-Z0-9_]*"\s*,\s*\d+\s*,\s*"([a-z][\w.]*\.[\w.]+)"'
)
RVM_SIMPLE_ENUM_RE = re.compile(
    r'^\s*[A-Z][A-Z0-9_]*\("([a-z][\w.]*\.[\w.]+)"\)\s*[,;]', re.MULTILINE
)
# Parallax did not exist before 3.x. `ParallaxAttributes.java` is the marker for
# "this build has the Parallax command surface at all" -- it is absent from every
# 1.x and 2.x tree, so the historical corpus contributes NOTHING to this surface
# and a zero there is a fact about the app, not a parse failure.
PARALLAX_ATTRIBUTES_FILE = "ParallaxAttributes.java"

# (3) VehicleFeature is already extracted by `extract_features`; the surface just
# compares it against the transcription.

# (4) Charging / wallbox. Unlike vehicleState there is no single operation root,
# so the surface is defined by the roots the INTEGRATION itself sends -- anything
# else would be measuring the app's charging-network features, which this
# integration does not implement and cannot be in deficit against.
CHARGING_ROOT_RE = re.compile(
    r"\b(?:getRegisteredWallboxes|getWallboxStatus|chargingSchedules"
    r"|setChargingSchedules|getLiveSessionData)\b|\bchargingSession\("
)
GRAPHQL_OPERATION_RE = re.compile(r"\s*(query|subscription|mutation)\b")

# The vendored schema splits this surface across TWO files: the wallbox record
# lives in `charging.graphql`, not `gateway.graphql`. Naming only the gateway
# would report all 17 `WallboxRecord` fields as undeclared.
SCHEMA_FILES = ("gateway.graphql", "charging.graphql")
# Arg-bearing fields are declared `chargingSession(vehicleId: String!): T`, so
# the argument list has to be optional here. Without it the Query/Mutation roots
# drop out and the delta reports five phantom undeclared names.
SCHEMA_FIELD_RE = re.compile(r"^  (\w+)(?:\([^)]*\))?:", re.MULTILINE)
CHARGING_SCHEMA_TYPES = (
    "GeoCoordinates",
    "OK",
    "ChargingChartData",
    "ChargingLiveData",
    "ChargingSchedule",
    "ChargingSession",
    "InputChargingSchedule",
    "WallboxRecord",
    "LiveSessionData",
    "ChargingSessionSummary",
    "ChargingSessionSummaryMeta",
)
# `Query`/`Mutation`/`Subscription`/`Vehicle` are deliberately NOT in that list:
# they declare 70-odd names about login, orders and images that have nothing to
# do with charging, and folding them in buries a two-name delta under 73 lines of
# noise. Only the roots that reach the charging types are taken, and each one is
# checked to exist so a schema rename cannot silently drop it.
CHARGING_SCHEMA_ROOTS = (
    "getRegisteredWallboxes",
    "getWallboxStatus",
    "getVehicle",
    "chargingSchedules",
    "setChargingSchedules",
    "chargingSession",
    "getLiveSessionData",
)
SCHEMA_TYPE_RE = r"^(?:type|input) %s [^{]*\{\n(.*?)\n\}"
SCHEMA_ROOT_RE = r"^  %s(?:\([^)]*\))?:"

# BLE-only commands are NOT part of any sensor surface and never belong in a
# delta table: a command the app can only send over Bluetooth is not a field the
# integration is failing to read. They are reported as an appendix so that a
# reader who sees them in the ledger can tell why they are excluded here.
# `WINCH_*` (1.0.3-1.4.1) and `PAUSE_*` (1.0.3-2.6.0) are the two families.


def version_key(version: str) -> tuple[int, int, int, int]:
    """Sort 1.9.0 before 1.10.0, and let both `_beta` spellings through."""
    base, _, suffix = version.partition("_")
    parts = [int(p) for p in base.split(".")]
    while len(parts) < 3:
        parts.append(0)
    # A beta precedes the release it is named for; neither of ours collides.
    return (parts[0], parts[1], parts[2], 0 if suffix else 1)


def unescape_java(literal: str) -> str:
    simple = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "'": "'"}
    out: list[str] = []
    i = 0
    while i < len(literal):
        char = literal[i]
        if char == "\\" and i + 1 < len(literal):
            nxt = literal[i + 1]
            if nxt in simple:
                out.append(simple[nxt])
                i += 2
                continue
            if nxt == "u" and i + 6 <= len(literal):
                try:
                    out.append(chr(int(literal[i + 2 : i + 6], 16)))
                    i += 6
                    continue
                except ValueError:
                    pass
        out.append(char)
        i += 1
    return "".join(out)


def balanced_block(text: str, open_brace: int) -> str:
    """Return the `{...}` block starting at `open_brace`, braces balanced."""
    depth = 0
    for index in range(open_brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace : index + 1]
    return text[open_brace:]


def graphql_field_names(document: str) -> list[str]:
    """Field names selected anywhere in a GraphQL document.

    Written as a tokenizer rather than a regex because the interesting names sit
    in selection sets while the uninteresting ones -- operation names, variable
    types, fragment type conditions -- sit outside them, and only nesting depth
    tells the two apart.
    """
    tokens = [t for t in GRAPHQL_TOKEN_RE.findall(document) if not t.isspace()]
    fields: list[str] = []
    depth = 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "(":
            # Argument or variable-definition list: skip it whole.
            paren = 0
            while index < len(tokens):
                if tokens[index] == "(":
                    paren += 1
                elif tokens[index] == ")":
                    paren -= 1
                    if paren == 0:
                        break
                index += 1
            index += 1
            continue
        if token == "{":
            depth += 1
            index += 1
            continue
        if token == "}":
            depth -= 1
            index += 1
            continue
        if token == "...":
            # Fragment spread or inline fragment: `...name` / `... on Type`.
            index += 2 if index + 1 < len(tokens) and tokens[index + 1] == "on" else 1
            index += 1
            continue
        if depth >= 1 and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
            if index + 1 < len(tokens) and tokens[index + 1] == ":":
                # `alias: field` -- the field is what follows the colon.
                index += 2
                continue
            if token != "__typename":
                fields.append(token)
        index += 1
    seen = set()
    unique: list[str] = []
    for name in fields:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


def extract_commands(sources: dict[str, str]) -> list[dict]:
    """Command records from the VASCommand sources of one dump.

    A record is one `X extends VASCommand` class. `cloud` means the class builds
    a CloudDataWrapper, so the command is cloud-sendable; a class with only
    `ble` is BLE-only and cannot be sent from the integration.
    """
    # Named constants can be declared in either file; resolve across both.
    constants: dict[str, str] = {}
    for text in sources.values():
        for name, value in STRING_CONST_RE.findall(text):
            constants[name] = value

    commands: list[dict] = []
    for text in sources.values():
        for match in COMMAND_CLASS_RE.finditer(text):
            brace = text.find("{", match.end())
            if brace == -1:
                continue
            block = balanced_block(text, brace)
            class_name = match.group(1)

            cloud_names: list[str] = []
            for call in CLOUD_CALL_RE.finditer(block):
                literal, const = call.group("literal"), call.group("const")
                name = literal if literal is not None else constants.get(const, const)
                if name and name not in cloud_names:
                    cloud_names.append(name)

            has_cloud = bool(CLOUD_PRESENT_RE.search(block))
            if has_cloud and not cloud_names:
                cloud_names = [
                    literal
                    for literal in dict.fromkeys(SCREAMING_LITERAL_RE.findall(block))
                    if "_" in literal and len(literal) >= 8
                ]

            ble_consts = list(
                dict.fromkeys(m.group("const") for m in BLE_CALL_RE.finditer(block))
            )
            has_ble = bool(BLE_PRESENT_RE.search(block))

            invalid_names: list[str] = []
            for call in INVALID_CLOUD_CALL_RE.finditer(block):
                literal, const = call.group("literal"), call.group("const")
                name = literal if literal is not None else constants.get(const, const)
                if name and name not in invalid_names:
                    invalid_names.append(name)
            has_invalid = bool(INVALID_CLOUD_PRESENT_RE.search(block))

            if cloud_names:
                name = cloud_names[0]
            elif invalid_names:
                name = invalid_names[0]
            elif ble_consts:
                name = ble_consts[0][len("BLE_") :]
            else:
                # No wrapper of any kind, so the class carries no command-name
                # string. `PauseFrunk`, `PauseLiftgate`, `PauseTonneauCover` each
                # have a literal `cloudData = null`; `ParallaxCommand` takes its
                # wrapper as a constructor parameter. Falling back to the class
                # name here invented four commands that the app never names.
                name = None

            commands.append(
                {
                    "name": name,
                    "class": class_name,
                    "cloud": has_cloud,
                    "ble": has_ble,
                    "cloud_invalid": has_invalid,
                    "cloud_names": cloud_names,
                    "cloud_invalid_names": invalid_names,
                    "ble_constants": ble_consts,
                }
            )
    # `name` is None for wrapper-less classes, which cannot be compared to str.
    commands.sort(key=lambda c: (c["name"] or "", c["class"]))
    return commands


def extract_documents(hits: list[tuple[str, str]]) -> list[dict]:
    """One record per file whose content carries a `vehicleState(id:` document."""
    documents: list[dict] = []
    for relative_path, text in hits:
        operations: list[dict] = []
        for match in JAVA_STRING_RE.finditer(text):
            body = unescape_java(match.group(1))
            if not VEHICLE_STATE_MARKER.search(body):
                continue
            head = re.match(r"\s*(query|subscription|mutation)\s+(\w+)", body)
            operations.append(
                {
                    "operation": head.group(2) if head else None,
                    "type": head.group(1) if head else None,
                    "fields": graphql_field_names(body),
                }
            )
        documents.append({"file": relative_path, "operations": operations})
    documents.sort(key=lambda d: d["file"])
    return documents


def extract_features(text: str) -> list[dict]:
    """(member, featureName) pairs from the VehicleFeature enum.

    Both columns matter: the member is what the app's own code branches on, and
    the featureName is what the server actually emits in `supportedFeatures`.
    """
    return [
        {"member": member, "feature_name": feature}
        for member, feature in ENUM_MEMBER_RE.findall(text)
    ]


def selection_body(document: str, after_open_brace: int) -> str:
    """The body of a `{...}` whose opening brace has already been consumed."""
    depth = 1
    index = after_open_brace
    while depth and index < len(document):
        if document[index] == "{":
            depth += 1
        elif document[index] == "}":
            depth -= 1
        index += 1
    return document[after_open_brace : index - 1]


def split_top_level(body: str) -> list[str]:
    """The depth-1 tokens of a selection-set body.

    Replicated from `scripts/gates/helpers/apk_vehicle_state_fields.py`. It is
    duplicated rather than imported because that helper reads the nine
    pre-flight classes by path and this reads 26 whole trees; what has to match
    between them is the METRIC, and it does -- see the reconciliation in the
    comment above `VEHICLE_STATE_ROOT_RE`.
    """
    out: list[str] = []
    depth = 0
    current: list[str] = []
    for char in body:
        if char == "{":
            depth += 1
            current.append(char)
        elif char == "}":
            depth -= 1
            current.append(char)
            if depth == 0:
                out.append("".join(current).strip())
                current = []
        elif depth == 0 and char.isspace():
            if current:
                out.append("".join(current).strip())
                current = []
        else:
            current.append(char)
    if current:
        out.append("".join(current).strip())
    return [token for token in out if token]


def selection_names(body: str, fragments: dict[str, str]) -> set[str]:
    """Depth-1 field names of a selection set, resolving fragment spreads."""
    names: set[str] = set()
    for token in split_top_level(body):
        if token.startswith("..."):
            spread = token[3:]
            if spread in fragments:
                names |= selection_names(fragments[spread], fragments)
            continue
        if token.startswith("{") or token == "__typename":
            # A nested selection set belongs to the field before it, and
            # `__typename` is Apollo bookkeeping rather than a subscribed name.
            continue
        names.add(token)
    return names


def vehicle_state_field_names(document: str) -> set[str]:
    """Top-level `VehicleState` names selected by one GraphQL document.

    The depth-1 metric, not the union-at-any-depth one -- see the comment on
    `VEHICLE_STATE_ROOT_RE` for why the difference matters.
    """
    fragments = {
        match.group(1): selection_body(document, match.end())
        for match in VEHICLE_STATE_FRAGMENT_RE.finditer(document)
    }
    names: set[str] = set()
    for match in VEHICLE_STATE_ROOT_RE.finditer(document):
        names |= selection_names(selection_body(document, match.end()), fragments)
    return names


def extract_rvm_names(text: str) -> set[str]:
    """RVM names from one obfuscated Kotlin enum table, or nothing."""
    if not RVM_TABLE_MARKER_RE.search(text):
        return set()
    return set(RVM_ENUM_CTOR_RE.findall(text)) | set(RVM_SIMPLE_ENUM_RE.findall(text))


def charging_field_names(document: str) -> set[str]:
    """Field names of one charging/wallbox operation, at any depth.

    Any depth is right HERE and wrong for `vehicleState`: the charging types are
    two levels deep (`chargingSession { chartData { soc } }`) and the schema
    declares every one of those names, so a depth-1 metric would compare a
    handful of container names against 123 declared fields.
    """
    if not GRAPHQL_OPERATION_RE.match(document) or not CHARGING_ROOT_RE.search(
        document
    ):
        return set()
    return set(graphql_field_names(document))


# --- the integration's own sets, read from source ----------------------------
#
# Parsed, never imported. Importing `const.py` drags in `homeassistant`, and the
# whole point of this script is that it runs against a corpus that lives outside
# any virtualenv.


def _eval_set_expr(node: ast.expr, env: dict[str, set[str]]) -> set[str] | None:
    """Evaluate the tiny expression language `const.py`'s field sets are built in.

    That is: set literals, `frozenset({...})`, names bound earlier in the module,
    and `|`/`-` between them. Anything else returns None rather than guessing.
    """
    if isinstance(node, ast.Set):
        values = {e.value for e in node.elts if isinstance(e, ast.Constant)}
        return values if len(values) == len(node.elts) else None
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else None
        if name in {"frozenset", "set"} and len(node.args) == 1:
            return _eval_set_expr(node.args[0], env)
        return None
    if isinstance(node, ast.Name):
        return env.get(node.id)
    if isinstance(node, ast.BinOp):
        left = _eval_set_expr(node.left, env)
        right = _eval_set_expr(node.right, env)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.BitOr):
            return left | right
        if isinstance(node.op, ast.Sub):
            return left - right
    return None


def _module_sets(path: Path) -> dict[str, set[str]]:
    """Every module-level name in `path` that resolves to a set of strings."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    env: dict[str, set[str]] = {}
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target, value = statement.targets[0], statement.value
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            target, value = statement.target, statement.value
        else:
            continue
        if not isinstance(target, ast.Name):
            continue
        resolved = _eval_set_expr(value, env)
        if resolved is not None:
            env[target.id] = resolved
    return env


def integration_vehicle_state_fields(repo_root: Path) -> set[str]:
    env = _module_sets(repo_root / "custom_components" / "rivian" / "const.py")
    return env["VEHICLE_STATE_API_FIELDS"]


def integration_rvm_names(repo_root: Path) -> set[str]:
    """The keys of `RVM_DECODERS` -- the RVMs this fork can actually decode."""
    path = repo_root / "custom_components" / "rivian" / "rivian_client" / "parallax.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for statement in tree.body:
        target = None
        if isinstance(statement, ast.AnnAssign):
            target = statement.target
        elif isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
        if not isinstance(target, ast.Name) or target.id != "RVM_DECODERS":
            continue
        value = statement.value
        if isinstance(value, ast.Dict):
            return {
                key.value
                for key in value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
    raise SystemExit(f"RVM_DECODERS not found in {path}")


def integration_feature_pairs(repo_root: Path) -> set[tuple[str, str]]:
    """`(member, featureName)` from the transcription, not from `const.py`.

    The capability flags are not a `const.py` symbol: entity descriptions name
    the seven the integration gates on, one string at a time. `VEHICLE_FEATURES`
    in `tests/apk/transcription.py` is the recorded whole enum, and it is what a
    64-member app table is comparable to.
    """
    path = repo_root / "tests" / "apk" / "transcription.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for statement in tree.body:
        target = None
        if isinstance(statement, ast.AnnAssign):
            target = statement.target
        elif isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
        if not isinstance(target, ast.Name) or target.id != "VEHICLE_FEATURES":
            continue
        value = statement.value
        if isinstance(value, (ast.Tuple, ast.List)):
            pairs: set[tuple[str, str]] = set()
            for element in value.elts:
                if (
                    isinstance(element, (ast.Tuple, ast.List))
                    and len(element.elts) == 2
                ):
                    first, second = element.elts
                    if isinstance(first, ast.Constant) and isinstance(
                        second, ast.Constant
                    ):
                        pairs.add((first.value, second.value))
            return pairs
    raise SystemExit(f"VEHICLE_FEATURES not found in {path}")


def integration_charging_fields(repo_root: Path) -> set[str]:
    """Charging/wallbox field names declared by the vendored schemas."""
    schemas = repo_root / "custom_components" / "rivian" / "rivian_client" / "schemas"
    fields: set[str] = set()
    seen: set[str] = set()
    texts = [(schemas / name).read_text(encoding="utf-8") for name in SCHEMA_FILES]
    for text in texts:
        for type_name in CHARGING_SCHEMA_TYPES:
            match = re.search(
                SCHEMA_TYPE_RE % type_name, text, re.MULTILINE | re.DOTALL
            )
            if match is None:
                continue
            seen.add(type_name)
            fields |= set(SCHEMA_FIELD_RE.findall(match.group(1)))
    for root in CHARGING_SCHEMA_ROOTS:
        if any(re.search(SCHEMA_ROOT_RE % root, text, re.MULTILINE) for text in texts):
            seen.add(root)
            fields.add(root)
    missing = [
        name
        for name in CHARGING_SCHEMA_TYPES + CHARGING_SCHEMA_ROOTS
        if name not in seen
    ]
    if missing:
        # A renamed type or root would silently shrink the schema side and
        # manufacture a delta against the app, which is the exact failure this
        # whole mode is meant to make impossible.
        raise SystemExit(
            "charging schema names not found in either vendored schema: "
            + ", ".join(missing)
        )
    return fields


def relative_prefix(paths: Iterable[Path], root: Path) -> str:
    """The shared directory prefix of the scanned sources, discovered not assumed.

    This is what distinguishes `sources/` from `java_src/` from a root that is
    already the source root -- read off the files that were actually found.
    """
    prefix: list[str] | None = None
    for path in paths:
        parts = list(path.relative_to(root).parts[:-1])
        if prefix is None:
            prefix = parts
            continue
        keep = 0
        while keep < min(len(prefix), len(parts)) and prefix[keep] == parts[keep]:
            keep += 1
        prefix = prefix[:keep]
        if not prefix:
            break
    return "/".join(prefix) if prefix else "."


def sweep_version(version: str, root: Path, sensors: bool = False) -> dict:
    """Walk one dump once, collecting everything the sweep needs from it.

    `sensors` is off by default because it costs two more regex scans per file
    across 26 trees, and the command ledger -- the older and more used half of
    this script -- does not need any of it.
    """
    command_sources: dict[str, str] = {}
    feature_text: str | None = None
    document_hits: list[tuple[str, str]] = []
    java_files: list[Path] = []
    rvm_names: set[str] = set()
    parallax_attributes = False
    charging_fields: set[str] = set()
    charging_documents = 0

    for path in sorted(root.rglob("*.java")):
        java_files.append(path)
        name = path.name
        wanted = name in VAS_COMMAND_FILES or name == VEHICLE_FEATURE_FILE
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as err:  # unreadable file: report, do not silently drop
            print(f"warning: {version}: cannot read {path}: {err}", file=sys.stderr)
            continue
        if name in VAS_COMMAND_FILES:
            command_sources[name] = text
        elif name == VEHICLE_FEATURE_FILE:
            feature_text = text
        if not wanted and VEHICLE_STATE_MARKER.search(text):
            document_hits.append((str(path.relative_to(root)), text))
        if not sensors:
            continue
        if name == PARALLAX_ATTRIBUTES_FILE:
            parallax_attributes = True
        rvm_names |= extract_rvm_names(text)
        if CHARGING_ROOT_RE.search(text):
            for match in JAVA_STRING_RE.finditer(text):
                found = charging_field_names(unescape_java(match.group(1)))
                if found:
                    charging_documents += 1
                    charging_fields |= found

    commands = extract_commands(command_sources)
    documents = extract_documents(document_hits)
    features = extract_features(feature_text) if feature_text else []

    errors: list[str] = []
    if not java_files:
        errors.append("no .java files found under the dump root")
    if not command_sources:
        errors.append("no VASCommand sources found")
    if not commands:
        errors.append("zero commands extracted")

    result = {
        "version": version,
        "root": str(root),
        "layout": relative_prefix(java_files, root),
        "files_scanned": len(java_files),
        "commands": commands,
        "documents": documents,
        "features": features,
        "errors": errors,
    }
    if sensors:
        # The vehicleState half re-reads the documents already collected above,
        # under the depth-1 metric rather than the tokenizer's.
        vehicle_state_fields: set[str] = set()
        for _, text in document_hits:
            for match in JAVA_STRING_RE.finditer(text):
                body = unescape_java(match.group(1))
                if VEHICLE_STATE_MARKER.search(body):
                    vehicle_state_fields |= vehicle_state_field_names(body)
        result["sensors"] = {
            "vehicle_state_fields": sorted(vehicle_state_fields),
            "rvm_names": sorted(rvm_names),
            "parallax_attributes": parallax_attributes,
            "feature_pairs": [(f["member"], f["feature_name"]) for f in features],
            "charging_fields": sorted(charging_fields),
            "charging_documents": charging_documents,
        }
    return result


def report(result: dict) -> None:
    status = "ERROR" if result["errors"] else "ok"
    cloud = sum(1 for c in result["commands"] if c["cloud"])
    ble = sum(1 for c in result["commands"] if c["ble"])
    invalid = sum(1 for c in result["commands"] if c["cloud_invalid"])
    print(f"=== {result['version']}  [{status}]")
    print(f"  root     {result['root']}")
    print(f"  layout   {result['layout']}  ({result['files_scanned']} .java files)")
    print(
        f"  commands {len(result['commands'])}"
        f"  (cloud {cloud}, ble {ble}, invalid-cloud {invalid})"
    )
    for command in result["commands"]:
        wrappers = ",".join(
            [
                w
                for w, on in (
                    ("cloud", command["cloud"]),
                    ("ble", command["ble"]),
                    ("invalid-cloud", command["cloud_invalid"]),
                )
                if on
            ]
        )
        # `name` is None for a wrapper-less class -- the same None the ledger
        # sort key already guards. A class with no wrapper carries no command
        # name, and 3.16.0 has four of them.
        label = command["name"] or "(no command name)"
        print(f"    {label:48s} {wrappers or '-':20s} {command['class']}")
    print(f"  documents {len(result['documents'])}")
    for document in result["documents"]:
        for operation in document["operations"]:
            label = operation["operation"] or "(unnamed)"
            print(
                f"    {document['file']}  {operation['type'] or '?'} {label}"
                f"  ({len(operation['fields'])} fields)"
            )
            print(f"      {' '.join(operation['fields'])}")
    print(f"  features {len(result['features'])}")
    for feature in result["features"]:
        marker = " *" if feature["member"] != feature["feature_name"] else "  "
        print(f"   {marker} {feature['member']:44s} {feature['feature_name']}")
    for error in result["errors"]:
        print(f"  ERROR: {error}")
    print()


# Layout is a PROXY for the producing pipeline, not the pipeline itself. Which
# decompiler wrote each 1.x/2.x dump was never recorded, and that gap is why a
# count is only comparable within a cohort: a drop between versions cannot be
# attributed to a real app change rather than a lossier extraction unless the
# producing tool is known. Only the 3.15.0 cohort has documented provenance
# (jadx, per docs/development/apk/REGENERATION.md).
COHORTS: dict[str, str] = {
    "sources": "A/sources (1.x + 2.0.0_beta; decompiler unrecorded)",
    "java_src": "B/java_src (2.2.0+; decompiler unrecorded)",
    # 29 trees, 2.6.1 to 3.16.0, all decompiled here with jadx 1.5.6
    # from APKMirror bundles. Unlike cohorts A and B, whose decompiler was
    # never recorded, this one has documented provenance -- so counts inside
    # it are comparable to each other, and 3.15.0 remains its ground truth.
    ".": "C/jadx (29 trees 2.6.1-3.16.0; jadx 1.5.6, documented)",
}


def roll_up_ledger(results: list[dict]) -> list[dict]:
    """One row per command name, across every version it ever appeared in.

    The ledger is the deliverable; the probe queue is a prioritised view over it.
    So a row records what the app said and when, and never whether the command is
    worth sending -- a decompile enumerates, only the vehicle promotes.
    """
    ordered = sorted(results, key=lambda r: version_key(r["version"]))
    rows: dict[str, dict] = {}

    for result in ordered:
        cohort = COHORTS.get(result["layout"], result["layout"])
        for command in result["commands"]:
            name = command.get("name")
            if not name:
                continue
            row = rows.setdefault(
                name,
                {
                    "name": name,
                    "first_seen": result["version"],
                    "last_seen": result["version"],
                    "versions": [],
                    "cohorts": [],
                    "cloud": False,
                    "ble": False,
                    "cloud_invalid": False,
                },
            )
            row["last_seen"] = result["version"]
            # Deduped, like `cohorts` two lines below. Two classes in one dump can
            # resolve to the same command name -- OPEN_LIFTGATE_UNLATCH_TAILGATE
            # does in 25 of 26 versions -- and an unconditional append counted it
            # twice, shipping n=51 for a 26-version corpus.
            if result["version"] not in row["versions"]:
                row["versions"].append(result["version"])
            if cohort not in row["cohorts"]:
                row["cohorts"].append(cohort)
            for transport in ("cloud", "ble", "cloud_invalid"):
                if command.get(transport):
                    row[transport] = True

    for row in rows.values():
        if row["cloud"]:
            row["transport"] = "cloud+ble" if row["ble"] else "cloud"
        elif row["ble"]:
            row["transport"] = "ble-only"
        elif row["cloud_invalid"]:
            row["transport"] = "invalid-wrapper"
        else:
            row["transport"] = "none"

    return [rows[name] for name in sorted(rows)]


# --- sensor-surface roll-up --------------------------------------------------

# The FLOOR is the union size measured across the whole corpus on 2026-08-31. It
# exists for the same reason the command ledger's does: an extractor that quietly
# stops matching -- a renamed obfuscated class, a jadx output change, a dump that
# moved -- reports a SMALLER union and every delta gets smaller with it, which
# reads like progress. A shrink is therefore an error, not a pass. A GROWTH is
# fine and is reported, because a new app build legitimately adds names.
#
# Each floor is per-surface because the four surfaces fail independently: the
# Parallax table can vanish while the vehicleState documents parse perfectly.
SURFACE_FLOORS: dict[str, int] = {
    "vehicle_state": 157,
    "parallax_rvm": 58,
    "vehicle_feature": 89,
    "charging": 52,
}

SURFACE_TITLES: dict[str, str] = {
    "vehicle_state": "vehicleState GraphQL fields  vs  VEHICLE_STATE_API_FIELDS",
    "parallax_rvm": "Parallax RVMs  vs  RVM_DECODERS",
    "vehicle_feature": "VehicleFeature (member, featureName)  vs  VEHICLE_FEATURES",
    "charging": "charging / wallbox fields  vs  the vendored schemas",
}

SURFACE_METRICS: dict[str, str] = {
    "vehicle_state": (
        "depth-1 names on VehicleState, fragment spreads resolved -- the metric "
        "of scripts/gates/helpers/apk_vehicle_state_fields.py, NOT "
        "graphql_field_names()"
    ),
    "parallax_rvm": (
        "rvmName literals of the obfuscated enum tables; 3.x ONLY -- "
        "ParallaxAttributes.java is absent from every 1.x and 2.x tree, so the "
        "historical corpus contributes nothing to this surface"
    ),
    "vehicle_feature": (
        "both columns: the member the app branches on and the featureName the "
        "server emits; they differ for 19 of the 64 members in 3.15.0"
    ),
    "charging": (
        "field names at any depth in the operations the integration itself "
        "sends; the schema side spans gateway.graphql AND charging.graphql, "
        "because WallboxRecord lives in the latter"
    ),
}


def sensor_surfaces(
    results: list[dict], repo_root: Path, enforce_floor: bool = True
) -> dict:
    """The four deltas, each against the integration set it is comparable to."""
    ordered = sorted(results, key=lambda r: version_key(r["version"]))

    app: dict[str, set] = {key: set() for key in SURFACE_FLOORS}
    seen: dict[str, dict] = {key: {} for key in SURFACE_FLOORS}
    per_version: dict[str, list[tuple[str, int]]] = {key: [] for key in SURFACE_FLOORS}
    parallax_versions: list[str] = []

    for result in ordered:
        sensors = result.get("sensors")
        if sensors is None:
            continue
        version = result["version"]
        contributions = {
            "vehicle_state": set(sensors["vehicle_state_fields"]),
            "parallax_rvm": set(sensors["rvm_names"]),
            "vehicle_feature": {tuple(pair) for pair in sensors["feature_pairs"]},
            "charging": set(sensors["charging_fields"]),
        }
        for key, names in contributions.items():
            app[key] |= names
            per_version[key].append((version, len(names)))
            for name in names:
                # first/last seen, exactly as the command ledger records them.
                # Without this a name last present in 1.4.1 reads as a live gap,
                # and 25 of the VehicleFeature members are precisely that.
                window = seen[key].setdefault(name, [version, version])
                window[1] = version
        if sensors["parallax_attributes"]:
            parallax_versions.append(version)

    ours = {
        "vehicle_state": integration_vehicle_state_fields(repo_root),
        "parallax_rvm": integration_rvm_names(repo_root),
        "vehicle_feature": integration_feature_pairs(repo_root),
        "charging": integration_charging_fields(repo_root),
    }

    surfaces = {}
    for key, floor in SURFACE_FLOORS.items():
        surfaces[key] = {
            "title": SURFACE_TITLES[key],
            "metric": SURFACE_METRICS[key],
            "app": sorted(app[key]),
            "ours": sorted(ours[key]),
            "app_only": [
                {
                    "name": name,
                    "first_seen": seen[key][name][0],
                    "last_seen": seen[key][name][1],
                }
                for name in sorted(app[key] - ours[key])
            ],
            "ours_only": sorted(ours[key] - app[key]),
            "per_version": per_version[key],
            "floor": floor,
            "below_floor": enforce_floor and len(app[key]) < floor,
        }

    ledger = roll_up_ledger(results)
    ble_only = [row for row in ledger if row["transport"] == "ble-only"]

    return {
        "surfaces": surfaces,
        "parallax_versions": parallax_versions,
        "ble_only_commands": ble_only,
        "floor_enforced": enforce_floor,
        "errors": [
            f"{key}: union {len(surfaces[key]['app'])} is below the recorded "
            f"floor of {surfaces[key]['floor']}"
            for key in SURFACE_FLOORS
            if surfaces[key]["below_floor"]
        ],
    }


def format_entry(entry) -> str:
    """A surface entry as one string. VehicleFeature entries are two columns."""
    if isinstance(entry, (tuple, list)) and len(entry) == 2:
        return f"{entry[0]} -> {entry[1]}"
    return str(entry)


def report_sensors(report: dict) -> None:
    for key, surface in report["surfaces"].items():
        print(f"=== ({key}) {surface['title']}")
        print(f"  metric   {surface['metric']}")
        floor = surface["floor"] if report["floor_enforced"] else "n/a (partial)"
        print(
            f"  app union {len(surface['app']):4d}   floor {floor}"
            f"   ours {len(surface['ours'])}"
        )
        counts = "  ".join(f"{v}:{n}" for v, n in surface["per_version"] if n)
        print(f"  per version  {counts or '(none)'}")
        print(f"  in the app, not in ours  {len(surface['app_only'])}")
        for row in surface["app_only"]:
            window = (
                row["first_seen"]
                if row["first_seen"] == row["last_seen"]
                else f"{row['first_seen']}-{row['last_seen']}"
            )
            print(f"    + {format_entry(row['name']):58s} {window}")
        print(f"  in ours, not in the app  {len(surface['ours_only'])}")
        for entry in surface["ours_only"]:
            print(f"    - {format_entry(entry)}")
        print()

    print("=== appendix: BLE-only commands (NOT a sensor surface)")
    print(
        "  A command the app can only send over Bluetooth is not a field the\n"
        "  integration is failing to read, so these are excluded from every\n"
        "  delta above rather than counted as a gap."
    )
    for row in report["ble_only_commands"]:
        print(
            f"    {row['name']:32s} {row['first_seen']:10s} -> "
            f"{row['last_seen']:10s}  ({len(row['versions'])} version(s))"
        )
    if not report["ble_only_commands"]:
        print("    (none in this sweep)")
    print()

    versions = ", ".join(report["parallax_versions"]) or "(none)"
    print(f"Parallax-bearing builds in this sweep: {versions}")
    for error in report["errors"]:
        print(f"ERROR: {error}")


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--src-root",
        type=Path,
        default=Path.home() / "src",
        help="directory holding the extracted app dumps (default: ~/src)",
    )
    parser.add_argument(
        "--only",
        action="append",
        metavar="VERSION",
        help="sweep just this version; repeatable",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--ledger",
        action="store_true",
        help="roll the sweep up into one row per command across all versions",
    )
    parser.add_argument(
        "--sensors",
        action="store_true",
        help="four sensor-surface deltas against the integration's own sets",
    )
    args = parser.parse_args()

    roots: dict[str, Path] = {v: args.src_root / d for v, d in SRC_DUMPS.items()}
    roots.update(REPO_DUMPS)

    if args.only:
        unknown = [v for v in args.only if v not in roots]
        if unknown:
            known = ", ".join(sorted(roots, key=version_key))
            raise SystemExit(
                f"unknown version(s): {', '.join(unknown)}\nknown: {known}"
            )
        roots = {v: roots[v] for v in args.only}

    versions = sorted(roots, key=version_key)

    missing = [(v, roots[v]) for v in versions if not roots[v].is_dir()]
    if missing:
        for version, root in missing:
            print(
                f"ERROR: {version}: dump directory not found: {root}", file=sys.stderr
            )
        print(
            "The corpus is an explicit allowlist, so a missing directory means the "
            "dump was moved or never extracted -- it is not skipped.",
            file=sys.stderr,
        )
        return 2

    results = [
        sweep_version(version, roots[version], sensors=args.sensors)
        for version in versions
    ]

    if args.sensors:
        # A partial sweep cannot meet a whole-corpus floor, so `--only`
        # reports the deltas and skips the floor rather than failing.
        surfaces = sensor_surfaces(results, REPO_ROOT, enforce_floor=not args.only)
        if args.json:
            print(json.dumps(surfaces, indent=2))
        else:
            report_sensors(surfaces)
        failed = any(r["errors"] for r in results) or surfaces["errors"]
        return 1 if failed else 0

    if args.ledger:
        ledger = roll_up_ledger(results)
        if args.json:
            print(json.dumps(ledger, indent=2))
        else:
            print(f"{len(ledger)} command(s) across {len(results)} version(s)\n")
            print(f"{'command':46s} {'first':10s} {'last':10s} {'n':>3s}  transport")
            for row in ledger:
                print(
                    f"{row['name']:46s} {row['first_seen']:10s} "
                    f"{row['last_seen']:10s} {len(row['versions']):>3d}  "
                    f"{row['transport']}"
                )
        return 1 if any(r["errors"] for r in results) else 0

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for result in results:
            report(result)
        failed = [r["version"] for r in results if r["errors"]]
        print(f"{len(results)} version(s) swept, {len(failed)} with errors")
        if failed:
            print(f"errors in: {', '.join(failed)}")

    return 1 if any(r["errors"] for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
