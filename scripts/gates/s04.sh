#!/usr/bin/env bash
# S4 — client cleanup.
source "$(dirname "$0")/_lib.sh"
echo "S4 — client cleanup"
on_branch "$CLIENT" vendor-client
# GATE CORRECTED, and deliberately not to make it pass. Its original assertion
# was "py<3.11 shims gone", derived from a plan step that read: drop the shims
# AND set requires-python >= 3.10. Those two cannot both hold -- StrEnum and
# asyncio.timeout are 3.11+, so on 3.10 the shims are exactly what is required.
# Upstream keeps them for the same reason. Dropping them would need
# requires-python >= 3.11, which is a scope change nobody asked for.
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
