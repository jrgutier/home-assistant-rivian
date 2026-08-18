#!/usr/bin/env bash
# S6a — Parallax routed through real decoders; get() unified.
source "$(dirname "$0")/_lib.sh"
echo "S6a — Parallax routing + get() unification"
C="$HA/custom_components/rivian/coordinator.py"
absent "the {\"raw\": ...} stub is gone" 'TODO: Add protobuf decoding' "$HA/custom_components"
contains "routes to decode_parallax_message" 'decode_parallax_message' "$C"
# Code only: a comment EXPLAINING why rvms=None is wrong must not fail the gate.
# (s02 hit the same self-triggering-comment problem.)
if grep -rn --include='*.py' 'rvms=None' "$HA/custom_components" \
     | sed 's/#.*//' | grep -q 'rvms=None'; then
  bad "a live rvms=None subscription remains"
else
  ok "no rvms=None subscription in code"
fi
if [ -f "$HA/tests/test_parallax_coordinator.py" ] && \
   grep -qF 'test_decode_unknown_rvm_returns_raw' "$HA/tests/test_parallax_coordinator.py"; then
  bad "test_decode_unknown_rvm_returns_raw still present (must be DELETED, not adapted)"
else
  ok "stub-asserting test deleted"
fi
n=$( { grep -cE '^[[:space:]]*def get\(' "$C" || true; } )
if [ "$n" -le 1 ]; then ok "single get() definition ($n)"; else bad "$n get() definitions remain"; fi
summary S6a
