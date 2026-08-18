#!/usr/bin/env bash
# Inspect a built rivian.zip before it reaches users.
#
# pre-release.yaml fires on every push to dev and dev-*, and what it publishes is
# what beta users install. Both release workflows used a bare recursive zip of
# custom_components/rivian, which ships whatever happens to be sitting in that
# directory -- a stray dotfile, a scratch script, a __pycache__ from a local run.
#
# Two checks, deliberately separate:
#   1. contents  -- only the file types the integration actually needs
#   2. secrets   -- nothing token-shaped, no private key, no .env
#
# Patterns are narrow on purpose. A scanner that fires on ordinary source turns
# into a workflow people add `|| true` to.
#
# Usage: scripts/scan_artifact.sh path/to/rivian.zip

set -euo pipefail

ZIP="${1:?usage: scan_artifact.sh <zipfile>}"
[ -f "$ZIP" ] || { echo "error: no such file: $ZIP" >&2; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
unzip -q "$ZIP" -d "$WORK"

fails=0
fail() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }
pass() { printf '  PASS  %s\n' "$1"; }

echo "scanning $ZIP"

# --- 1. contents -------------------------------------------------------------
# Anything outside this set is unexpected. Listing what is allowed rather than
# what is forbidden is the whole point: a deny-list only catches what someone
# already thought of.
unexpected=$(
  find "$WORK" -type f \
    ! -name '*.py' ! -name '*.json' ! -name '*.graphql' \
    ! -name '*.proto' ! -name '*.yaml' ! -name 'py.typed' \
    -printf '%P\n' 2>/dev/null || \
  find "$WORK" -type f \
    ! -name '*.py' ! -name '*.json' ! -name '*.graphql' \
    ! -name '*.proto' ! -name '*.yaml' ! -name 'py.typed' \
    | sed "s|^$WORK/||"
)
if [ -z "$unexpected" ]; then
  pass "no unexpected file types"
else
  fail "unexpected files in the artifact:"
  echo "$unexpected" | sed 's/^/          /'
fi

dotfiles=$(find "$WORK" -name '.*' ! -name '.' ! -name '..' | sed "s|^$WORK/||")
if [ -z "$dotfiles" ]; then
  pass "no dotfiles"
else
  fail "dotfiles in the artifact:"
  echo "$dotfiles" | sed 's/^/          /'
fi

if find "$WORK" -name '__pycache__' -type d | grep -q .; then
  fail "__pycache__ shipped"
else
  pass "no __pycache__"
fi

# --- 2. secrets --------------------------------------------------------------
# Narrow, high-signal patterns. Each one is a thing that has no business in
# source and cannot plausibly be a false positive.
scan() {
  local label="$1" pattern="$2" hits
  hits=$(grep -rlIE "$pattern" "$WORK" 2>/dev/null | sed "s|^$WORK/||" || true)
  if [ -z "$hits" ]; then
    pass "no $label"
  else
    # Print the file, never the match -- this output goes to a public CI log.
    fail "$label found in:"
    echo "$hits" | sed 's/^/          /'
  fi
}

scan "PEM private key" '^-+BEGIN [A-Z ]*PRIVATE KEY-+'
scan "JWT-shaped literal" 'eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}'
scan "assigned credential literal" \
  '(access_token|refresh_token|user_session_token|csrf_token|app_session_token|private_key)["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"'][A-Za-z0-9_/+-]{20,}["'"'"']'

echo
if [ "$fails" -eq 0 ]; then
  echo "artifact clean"
else
  echo "$fails check(s) failed — this artifact must not be published"
fi
exit $([ "$fails" -eq 0 ] && echo 0 || echo 1)
