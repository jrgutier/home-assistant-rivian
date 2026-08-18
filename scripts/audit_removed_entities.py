#!/usr/bin/env python3
"""Find every reference to entities that 1.6.0 removes, before you upgrade.

1.6.0 removes 11 Parallax entities whose backing RVMs return INTERNAL_SERVER_ERROR
for both reads and writes -- they never worked, they just reported their defaults.
Removing them is correct, but anything still pointing at them breaks quietly:
a Lovelace card renders "Entity not available", and an automation fails at runtime
with no warning until it is triggered.

Read-only. Opens nothing but the config directory and prints what it finds.

Run it ON the Home Assistant machine, against the live config:

    python3 audit_removed_entities.py /config
    python3 audit_removed_entities.py ~/homeassistant

It covers storage-mode dashboards (.storage/lovelace*), YAML dashboards, and
automations/scripts/scenes/templates, because an automation referencing a dead
entity is a worse failure than a card: it is invisible until it fires.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

# The entity-description keys removed in 1.6.0. Entity ids are
# <domain>.<vehicle_name>_<key>, and the vehicle name is user-set, so match on the
# key with a domain prefix rather than guessing the full id.
REMOVED = {
    "switch": [
        "cabin_ventilation",
        "gear_guard_video_consent",
        "halloween_enabled",
        "passive_entry",
    ],
    "number": [
        "cabin_ventilation_duration",
        "cabin_ventilation_sunroof",
        "cabin_ventilation_windows",
        "halloween_brightness",
        "passive_entry_distance",
    ],
    "select": ["cabin_ventilation_mode", "halloween_mode"],
}
REMOVED_SERVICES = ["rivian.set_geofences"]


def build_patterns() -> list[tuple[str, re.Pattern[str]]]:
    out = []
    for domain, keys in REMOVED.items():
        for key in keys:
            # cabin_ventilation must not match cabin_ventilation_duration, so require
            # a non-word character (or end) after the key.
            out.append(
                (
                    f"{domain}.*_{key}",
                    re.compile(rf"\b{domain}\.[a-z0-9_]*{key}(?![a-z0-9_])"),
                )
            )
    for svc in REMOVED_SERVICES:
        out.append((svc, re.compile(re.escape(svc))))
    return out


def scan(root: Path) -> int:
    patterns = build_patterns()
    targets: list[Path] = []

    storage = root / ".storage"
    if storage.is_dir():
        targets += [p for p in storage.iterdir() if p.name.startswith("lovelace")]
    for name in (
        "automations.yaml",
        "scripts.yaml",
        "scenes.yaml",
        "configuration.yaml",
        "ui-lovelace.yaml",
        "templates.yaml",
    ):
        if (root / name).is_file():
            targets.append(root / name)
    for pattern in ("*.yaml", "*.yml"):
        targets += [
            p
            for p in root.rglob(pattern)
            if ".storage" not in p.parts
            and "custom_components" not in p.parts
            and "deps" not in p.parts
            and "blueprints" not in p.parts
        ]

    seen: set[Path] = set()
    findings: dict[str, list[str]] = {}
    for path in targets:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for label, rx in patterns:
            for match in set(rx.findall(text)):
                findings.setdefault(match, []).append(str(path.relative_to(root)))

    print(f"scanned {len(seen)} files under {root}\n")
    if not findings:
        print("No references to removed entities. Your dashboards and automations")
        print("will not be affected by the 1.6.0 entity removals.")
        return 0

    print(f"{len(findings)} removed entity/service reference(s) still in use:\n")
    for entity in sorted(findings):
        where = sorted(set(findings[entity]))
        print(f"  {entity}")
        for w in where:
            print(f"      {w}")
    print("\nEach of these will stop working after upgrading to 1.6.0.")
    print("Cards show 'Entity not available'; automations fail when triggered.")
    print("\nThese entities never functioned -- their Parallax RVMs return")
    print("INTERNAL_SERVER_ERROR in both directions -- so they were reporting")
    print("defaults, not vehicle state. Remove the cards and automation lines.")
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <config-dir>   e.g. /config")
    config = Path(sys.argv[1]).expanduser()
    if not config.is_dir():
        sys.exit(f"error: {config} is not a directory")
    raise SystemExit(scan(config))
