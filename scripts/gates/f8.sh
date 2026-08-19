#!/usr/bin/env bash
# f8 — the field residue probe is recorded with a VERDICT the gate understands.
#
# The trap this gate exists to avoid: f8 can legitimately end without answering
# anything, and an existence check ("the doc mentions f8") would pass on a stub,
# on a deferral, and on a run that reported five absent fields it never actually
# measured. So the verdict vocabulary is closed -- the record must say either that
# the five were probed as sole subscriber, or that the run was inconclusive AND
# why the instrument failed. "Deferred" is not in the vocabulary: a story that has
# been attempted cannot still be deferred.

source "$(dirname "$0")/_lib.sh"

VENV_PY="$(resolve_python "$HA")"

echo "f8 — field residue probe"

DOC="$HA/docs/development/UNPOPULATED_FIELDS.md"
PROBE="$HA/scripts/f8_probe.py"

have_path "the f8 record exists" "$DOC"
have_path "the probe is committed, not left in a session directory" "$PROBE"

contains "f8 is recorded as attempted" "f8 attempted" "$DOC"

# The verdict must be one this gate knows. Inconclusive is a PASS -- it is an
# honest outcome -- but it must be labelled, and it must carry its reason.
"$VENV_PY" - "$DOC" <<'PYEOF'
import sys
doc = open(sys.argv[1]).read()
VERDICTS = ("INCONCLUSIVE", "PROBED", "DELIVERED", "NEVER DELIVERED")
found = [v for v in VERDICTS if v in doc]
if not found:
    print(f"no recognised verdict in the record; expected one of {VERDICTS}")
    sys.exit(1)
if "INCONCLUSIVE" in found:
    # An inconclusive run must say why the instrument failed, or it is
    # indistinguishable from not having run.
    for needed in ("control", "sole subscriber"):
        if needed.lower() not in doc.lower():
            print(f"inconclusive recorded without '{needed}' -- reason not given")
            sys.exit(1)
print(f"verdict recorded: {sorted(found)}")
PYEOF
check "the record carries a verdict this gate understands" $?

# The five fields must each be named, whatever the verdict.
"$VENV_PY" - "$DOC" <<'PYEOF'
import sys
doc = open(sys.argv[1]).read()
five = [
    "tirePressureStatusValidFrontLeft", "tirePressureStatusValidFrontRight",
    "tirePressureStatusValidRearLeft", "tirePressureStatusValidRearRight",
    "cabinHoldNotification",
]
missing = [f for f in five if f not in doc]
if missing:
    print(f"fields not named in the record: {sorted(missing)}")
    sys.exit(1)
print(f"all {len(five)} target fields named")
PYEOF
check "all five target fields are named in the record" $?

# Principle -1: an inconclusive run removes nothing.
contains "no verdict changed on an inconclusive run" "No verdict changes" "$DOC"

# The outage must be accounted for, including the restore.
contains "the integration outage window is recorded" "Outage" "$DOC"
contains "recovery is evidenced, not asserted" "fresh recorder rows" "$DOC"

# f8 forced a retraction; it must be annotated where it was originally claimed.
contains "the retraction reached WS_CONTENTION.md, the document it retracts" \
  "RETRACTION NOTICE" "$HA/docs/development/WS_CONTENTION.md"

# The probe must still carry its control -- that control is what stopped f8
# reporting five absent fields it had not measured.
contains "the probe keeps a known-good CONTROL" "CONTROL" "$PROBE"
contains "the probe bisects rather than sending one document" "BISECT" "$PROBE"

summary F8
