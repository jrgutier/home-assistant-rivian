#!/usr/bin/env bash
# S12b — release hardening. BOTH workflows; pre-release fires on every dev push.
source "$(dirname "$0")/_lib.sh"
echo "S12b — release hardening"
REL="$HA/.github/workflows/release.yaml"; PRE="$HA/.github/workflows/pre-release.yaml"
for f in "$REL" "$PRE"; do
  b=$(basename "$f")
  if grep -qE "zip .*(-x|-i) " "$f"; then ok "$b zip has an allow/deny list"
  else bad "$b still does a bare recursive zip"; fi
done
if grep -qE "sed -i.*'/version/c" "$REL"; then
  bad "release.yaml sed still unanchored (rewrites every line containing 'version')"
else ok "release.yaml sed anchored"; fi
summary S12b
