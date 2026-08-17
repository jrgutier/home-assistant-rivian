#!/usr/bin/env bash
# S5 — HA integration merged with upstream 1.5.3b5.
#
# This gate carries more weight than the others. S5 runs in the loop across all
# 19 conflicted files, by explicit user decision, against the recommendation to
# split it. The accepted risk: a take-ours resolution satisfies "no conflict
# markers + pytest green" perfectly while silently dropping the upstream fixes
# the merge exists to acquire. Those fixes break nothing a test can see; they
# surface weeks later as field bugs.
#
# So this gate asserts the acquired fixes BY VALUE, not just by symbol. Every
# assertion below was validated 6/6 against the real 1.5.3b5 tree.
#
# A mandatory human review follows a green result here, before S6a.

source "$(dirname "$0")/_lib.sh"

echo "S5 — upstream 1.5.3b5 merged into home-assistant-rivian"

on_branch "$HA" vendor-client

# 1. Upstream is genuinely in the history. Defeats "resolved" by never merging.
try "1.5.3b5 is an ancestor of HEAD" \
    git -C "$HA" merge-base --is-ancestor 1.5.3b5 HEAD

# 2. No unresolved markers.
absent "no conflict markers" '^(<<<<<<<|=======$|>>>>>>>)' "$HA/custom_components"

# 3. Upstream-fix manifest — the part a take-ours merge would drop silently.
COORD="$HA/custom_components/rivian/coordinator.py"
CONST="$HA/custom_components/rivian/const.py"
INIT="$HA/custom_components/rivian/__init__.py"

contains "a7e00d0: INITIAL_UPDATE_TIMEOUT = 60 (not 1s)" \
         'INITIAL_UPDATE_TIMEOUT = 60' "$COORD"
contains "ab760d1: vehicleMileage oscillation branch" \
         'elif k == "vehicleMileage":' "$COORD"
contains "ab760d1: monotonic guard on the Parallax odometer" \
         'new_val >= prev_val' "$COORD"
contains "charging-schedule constants present" \
         'MINUTES_PER_DAY' "$CONST"
have_path "upstream's new time.py platform" \
         "$HA/custom_components/rivian/time.py"
contains "Platform.TIME registered" \
         'Platform.TIME' "$INIT"

# 4. Our side survived the merge too.
have_path "our navigation service kept" "$HA/custom_components/rivian/notify.py"
have_path "our next_action_states kept"  "$HA/custom_components/rivian/next_action_states.py"

# 5. Both client pins agree and point at a SHA, not a moving branch.
if grep -qE 'rivian-python-client.*@(dev|main)\b' "$HA/custom_components/rivian/manifest.json"; then
  bad "manifest.json still pins a moving branch"
else
  ok "manifest.json does not pin a moving branch"
fi

# 6. Version must satisfy pre-release.yaml's regex, which accepts X.Y.Z-betaN or
#    X.Y.Z. Upstream's committed "0.0.0" ALSO matches, and would silently publish
#    0.0.0-beta1 sorting below every existing release — so assert it is not 0.0.0.
VER=$(python3 -c "import json;print(json.load(open('$HA/custom_components/rivian/manifest.json'))['version'])")
if [[ "$VER" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-beta[0-9]+)?$ ]] && [ "$VER" != "0.0.0" ]; then
  ok "version '$VER' passes pre-release.yaml and is not 0.0.0"
else
  bad "version '$VER' fails pre-release.yaml regex or is the silent 0.0.0 case"
fi

# 7. Tests were not deleted to reach green.
test_count "$HA" 301

summary S5
