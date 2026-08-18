#!/usr/bin/env bash
# Bring an upstream rivian-python-client change into the vendored copy.
#
# The client is vendored at custom_components/rivian/rivian_client/ and edited in
# place: there is no package to bump and no publish step. That removes the moving
# git-URL requirement that made installs unreproducible, but it also removes the
# path upstream fixes used to arrive by, so this script is that path.
#
# It deliberately does NOT need the sibling rivian-python-client checkout. That
# repo is a staging area at best and is slated for archival; a process that only
# works on the maintainer's laptop is not a process. Upstream is fetched straight
# into this repo as the `client-upstream` remote -- an unrelated history, which
# git is perfectly happy to hold alongside our own.
#
# Usage:
#   scripts/sync_upstream_client.sh                 # what is waiting upstream
#   scripts/sync_upstream_client.sh <from>..<to>    # apply that range
#   scripts/sync_upstream_client.sh --check <range> # dry run, change nothing
#
# Path mapping: upstream paths are src/rivian/<f>, ours are
# custom_components/rivian/rivian_client/<f>, hence -p3 plus --directory.
# -p2 leaves an extra rivian/ segment and fails with "No such file or directory",
# which is the first thing to check if this stops working.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

REMOTE=client-upstream
URL=https://github.com/bretterer/rivian-python-client.git
VENDORED=custom_components/rivian/rivian_client
STRIP=3

git remote get-url "$REMOTE" >/dev/null 2>&1 || git remote add "$REMOTE" "$URL"
git fetch --quiet "$REMOTE"

CHECK=0
if [ "${1:-}" = "--check" ]; then CHECK=1; shift; fi
RANGE="${1:-}"

if [ -z "$RANGE" ]; then
  echo "upstream client commits touching src/rivian, newest first:"
  git log --oneline -20 "$REMOTE/main" -- src/rivian | sed 's/^/  /'
  echo
  echo "The vendored copy carries no upstream commit ids, so git cannot tell you"
  echo "which of these are already in. Check the marker in $VENDORED/__init__.py,"
  echo "then re-run with a range, e.g.:"
  echo "  $0 --check <sha>^..<sha>"
  exit 0
fi

PATCH="$(mktemp)"
trap 'rm -f "$PATCH"' EXIT
git diff "$RANGE" -- src/rivian > "$PATCH"

if [ ! -s "$PATCH" ]; then
  echo "no changes under src/rivian in $RANGE — nothing to sync"
  exit 0
fi

echo "range $RANGE touches:"
git diff --stat "$RANGE" -- src/rivian | sed 's/^/  /'
echo

# Reverse-applying is how you tell "already vendored" from "does not fit". Both
# fail a forward --check, and they need opposite responses.
if git apply -R --check -p"$STRIP" --directory="$VENDORED" "$PATCH" 2>/dev/null; then
  echo "this range is ALREADY in the vendored tree (it reverse-applies cleanly)"
  exit 0
fi

if ! git apply --check -p"$STRIP" --directory="$VENDORED" "$PATCH" 2>/dev/null; then
  echo "does not apply cleanly. Resolve by hand:"
  echo "  git apply --3way -p$STRIP --directory=$VENDORED <patch>"
  echo "The patch is the diff of: git diff $RANGE -- src/rivian"
  exit 1
fi

if [ "$CHECK" = 1 ]; then
  echo "applies cleanly (dry run — nothing changed)"
  exit 0
fi

git apply -p"$STRIP" --directory="$VENDORED" "$PATCH"
echo "applied. Now:"
echo "  1. update the vendored-from marker in $VENDORED/__init__.py"
echo "  2. .venv/bin/pytest -q && .venv/bin/python scripts/check_coverage.py"
echo "  3. bash scripts/load_test.sh   (upstream may import something new)"
