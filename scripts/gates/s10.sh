#!/usr/bin/env bash
# S10 — protobuf removed from the vendored client.
#
# Every assertion here is about the CONTENTS of rivian_client/. If that directory
# does not exist, "the file is deleted" and "no _pb2 references" are both trivially
# true — the vacuous-pass failure this whole gate discipline exists to prevent.
# So the precondition is asserted first and the gate refuses to continue without it.

source "$(dirname "$0")/_lib.sh"

echo "S10 — protobuf removed"

VC="$HA/custom_components/rivian/rivian_client"

if [ ! -d "$VC" ]; then
  bad "PRECONDITION: vendored client missing at $VC — S7 has not landed"
  note "refusing to evaluate deletion assertions against a non-existent tree;"
  note "they would all pass vacuously and mark protobuf 'removed' before it was added"
  summary S10
  exit 1
fi

# Only IMPORT STATEMENTS matter for a dependency. Prose that explains what was
# replaced must not fail the gate (fifth self-triggering-comment defect here), and
# the .proto files legitimately keep `import "google/protobuf/timestamp.proto"` --
# they remain the documented wire format and are not shipped code.
if grep -rnE --include='*.py' '^[[:space:]]*(from|import)[[:space:]]+google\.protobuf' "$VC" | grep -q .; then
  bad "a google.protobuf import statement remains"
  grep -rnE --include='*.py' '^[[:space:]]*(from|import)[[:space:]]+google\.protobuf' "$VC" | sed 's/^/      /'
else
  ok "no google.protobuf import statements remain"
fi

# proto/climate.py must be DELETED. It holds ClimateHoldSetting(enabled,
# duration_minutes, target_temp_celsius) — a dead, incompatible definition. The
# shipped write uses rivian_climate_pb2.ClimateHoldSetting(hold_time_duration_seconds),
# verified on the wire as 08a038 = 7200s. Keeping the wrong one silently breaks the
# only verified Parallax write.
if [ -e "$VC/proto/climate.py" ]; then
  bad "proto/climate.py still present — it holds the DEAD ClimateHoldSetting"
else
  ok "proto/climate.py deleted"
fi

# proto/vehicle_operation.py must SURVIVE — it is the live command envelope and
# already hand-rolls its encoding, so the _message.Message base drops for free.
have_path "proto/vehicle_operation.py kept (live envelope)" "$VC/proto/vehicle_operation.py"

# Generated modules gone.
# Same rule: an import of a generated module, not a mention of one.
if grep -rnE --include='*.py' '^[[:space:]]*(from|import)[[:space:]]+\S*_pb2' "$VC" | grep -q .; then
  bad "a generated *_pb2 module is still imported"
else
  ok "no *_pb2 imports"
fi
# ...and none of the generated files themselves may ship.
if find "$VC" -name '*_pb2.py' -o -name '*_pb2.pyi' | grep -q .; then
  bad "generated *_pb2 files still present in the package"
else
  ok "no generated *_pb2 files ship"
fi

# The real gate: the package imports with protobuf absent. A grep proves nothing
# about a transitive import chain — proto/__init__.py pulls in eight submodules.
# The system python has neither Home Assistant nor aiohttp; use the project venv.
PY="$(resolve_pytest "$HA")"; PY="${PY%/pytest}/python"
if (cd "$HA" && "$PY" -c "import custom_components.rivian" >/dev/null 2>&1); then
  ok "custom_components.rivian imports"
else
  bad "custom_components.rivian does not import"
fi

# The assertion that actually counts: it must import with protobuf ABSENT. A grep
# proves nothing about a transitive chain, and the dev venv still has protobuf
# installed for the .proto regeneration.
if (cd "$HA" && "$PY" -c "
import importlib.util, sys
if importlib.util.find_spec('google') is not None:
    sys.exit(3)
" >/dev/null 2>&1); then
  ok "protobuf genuinely absent from the test environment"
else
  note "protobuf still installed here (dev tooling); relying on requirements_test.txt"
fi
try "requirements_test.txt does not install protobuf" \
  bash -c "! grep -q '^protobuf' '$HA/requirements_test.txt'"

# Interim protobuf pin removed from the manifest (added in S7, dropped here).
MAN="$HA/custom_components/rivian/manifest.json"
if grep -q 'protobuf' "$MAN"; then
  bad "manifest still declares the interim protobuf pin"
elif grep -q 'bleak' "$MAN"; then
  ok "manifest back to bleak-only"
else
  bad "manifest declares neither protobuf nor bleak — S7 has not landed"
fi

summary S10
