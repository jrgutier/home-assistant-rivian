#!/usr/bin/env bash
# S13 — HUMAN: end-to-end against the real vehicle. Not automatable; this records the verdict.
source "$(dirname "$0")/_lib.sh"
echo "S13 — E2E acceptance (human)"
have_path "signed-off E2E report" "$HA/docs/E2E_ACCEPTANCE.md"
summary S13
