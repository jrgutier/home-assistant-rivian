#!/usr/bin/env bash
# S14 — upstream tracking documented and rehearsed. The rehearsal is a DRY RUN:
# nothing is merged, nothing is pushed.
source "$(dirname "$0")/_lib.sh"
echo "S14 — upstream tracking"

# --- documentation -----------------------------------------------------------
contains "CLAUDE.md documents the vendored client" 'rivian_client' "$HA/CLAUDE.md"
# The old git-URL requirement is the thing vendoring removed; CLAUDE.md described
# it as current for the whole of this project.
if grep -q 'requirements": \["rivian-python-client\[ble\] @ git' "$HA/CLAUDE.md" \
   && ! grep -q 'It previously read' "$HA/CLAUDE.md"; then
  bad "CLAUDE.md still presents the git-URL requirement as current"
else
  ok "CLAUDE.md no longer presents the git URL as current"
fi
contains "CLAUDE.md points at the upstream process" 'UPSTREAM_MERGE_REHEARSAL' "$HA/CLAUDE.md"
have_path "rehearsal captured" "$HA/docs/UPSTREAM_MERGE_REHEARSAL.md"

# --- the client sync path exists and runs ------------------------------------
# The integration merges from upstream normally; the vendored client cannot, so a
# document describing only the merge would cover half the problem.
have_path "client sync script exists" "$HA/scripts/sync_upstream_client.sh"
contains "rehearsal covers the client, not just the merge" \
         'sync_upstream_client' "$HA/docs/UPSTREAM_MERGE_REHEARSAL.md"

# Positive: actually run it. A script nobody has executed is a plan, not a path.
try "client sync script runs and lists upstream commits" \
    bash -c "bash '$HA/scripts/sync_upstream_client.sh' | grep -q 'upstream client commits'"

# --- the vendoring invariant --------------------------------------------------
# While the sibling repo still exists, the two copies must not have drifted. It is
# slated for archival, so its absence is not a failure.
SIB="$HA/../rivian-python-client/src/rivian"
VEN="$HA/custom_components/rivian/rivian_client"
if [ -d "$SIB" ]; then
  drift_list=$(diff -rq --exclude=__pycache__ --exclude=__version__.py "$SIB" "$VEN" 2>/dev/null \
               | grep -v '__init__.py' || true)
  drift=$(printf '%s' "$drift_list" | grep -c . || true)
  if [ "$drift" = "0" ]; then
    ok "vendored client matches the sibling repo (only __init__.py differs, by design)"
  else
    bad "vendored client has drifted from the sibling repo in $drift file(s)"
    printf '%s\n' "$drift_list" | sed 's/^/        /' | head -5
  fi
  sha=$(git -C "$HA/../rivian-python-client" rev-parse HEAD)
  mark=$(sed -n 's/^__version__ = "vendored+\(.*\)"$/\1/p' "$VEN/__init__.py")
  case "$sha" in "$mark"*) ok "vendored-from marker names the sibling's HEAD" ;;
                 *) bad "vendored-from marker $mark is not a prefix of sibling HEAD $sha" ;; esac
else
  note "sibling rivian-python-client not present — skipping the drift check"
fi
# The marker is the only record of which upstream commit the copy corresponds to.
contains "vendored copy records its source commit" 'vendored+' "$VEN/__init__.py"

# --- the rehearsal really was a dry run --------------------------------------
if [ -f "$HA/.git/MERGE_HEAD" ]; then
  bad "a merge is still in progress — the rehearsal did not abort"
else
  ok "no merge in progress"
fi
# NOT "working tree clean": that fails on any ordinary uncommitted work and so
# gets ignored. The invariant is that the rehearsal left no residue.
unmerged=$(cd "$HA" && git diff --name-only --diff-filter=U | grep -c . || true)
check "no unmerged paths left behind" "$unmerged"
if [ -f "$HA/.git/MERGE_MSG" ] && [ -f "$HA/.git/MERGE_HEAD" ]; then
  bad "MERGE_MSG and MERGE_HEAD present — a merge was left half-done"
else
  ok "no half-finished merge state"
fi
markers=$(cd "$HA" && git grep -lE '^(<<<<<<< |>>>>>>> )' -- \
          ':!*.md' ':!scripts/gates/*' 2>/dev/null | grep -c . || true)
check "no conflict markers in tracked files" "$markers"

summary S14
