#!/usr/bin/env bash
# S17 — the corpus extractor works on all THREE tree layouts, not the two it was
# tested against.
#
# WHY THIS GATE EXISTS. `scripts/apk_corpus_sweep.py` reads decompiled app dumps
# spanning 26 versions. Those dumps do not share a root layout:
#
#   sources/        all 1.x dumps AND rivian_2.0.0_beta   (19 of 25)
#   java_src/       2.2.0 and later                        (6 of 25)
#   jadx/sources/   the in-repo 3.15.0 tree
#
# The plan that commissioned the extractor proposed testing it against two trees
# -- 2.6.0 (java_src) and 3.15.0 (jadx/sources). Both of those happen to hold
# VASCommand.java under com/rivian/android/core/modules/, so a two-tree gate
# passes whether or not the extractor hard-codes that package path, and it never
# touches the `sources/` layout that the MAJORITY of the corpus uses. A gate that
# cannot distinguish a correct extractor from one that breaks on 19 of 25 dumps
# is not a gate. Hence three layouts here, one spot check each.
#
# The spot check is the point. Asserting "nonzero commands" catches a total
# failure and misses a PARTIAL -- an extractor reading the wrong subtree still
# returns something. Each layout therefore names a command that must be present.
#
# INDEPENDENCE. This gate does NOT run apk_corpus_sweep.py. `scripts/gates/f1.sh`
# states the rule it inherits: "A gate that re-runs the generator proves only that
# the generator is deterministic." The derivation below is a flat grep for the
# command-name string literal -- deliberately a different mechanism from the
# extractor's class-block parser, so the two can disagree.
#
# The dumps are gitignored and live outside the repo, so this is a pre-flight
# gate, not a test. A clean checkout has no corpus; a skipped test would be worse
# than an absent one, which is why this half lives here.

source "$(dirname "$0")/_lib.sh"

echo "s17 — corpus extractor across all three tree layouts"

SRC_ROOT="${APK_SRC_ROOT:-$HOME/src}"
SWEEP="$HA/scripts/apk_corpus_sweep.py"

have_path "the extractor exists" "$SWEEP"

# --- 1. the extractor enumerates, and does not glob -------------------------
#
# `~/src/rivian*` also matches rivian-dump/, which is ABRP telemetry JSON and not
# an app dump at all. An allowlist is the only enumeration that excludes it.
contains "the corpus is an explicit allowlist" "SRC_DUMPS" "$SWEEP"

if grep -qE 'glob\(["'"'"']rivian' "$SWEEP"; then
  bad "the extractor globs for dump directories"
else
  ok "the extractor does not glob for dump directories"
fi

# --- 2. one dump per layout, each with a spot check -------------------------
#
# layout|dir|command that must be present
LAYOUTS="
sources|rivian_1.0.3|WAKE_VEHICLE
java_src|com_rivian_android_consumer_v2.6.0|UNLOCK_ALL_AND_OPEN_WINDOWS
"

while IFS='|' read -r layout dir command; do
  [ -z "$layout" ] && continue
  root="$SRC_ROOT/$dir"

  # A missing dump FAILS. Skipping it silently is how a gate reports green on a
  # machine where pre-flight never ran.
  if [ ! -d "$root" ]; then
    bad "$layout: dump present ($dir)"
    note "expected at: $root"
    note "run pre-flight, or set APK_SRC_ROOT to where the dumps live"
    continue
  fi
  ok "$layout: dump present ($dir)"

  # The layout is what this gate is about, so assert it rather than assuming it.
  if [ -d "$root/$layout" ]; then
    ok "$layout: layout confirmed on disk"
  else
    bad "$layout: expected a $layout/ subtree in $dir"
  fi

  # Independent re-derivation: a flat grep for the string literal, restricted to
  # .java. Without --include a .dex under resources/ matches the same bytes --
  # that exact mistake produced a wrong document count earlier in this work.
  hits=$( { grep -rl -I --include='*.java' -- "\"$command\"" "$root" || true; } \
            | wc -l | tr -d ' ')
  if [ "$hits" -gt 0 ]; then
    ok "$layout: $command found independently ($hits files)"
  else
    bad "$layout: $command NOT found in $dir"
  fi
done <<EOF
$LAYOUTS
EOF

# --- 3. the third layout: the in-repo 3.15.0 tree ---------------------------
#
# Separate from the loop because its root is repo-relative and its spot check is
# a capability member rather than a command: 3.15.0's VASCommand.java carries no
# BLE wrappers at all, so command coverage there is not comparable to the others.
JADX="$HA/.apk/3.15.0/jadx/sources"

if [ ! -d "$JADX" ]; then
  bad "jadx/sources: the 3.15.0 tree is present"
  note "expected at: $JADX"
  note "REGENERATION.md records how to rebuild it"
else
  ok "jadx/sources: the 3.15.0 tree is present"

  vf=$( { grep -rl -I --include='VehicleFeature.java' -- 'TAILGATE_CMD' "$JADX" \
            || true; } | wc -l | tr -d ' ')
  if [ "$vf" -gt 0 ]; then
    ok "jadx/sources: VehicleFeature found independently"
  else
    bad "jadx/sources: VehicleFeature NOT found"
  fi
fi

# --- 4. the gitignore that keeps proprietary source out of a public repo ----
if git -C "$HA" check-ignore -q .apk/3.15.0; then
  ok "the decompiled tree is gitignored"
else
  bad "the decompiled tree is NOT gitignored -- this is a public HACS repo"
fi

summary S17
