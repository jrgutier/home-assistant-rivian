#!/usr/bin/env bash
# f7 — every command in the pool carries a DISPOSITION, and the prohibited one
# carries its own.
#
# The pressure here is toward an existence check: assert the doc mentions f7 and
# call the story passed. That is the s13.sh shape this project already condemns,
# and it would have passed while the run was still deferred. So every assertion
# below names a specific command and a specific disposition.
#
# The pool is 13: two closure-openers, four third-row seat-heat spellings, and the
# seven generateInvalidCloudDataWrapper commands. OPEN_TAILGATE is PROHIBITED by
# the owner (2026-08-19) -- the truck is parked where it strikes the garage -- and
# that is a disposition distinct from "not run", so it is asserted by name.

source "$(dirname "$0")/_lib.sh"

echo "f7 — actuate the residue"

VENV_PY="$(resolve_python "$HA")"

DOC="$HA/docs/E2E_ACCEPTANCE.md"
COV="$HA/docs/development/COMMAND_COVERAGE.md"

have_path "the f7 record exists" "$DOC"
contains "f7 is recorded as having RUN, not deferred" "## f7 — actuate the residue" "$DOC"
contains "the stale 'f7 not attempted' note is superseded, not deleted" \
  "Supersedes, does not replace" "$DOC"

# The prohibition is a first-class disposition, not silence.
contains "OPEN_TAILGATE is recorded as NOT SENT" "not sent — owner prohibited" "$DOC"
contains "the prohibition names its physical reason" "strikes the garage" "$DOC"
try "OPEN_TAILGATE is never recorded as accepted or rejected" \
  bash -c "! grep -E '\\\`OPEN_TAILGATE\\\`.*\\|.*(accepted|rejected)' '$DOC'"

# The spelling question is the one capability answer f7 bought. Both halves.
contains "the ACCEPTED third-row spelling is named" "CABIN_HVAC_3RD_ROW_REAR_LEFT_SEAT_HEAT" "$DOC"
contains "the REJECTED third-row spelling is named" "CABIN_HVAC_THIRD_ROW_LEFT_SEAT_HEAT" "$DOC"
contains "the spelling verdict reached COMMAND_COVERAGE" "ANSWERED by f7" "$COV"

# Every one of the seven invalid-wrapper commands carries a disposition.
"$VENV_PY" - "$DOC" <<'PYEOF'
import re, sys
doc = open(sys.argv[1]).read()
seven = [
    "PET_COMFORT_ON", "PET_COMFORT_OFF", "START_VIDEO_DOWNLOADING_SESSION",
    "TWO_FACTOR_DRIVE_ALLOW", "TWO_FACTOR_DRIVE_DENY",
    "TWO_FACTOR_DRIVE_DISABLE", "TWO_FACTOR_DRIVE_ENABLE",
]
missing = [c for c in seven if c not in doc]
if missing:
    print(f"no disposition recorded for: {sorted(missing)}")
    sys.exit(1)
# and each must sit on a line that also records what happened to it
undecided = []
for c in seven:
    lines = [ln for ln in doc.splitlines() if c in ln]
    if not any(re.search(r"rejected|accepted|not sent", ln, re.I) for ln in lines):
        undecided.append(c)
if undecided:
    print(f"named but with no outcome: {sorted(undecided)}")
    sys.exit(1)
print(f"all {len(seven)} invalid-wrapper commands carry an outcome")
PYEOF
check "each of the seven invalid-wrapper commands has a recorded outcome" $?

# A transport-shaped rejection must not be written up as a capability verdict.
contains "the uniform rejection is read as TRANSPORT, not capability" \
  "transport" "$DOC"
contains "Principle -1 is honoured: nothing removed on a rejection" \
  "Nothing is removed on this evidence" "$DOC"

# The guardrail that could not be discharged is stated, not implied as met.
contains "the no-state-surface commands are declared undischargeable" \
  "no state surface" "$DOC"

# Owner ruling 14: the latency question is answered with numbers.
contains "the measured latency is recorded" "1.47" "$DOC"
try "the recorded latency is a measurement, not an estimate" \
  bash -c "grep -qE 'Send→terminal|send to terminal|send→terminal' '$DOC'"

summary F7
