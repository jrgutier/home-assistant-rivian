#!/usr/bin/env bash
#
# RETIRED 2026-08-20 -- this gate can no longer assert anything, by design.
#
# It gated the story "merge the client onto upstream 2.1.0's transport" in PRD
# vendor-rivian-client-parallax, which is COMPLETE: all 20 stories show
# passes:true, and its branch `vendor-client` no longer exists.
#
# Every check below is conditional on the sibling repo rivian-python-client being
# present. It is not, and it will not be again: story s07 VENDORED the client into
# custom_components/rivian/rivian_client/, which is exactly what this gate helped
# verify. So S3 now skips and reports "0 passed, 0 failed" -- it exits 0 without
# checking anything.
#
# It is kept, not deleted, because it is the executable record of how the vendoring
# was verified. Read its exit 0 as "not applicable", NEVER as "verified". A sweep
# that counts this as a pass is counting a check that cannot fail -- the same defect
# s16.sh exists to catch elsewhere.
#
# S3 — client merged onto upstream 2.1.0's transport. HUMAN story; this gate verifies
# the result, it does not make the merge safe to automate.
source "$(dirname "$0")/_lib.sh"
echo "S3 — client on upstream transport"
if [ ! -d "$CLIENT" ]; then
  note "sibling rivian-python-client not present — skipping client transport checks"
  summary S3
  exit 0
fi
on_branch "$CLIENT" vendor-client
try "2.1.0 is an ancestor of HEAD" git -C "$CLIENT" merge-base --is-ancestor 2.1.0 HEAD
absent "no conflict markers" '^(<<<<<<<|=======$|>>>>>>>)' "$CLIENT/src"
absent "no gql/graphql imports remain" '^[[:space:]]*(from|import) (gql|graphql)\b' "$CLIENT/src"
[ -e "$CLIENT/src/rivian/schema.py" ] && bad "schema.py still present (gql DSL not removed)" \
                                      || ok "schema.py deleted"
# Preserved-symbol manifest: defeats resolve-by-deletion, which 'pytest green' cannot see.
P="$CLIENT/src/rivian/parallax.py"; R="$CLIENT/src/rivian/rivian.py"
contains "upstream's decode_parallax_message survived"  'def decode_parallax_message' "$P"
contains "upstream's RVM_DECODERS survived"             'RVM_DECODERS' "$P"
contains "our RVMType survived"                         'class RVMType' "$P"
contains "our build_climate_hold_command survived"      'def build_climate_hold_command' "$P"
contains "our send_vehicle_operation survived"          'def send_vehicle_operation' "$R"
contains "our subscribe_for_parallax_messages survived" 'def subscribe_for_parallax_messages' "$R"
have_path "our ble_gen2 survived" "$CLIENT/src/rivian/ble_gen2.py"
summary S3
