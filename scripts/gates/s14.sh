#!/usr/bin/env bash
# S14 — upstream tracking documented; merge rehearsed as a DRY RUN.
source "$(dirname "$0")/_lib.sh"
echo "S14 — upstream tracking"
contains "CLAUDE.md documents the vendored client" 'rivian_client' "$HA/CLAUDE.md"
have_path "dry-run rehearsal captured" "$HA/docs/UPSTREAM_MERGE_REHEARSAL.md"
try "working tree clean (merge --abort ran)" git -C "$HA" diff --quiet
summary S14
