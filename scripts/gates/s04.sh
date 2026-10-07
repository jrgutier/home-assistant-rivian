#!/usr/bin/env bash
#
# MOSTLY RETIRED 2026-08-20 -- one live assertion remains, added in s53.
#
# It gated the story "client cleanup" in PRD
# vendor-rivian-client-parallax, which is COMPLETE: all 20 stories show
# passes:true, and its branch `vendor-client` no longer exists.
#
# Every check after the skip below is conditional on the sibling repo
# rivian-python-client being present. It is not, and it will not be again: story
# s07 VENDORED the client into custom_components/rivian/rivian_client/, which is
# exactly what this gate helped verify. Those checks are kept, not deleted,
# because they are the executable record of how the vendoring was verified.
#
# So a sibling-less run reports exactly "1 passed": the vendored-shim check. Read
# that as "the vendored copy has no py<3.11 shims" and NOTHING about the sibling
# checks, which did not run. A sweep that counts the skipped half as verified is
# counting a check that cannot fail -- the same defect s16.sh exists to catch
# elsewhere.
#
# S4 — client cleanup.
source "$(dirname "$0")/_lib.sh"
echo "S4 — client cleanup"
# The vendored copy and the sibling answer this question OPPOSITELY, on purpose.
# The sibling declares requires-python >= 3.10, where the shims are required (see
# below). The vendored copy only ever runs inside Home Assistant, whose floor is
# Python 3.13.2 (hacs.json 2025.6.0), so there the else-branches could not run
# and named packages (backports.strenum, async_timeout, typing_extensions) that
# manifest.json does not declare. s53 removed them; this keeps an upstream sync
# from quietly bringing them back.
absent "vendored client carries no py<3.11 shims" \
  'sys\.version_info|backports|^[[:space:]]*import async_timeout|typing_extensions' \
  "$_REPO_ROOT/custom_components/rivian/rivian_client"
if [ ! -d "$CLIENT" ]; then
  note "sibling rivian-python-client not present — skipping client cleanup checks"
  summary S4
  exit 0
fi
on_branch "$CLIENT" vendor-client
# GATE CORRECTED, and deliberately not to make it pass. Its original assertion
# was "py<3.11 shims gone", derived from a plan step that read: drop the shims
# AND set requires-python >= 3.10. Those two cannot both hold -- StrEnum and
# asyncio.timeout are 3.11+, so on 3.10 the shims are exactly what is required.
# Upstream keeps them for the same reason. Dropping them would need
# requires-python >= 3.11, which is a scope change nobody asked for. (That is
# the SIBLING's floor. The vendored copy's is 3.13.2, hence the check above.)
#
# What was actually wrong was subtler: async_timeout was imported on 3.10 and
# declared by nobody, resolving only because aiohttp happens to depend on it
# below 3.11. So the gate now asserts the shims are DECLARED, not absent.
contains "requires-python is >=3.10"        'requires-python = ">=3.10"' "$CLIENT/pyproject.toml"
contains "backports-strenum declared for py<3.11" 'backports-strenum' "$CLIENT/pyproject.toml"
contains "async-timeout declared for py<3.11"     'async-timeout'     "$CLIENT/pyproject.toml"
# Narrowed to phone_id. A bare '32-byte' grep also flags ble_gen2's HMAC-SHA256
# signatures and ECDH shared secrets, which really are 32 bytes -- the defect was
# only ever that phone_id is uuid.UUID(vasPhoneId).bytes, i.e. 16.
absent "no '32-byte phone' references" '32-byte phone' "$CLIENT/src"
summary S4
