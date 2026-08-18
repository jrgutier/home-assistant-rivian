#!/usr/bin/env bash
# Import the built artifact under ONLY the requirements manifest.json declares.
#
# This is the check that catches a missing manifest entry, and nothing weaker
# does. Running the suite proves nothing here: the test venv has Home Assistant's
# full test extra installed, so a module importing something HA core does not
# ship still resolves and only fails for users.
#
# It has already earned its place. button.py imported homeassistant.components
# .bluetooth at module scope; that component's requirements belong to the
# bluetooth integration and it reaches homeassistant.components.usb, whose
# aiousbwatcher and serialx are absent from HA core's own metadata. On any system
# where the bluetooth integration was never set up, the entire button platform --
# wake button included -- would have failed to load. Every test passed.
#
# Usage: scripts/load_test.sh [venv-dir]
#   The venv is reused if it already exists, so repeated local runs are cheap.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
REPO="$PWD"

VENV="${1:-${TMPDIR:-/tmp}/rivian-load-test-venv}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Exactly what the manifest declares -- read from the manifest, never hardcoded,
# so adding a requirement cannot silently skip this check.
# bash 3.2 (what macOS ships) has no mapfile, and CI must run the same script.
REQS=()
while IFS= read -r line; do
  [ -n "$line" ] && REQS+=("$line")
done < <(python3 -c "
import json
print('\n'.join(json.load(open('custom_components/rivian/manifest.json'))['requirements']))
")
HA_PIN=$(grep -oE '^homeassistant==[0-9.]+' requirements.txt)

echo "load test"
echo "  home assistant: $HA_PIN"
echo "  manifest declares: ${REQS[*]:-<none>}"

if [ ! -x "$VENV/bin/python" ]; then
  echo "  creating $VENV"
  uv venv --python 3.14 "$VENV" -q
  VIRTUAL_ENV="$VENV" uv pip install -q "$HA_PIN" "${REQS[@]}"
else
  echo "  reusing $VENV"
fi

# Build the artifact the same way the release workflows do, then import what a
# user would actually have on disk -- not the working tree.
( cd custom_components/rivian
  zip -q -r "$WORK/rivian.zip" ./ \
    -i '*.py' '*.json' '*.graphql' '*.proto' '*.yaml' 'py.typed' )
mkdir -p "$WORK/custom_components/rivian"
unzip -q "$WORK/rivian.zip" -d "$WORK/custom_components/rivian"

cd "$WORK"
"$VENV/bin/python" - <<'PY'
import importlib, pathlib, sys

root = pathlib.Path("custom_components/rivian")
mods = sorted(root.rglob("*.py"))
if not mods:
    sys.exit("no modules unpacked -- the zip allow-list excluded everything")

failed = []
for f in mods:
    name = str(f.with_suffix("")).replace("/", ".").removesuffix(".__init__")
    try:
        importlib.import_module(name)
    except Exception as exc:
        failed.append(f"{name}: {type(exc).__name__}: {exc}")

print(f"  {len(mods)} modules imported, {len(failed)} failed")
for line in failed:
    print(f"    {line}")
sys.exit(1 if failed else 0)
PY

echo "  artifact loads under the declared requirements alone"
