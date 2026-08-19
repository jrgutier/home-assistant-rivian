#!/usr/bin/env bash
# pf — pre-flight: the nine decompiled classes every later story cites are
# present, are the RIGHT nine, and are NOT tracked in git.
#
# Two failure modes this gate exists to catch, both of which look like success:
#
#   1. Copying `wcm.java` alone. The app's field set is the union of FIVE
#      vehicleState(id:) documents. With wcm only, f4's delta computes as 24
#      instead of 15, and the nine extra are live working sensors — which re-arms
#      exactly the deletion pressure f4 exists to disarm. So this gate does not
#      merely count files: it asserts the content that is unique to each of the
#      five.
#
#   2. Committing them. This is a public HACS repository and these are decompiled
#      proprietary sources. `git ls-files` must report none of them, and
#      `git check-ignore` must claim all nine.
#
# A clean checkout FAILS this gate. That is intended: pre-flight is a re-runnable
# step, not a one-off, and REGENERATION.md carries the command.

source "$(dirname "$0")/_lib.sh"

echo "pf — pre-flight APK provenance"

APKDIR="$HA/docs/development/apk"
NINE=(VehicleFeature.java VASCommand.java VASCommandKt.java l6e.java \
      wcm.java cdm.java apj.java h9l.java lel.java)

if [ ! -d "$APKDIR" ]; then
  bad "docs/development/apk/ missing — run pre-flight (see REGENERATION.md)"
  summary pf; exit 1
fi

# --- presence, and non-emptiness -------------------------------------------
for f in "${NINE[@]}"; do
  if [ -s "$APKDIR/$f" ]; then ok "present and non-empty: $f"
  else bad "missing or empty: $f"; fi
done

# --- the right nine, asserted by content unique to each ---------------------
# Not file names. A zero-byte or wrong-class file passes a name check.
contains "VehicleFeature carries the capability enum" \
         'VehicleFeature' "$APKDIR/VehicleFeature.java"
n=$( { grep -cE '^[[:space:]]+[A-Z0-9_]+\("' "$APKDIR/VehicleFeature.java" || true; } | tr -d ' ')
if [ "${n:-0}" -eq 64 ]; then ok "VehicleFeature has 64 members"
else bad "VehicleFeature has ${n:-0} members, expected 64"; fi

contains "VASCommand carries the cloud-data wrapper" \
         'generateCloudDataWrapper' "$APKDIR/VASCommand.java"
contains "VASCommand carries the invalid-wrapper routing f6 reasons about" \
         'generateInvalidCloudDataWrapper' "$APKDIR/VASCommand.java"
contains "l6e is the Parallax RVM table" 'VEHICLE_WHEELS' "$APKDIR/l6e.java"

# --- all FIVE vehicleState documents, each proven by its own contribution ---
for f in wcm cdm apj h9l lel; do
  contains "$f.java is a vehicleState(id:) document" \
           'vehicleState(id: $vehicleID)' "$APKDIR/$f.java"
done
contains "apj carries the tyre fields (its unique contribution)" \
         'tirePressureRearRight' "$APKDIR/apj.java"
contains "h9l carries activeDriverName (its unique contribution)" \
         'activeDriverName' "$APKDIR/h9l.java"
contains "lel carries the GNSS consent block (its unique contribution)" \
         'gnssLocation { consentStatus }' "$APKDIR/lel.java"

# wcm alone is NOT the app's field set. Assert the other four each add something
# wcm does not have, so "I copied wcm and stubbed the rest" cannot pass.
for pair in "apj:tirePressureRearRight" "h9l:activeDriverName" "lel:consentStatus"; do
  f="${pair%%:*}"; tok="${pair##*:}"
  if grep -qF -- "$tok" "$APKDIR/wcm.java" 2>/dev/null; then
    bad "$tok found in wcm.java — the five-document split is not what this gate assumes"
  else
    ok "$tok is unique to $f.java, not in wcm.java"
  fi
done

# --- NOT tracked, and positively ignored ------------------------------------
tracked=$(git -C "$HA" ls-files docs/development/apk/ | { grep -E '\.java$' || true; } | wc -l | tr -d ' ')
if [ "$tracked" -eq 0 ]; then ok "no decompiled .java tracked in git"
else bad "$tracked decompiled .java files are TRACKED — public HACS repo"; fi

for f in "${NINE[@]}"; do
  if git -C "$HA" check-ignore -q "docs/development/apk/$f"; then :
  else bad "not gitignored: docs/development/apk/$f"; fi
done
ok "all nine are gitignored (checked individually)"

# --- the regeneration command is recorded, and IS tracked -------------------
have_path "REGENERATION.md exists" "$APKDIR/REGENERATION.md"
contains "REGENERATION.md names the jadx command" \
         'jadx -d src --no-res --no-debug-info' "$APKDIR/REGENERATION.md"
contains "REGENERATION.md names the app version" \
         '3.15.0' "$APKDIR/REGENERATION.md"
contains "REGENERATION.md warns that apktool output lacks l6e/wcm" \
         'apktool' "$APKDIR/REGENERATION.md"
if git -C "$HA" ls-files --error-unmatch docs/development/apk/REGENERATION.md >/dev/null 2>&1; then
  ok "REGENERATION.md IS tracked (the doc ships; the sources do not)"
else
  bad "REGENERATION.md is not tracked — a clean checkout would have no way back"
fi

# --- the decoy tree stays out of the index ----------------------------------
if git -C "$HA" ls-files com.rivian.android.consumer/ | grep -q .; then
  bad "the apktool tree is tracked again — it lacks l6e.java and wcm.java"
else
  ok "the apktool decoy tree is not tracked"
fi

summary pf
