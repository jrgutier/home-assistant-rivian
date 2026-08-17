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

# Negative: no protobuf imports survive anywhere in the vendored package.
absent "no google.protobuf imports remain" 'google\.protobuf' "$VC"

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
if { grep -rl -- '_pb2' "$VC" 2>/dev/null || true; } | grep -q .; then
  bad "generated *_pb2 modules still referenced"
else
  ok "no *_pb2 references"
fi

# The real gate: the package imports with protobuf absent. A grep proves nothing
# about a transitive import chain — proto/__init__.py pulls in eight submodules.
if (cd "$HA" && python3 -c "import custom_components.rivian" >/dev/null 2>&1); then
  ok "custom_components.rivian imports"
else
  bad "custom_components.rivian does not import"
fi
note "run this in a venv with protobuf absent — that is the assertion that counts"

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
