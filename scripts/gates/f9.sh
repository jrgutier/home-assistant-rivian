#!/usr/bin/env bash
# f9 — the command-state contract after rulings 15 and 22.
#
# What this gate CAN prove: the terminality vocabulary matches the app's;
# the N1 defect text is gone; _execute_command returns on the first frame;
# the frame counter is a real increment, not an overwrite; the subscription
# chain is wired callback -> _command_states -> get_command_state; TIMEOUT
# is reachable only from zero well-formed frames (via the named unit tests);
# the 30 s ceiling was not lowered on a first-frame measurement; the
# observability attributes exist AND are keyed on the id that outlives the
# call; the UI refresh is not gated on an event that may never occur.
#
# What this gate CANNOT prove, and no repo check can: that the vehicle's
# subscription delivers a frame. That is the vehicle's behaviour. With the
# poll gone, a silent subscription is total silence for every command.
# Ruling 15 accepted that. This gate protects everything downstream of the
# first frame; nothing here protects the first frame's arrival.
#
# TIMEOUT disambiguation, because the log is the only distinguisher:
#   TIMEOUT with neither coordinator.py's "_LOGGER.error" on a malformed
#   payload nor its "_LOGGER.warning" on a null state is subscription silence.
#   TIMEOUT with one of them is a payload-shape bug and a different fix.

source "$(dirname "$0")/_lib.sh"

echo "f9 — command-state contract (rulings 15 + 22)"

VENV_PY="$(resolve_python "$HA")"
PYTEST="$(resolve_pytest "$HA")"

E="$HA/custom_components/rivian/entity.py"
C="$HA/custom_components/rivian/coordinator.py"
TR="$HA/tests/apk/transcription.py"
DOC="$HA/docs/E2E_ACCEPTANCE.md"
PRD="$HA/prd.json"
APK="$HA/docs/development/apk"

have_path "entity.py" "$E"
have_path "coordinator.py" "$C"
have_path "the transcription" "$TR"
have_path "the f7/f8 record" "$DOC"

# --- 1. transcription defines the disjoint continue / terminal sets ----------
# Import the constants -- parsing frozenset() with ast.literal_eval crashes.
# `try` swallows stderr; keep the traceback visible on FAIL.
if "$VENV_PY" - "$HA" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from tests.apk.transcription import COMMAND_STATE_CONTINUE, COMMAND_STATE_TERMINAL
if COMMAND_STATE_CONTINUE != frozenset({1, 2, 3, 5}):
    raise SystemExit(f"CONTINUE {COMMAND_STATE_CONTINUE!r}")
if COMMAND_STATE_TERMINAL != frozenset({0, 4, 6, 7}):
    raise SystemExit(f"TERMINAL {COMMAND_STATE_TERMINAL!r}")
if COMMAND_STATE_CONTINUE & COMMAND_STATE_TERMINAL:
    raise SystemExit("continue and terminal overlap")
print("continue {1,2,3,5} terminal {0,4,6,7} disjoint")
PY
then ok "transcription defines disjoint continue {1,2,3,5} and terminal {0,4,6,7}"
else bad "transcription defines disjoint continue {1,2,3,5} and terminal {0,4,6,7}"
fi

# --- 2. the exact N1 defect text is gone ------------------------------------
try "entity.py no longer contains the N1 defect text" \
  bash -c "! grep -qF 'isinstance(state, int) or state in' '$E'"

# --- 3. coordinator.py is where the vocabulary is consumed (ruling 22) ------
contains "coordinator.py references COMMAND_STATE_CONTINUE" \
  "COMMAND_STATE_CONTINUE" "$C"

# --- 4. the three attributes exist, are seeded, and are the live names ------
if "$VENV_PY" - "$E" <<'PY'
import sys, pathlib
src = pathlib.Path(sys.argv[1]).read_text()
needed = ("state_is_lifecycle", "state_frames_seen", "final_command_state")
for name in needed:
    if f'"{name}"' not in src and f"'{name}'" not in src:
        raise SystemExit(f"{name} not in entity.py")
# Seeded in extra_state_attributes before any command: the dict literal
# that runs on every read, not only after a send.
if '"state_frames_seen": 0' not in src:
    raise SystemExit("state_frames_seen is not seeded to 0")
if '"state_is_lifecycle": None' not in src:
    raise SystemExit("state_is_lifecycle is not seeded to None")
if '"final_command_state": None' not in src:
    raise SystemExit("final_command_state is not seeded to None")
if "def extra_state_attributes" not in src:
    raise SystemExit("extra_state_attributes missing")
print("three attributes named, seeded, exposed")
PY
then ok "entity.py exposes and seeds state_is_lifecycle, state_frames_seen, final_command_state"
else bad "entity.py exposes and seeds state_is_lifecycle, state_frames_seen, final_command_state"
fi

# --- 5. first-frame return: entity.py's wait has no terminality test --------
try "entity.py contains no COMMAND_STATE_CONTINUE (wait is not a terminality test)" \
  bash -c "! grep -qF 'COMMAND_STATE_CONTINUE' '$E'"
try "entity.py contains no COMMAND_STATE_TERMINAL" \
  bash -c "! grep -qF 'COMMAND_STATE_TERMINAL' '$E'"

# --- 6. frames_seen is incremented, not overwritten (N10) -------------------
if "$VENV_PY" - "$C" <<'PY'
import sys, pathlib
src = pathlib.Path(sys.argv[1]).read_text()
# A read of the prior counter AND a write of the incremented value.
if 'prior.get("frames_seen"' not in src and "prior.get('frames_seen'" not in src:
    raise SystemExit("no read of prior frames_seen")
if '"frames_seen": frames_seen' not in src and "'frames_seen': frames_seen" not in src:
    raise SystemExit("no write of frames_seen")
if "frames_seen = prior.get" not in src or "+ 1" not in src:
    raise SystemExit("frames_seen is not incremented")
print("frames_seen read + incremented + stored")
PY
then ok "coordinator.py increments frames_seen on both a read and a write"
else bad "coordinator.py increments frames_seen on both a read and a write"
fi

# --- 7 + 8. ceiling interlock -----------------------------------------------
# Pin the 30 s ceiling until the record carries a terminal-latency measurement.
# "terminal latency measured" is NOT a substring of "terminal latency is unmeasured".
DOC_HAS_MEASURED=0
DOC_HAS_UNMEASURED=0
grep -qF "terminal latency measured" "$DOC" && DOC_HAS_MEASURED=1
grep -qF "terminal latency is unmeasured" "$DOC" && DOC_HAS_UNMEASURED=1

if [ "$DOC_HAS_MEASURED" -eq 0 ] && [ "$DOC_HAS_UNMEASURED" -eq 0 ]; then
  bad "E2E_ACCEPTANCE.md names neither unmeasured nor measured terminal latency"
elif [ "$DOC_HAS_MEASURED" -eq 1 ]; then
  ok "terminal latency measured -- 30 s ceiling interlock relaxed"
else
  ok "terminal latency is unmeasured"
  contains "the 30 s ceiling is still 30" "timeout: int = 30" "$E"
fi

# --- 9. the poll is gone and stays gone -------------------------------------
try "coordinator.py has no _poll_command_state" \
  bash -c "! grep -qF '_poll_command_state' '$C'"
try "coordinator.py has no get_vehicle_command_state" \
  bash -c "! grep -qF 'get_vehicle_command_state' '$C'"
try "stale 'subscription does not deliver' comment is absent from coordinator.py" \
  bash -c "! grep -qE 'subscription (does not|never) deliver' '$C'"

# --- 10. the subscription is still wired end to end -------------------------
if "$VENV_PY" - "$C" <<'PY'
import sys, pathlib, re
src = pathlib.Path(sys.argv[1]).read_text()
# _process_command_state writes _command_states
if not re.search(r"def _process_command_state\b", src):
    raise SystemExit("_process_command_state missing")
if "self._command_states[command_id]" not in src:
    raise SystemExit("_process_command_state does not write _command_states")
# _subscribe_to_command_state registers the callback
if not re.search(r"def _subscribe_to_command_state\b", src):
    raise SystemExit("_subscribe_to_command_state missing")
if "callback=lambda data: self._process_command_state" not in src:
    raise SystemExit("subscribe does not register _process_command_state as callback")
# get_command_state reads the store
if not re.search(r"def get_command_state\b", src):
    raise SystemExit("get_command_state missing")
if "return self._command_states.get(command_id)" not in src:
    raise SystemExit("get_command_state does not read _command_states")
print("callback -> _command_states -> get_command_state")
PY
then ok "subscription chain is wired: callback writes _command_states, get_command_state reads it"
else bad "subscription chain is wired: callback writes _command_states, get_command_state reads it"
fi

# --- 11. PARALLAX_REQUEST_ONLY is a proper subset of the seven, size 2 (N6)
if "$VENV_PY" - "$HA" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from tests.apk.transcription import (
    INVALID_WRAPPER_COMMANDS,
    PARALLAX_REQUEST_ONLY_COMMANDS,
)
if not (PARALLAX_REQUEST_ONLY_COMMANDS < INVALID_WRAPPER_COMMANDS):
    raise SystemExit("PARALLAX_REQUEST_ONLY_COMMANDS is not a proper subset")
if len(PARALLAX_REQUEST_ONLY_COMMANDS) != 2:
    raise SystemExit(f"PARALLAX_REQUEST_ONLY has {len(PARALLAX_REQUEST_ONLY_COMMANDS)}, not 2")
print("N6: 2 of 7, proper subset")
PY
then ok "PARALLAX_REQUEST_ONLY_COMMANDS is a proper subset of INVALID_WRAPPER_COMMANDS with exactly 2 members"
else bad "PARALLAX_REQUEST_ONLY_COMMANDS is a proper subset of INVALID_WRAPPER_COMMANDS with exactly 2 members"
fi

# --- 12. N8: no appName / app_name / rshell outside rivian_client/proto ------
# ugrep: inside grep -E, \| is a LITERAL pipe. Write (a|b).
n8_hits=$( { grep -rnE -I --exclude-dir=__pycache__ --exclude-dir=proto --include='*.py' \
  -- 'appName|app_name|rshell' "$HA/custom_components/rivian" || true; } | wc -l | tr -d ' ')
if [ "${n8_hits:-0}" -eq 0 ]; then
  ok "N8: no appName/app_name/rshell under custom_components/rivian/ outside proto/"
else
  bad "N8: appName/app_name/rshell appeared ($n8_hits matches) -- Steps 6-7 reasoning must be revisited"
fi

# --- 13. N7: citations of a missing record, counted as occurrences ----------
# grep -o | wc -l, not grep -c (grep -c counts lines). Tracked files only.
n7_occ=$( { git -C "$HA" grep -o SENDVEHICLEOPERATION_TEST_RESULTS -- \
  ':*.py' ':*.md' ':*.sh' || true; } | wc -l | tr -d ' ')
if [ -f "$HA/docs/development/SENDVEHICLEOPERATION_TEST_RESULTS.md" ]; then
  ok "SENDVEHICLEOPERATION_TEST_RESULTS.md is present ($n7_occ citations)"
else
  if "$VENV_PY" - "$PRD" "$n7_occ" <<'PY'
import json, sys
prd = json.load(open(sys.argv[1]))
occ = int(sys.argv[2])
ids = {e["id"]: e for e in prd.get("known_gaps", [])}
gap = ids.get("sendvehicleoperation-record-missing")
if occ > 0 and gap is None:
    raise SystemExit(
        f"{occ} citations of SENDVEHICLEOPERATION_TEST_RESULTS.md, "
        "file absent, and known_gaps has no sendvehicleoperation-record-missing"
    )
if occ > 0 and gap.get("status") != "open":
    raise SystemExit(
        f"{occ} citations, file absent, known_gaps status={gap.get('status')!r} (want open)"
    )
print(f"{occ} citations, file absent, known_gaps records the open gap")
PY
  then ok "N7: $n7_occ citations of the missing record are covered by an open known_gaps entry"
  else bad "N7: $n7_occ citations of the missing record are covered by an open known_gaps entry"
  fi
fi

# --- 14. named unit tests exist and pass; nothing skipped or deselected -----
# Node ids, not a module glob: a skip marker on one of these is a FAIL.
NODES=(
  tests/test_apk_transcription.py::TestCommandStateVocabulary::test_continue_and_terminal_are_disjoint_and_cover_zero_to_seven
  tests/test_apk_transcription.py::TestCommandStateVocabulary::test_coordinator_imports_the_continue_set_by_name
  tests/test_apk_transcription.py::TestCommandStateVocabulary::test_entity_contains_no_terminality_vocabulary
  tests/test_apk_transcription.py::TestCommandStateVocabulary::test_parallax_request_only_is_two_of_the_invalid_wrapper_seven
  tests/test_apk_transcription.py::TestCommandStateVocabulary::test_our_client_never_sends_app_name
  tests/test_command_state.py::TestFirstFrameReturns::test_a_well_formed_frame_returns_on_the_first_tick
  tests/test_command_state.py::TestTimeoutMeansZeroWellFormedFrames::test_no_frame_is_timeout_with_zero_frames
  tests/test_command_state.py::TestAttributeSurface::test_5a_seeds_before_any_command
  tests/test_command_state.py::TestAttributeSurface::test_5b_read_through_after_the_call_has_returned
  tests/test_command_state.py::TestPollIsGone::test_poll_is_absent_from_subscribe
  tests/test_command_state.py::TestRefreshDoesNotDependOnTerminality::test_continue_set_frames_refresh_the_listeners
  tests/test_command_state.py::test_coordinator_continue_set_matches_the_transcription
)
for node in "${NODES[@]}"; do
  name="${node##*::}"
  file="$HA/${node%%::*}"
  if grep -qF "def $name" "$file"; then
    ok "named test exists: $name"
  else
    bad "named test missing: $name"
  fi
done

if [ ! -x "$PYTEST" ]; then
  bad "pytest not found"
else
  out=$(cd "$HA" && "$PYTEST" -q --no-cov -p no:cacheprovider "${NODES[@]}" 2>&1 || true)
  note "$(echo "$out" | tail -1)"
  if echo "$out" | grep -qE '^FAILED '; then
    bad "named f9 tests failed"
  else
    ok "named f9 tests passed"
  fi
  if echo "$out" | grep -qE '^[0-9]+ (skipped|deselected)'; then
    bad "named f9 tests skipped or deselected"
  else
    ok "named f9 tests: nothing skipped or deselected"
  fi
fi

# --- 15. pre-flight artifacts, skipped without FAIL when absent -------------
if [ -f "$APK/CommandStateSwitch.java" ]; then
  contains "CommandStateSwitch.java contains a switch" "switch (" "$APK/CommandStateSwitch.java"
else
  note "CommandStateSwitch.java absent -- arm skipped (gitignored)"
fi
if [ -f "$APK/CommandStateTerminality.java" ]; then
  if "$VENV_PY" - "$APK/CommandStateTerminality.java" <<'PY'
import sys, re
text = open(sys.argv[1]).read()
need = ("C10180P", "C10181Q", "C10182S", "C10184U")
for name in need:
    if not re.search(rf"^import p588Y9\.{name};", text, re.M):
        raise SystemExit(f"missing continue-set import {name}")
print("four continue-set imports present")
PY
  then ok "CommandStateTerminality.java imports the four continue-set classes"
  else bad "CommandStateTerminality.java imports the four continue-set classes"
  fi
else
  note "CommandStateTerminality.java absent -- arm skipped (gitignored)"
fi
if [ -f "$APK/VASCommandKt.java" ]; then
  if "$VENV_PY" - "$APK/VASCommandKt.java" <<'PY'
import sys, re
text = open(sys.argv[1]).read()
m = re.search(
    r"public static final boolean isParallaxRequestOnly\(VASCommand vASCommand\) \{(.+?)\n    \}",
    text,
    re.S,
)
if not m:
    raise SystemExit("isParallaxRequestOnly not found")
body = m.group(1)
if "TwoFactorDriveEnable" not in body or "TwoFactorDriveDisable" not in body:
    raise SystemExit("predicate does not name both TwoFactorDriveEnable and TwoFactorDriveDisable")
# The five that are NOT Parallax-only must not appear in the predicate.
for name in (
    "EnablePetComfort", "DisablePetComfort", "StartVideoDownloadingSession",
    "TwoFactorDriveAllow", "TwoFactorDriveDeny",
):
    if name in body:
        raise SystemExit(f"isParallaxRequestOnly unexpectedly names {name}")
print("isParallaxRequestOnly names exactly the two")
PY
  then ok "isParallaxRequestOnly names exactly TwoFactorDriveEnable and TwoFactorDriveDisable"
  else bad "isParallaxRequestOnly names exactly TwoFactorDriveEnable and TwoFactorDriveDisable"
  fi
else
  note "VASCommandKt.java absent -- arm skipped (gitignored)"
fi
if [ -f "$APK/VASCommand.java" ]; then
  if "$VENV_PY" - "$APK/VASCommand.java" <<'PY'
import sys, re
text = open(sys.argv[1]).read()
inv = re.search(
    r"public final CloudDataWrapper generateInvalidCloudDataWrapper\(String commandName\) \{(.+?)\n        \}",
    text,
    re.S,
)
if not inv:
    raise SystemExit("generateInvalidCloudDataWrapper not found")
if '""' not in inv.group(1):
    raise SystemExit("invalid-wrapper body has no empty-string appName")
bridge = re.search(
    r"generateCloudDataWrapper\$default\(Companion companion.+?\{(.+?)\n        \}",
    text,
    re.S,
)
if not bridge:
    raise SystemExit("$default bridge not found")
if '"rshell"' not in bridge.group(1):
    raise SystemExit("$default bridge has no rshell default")
print("invalid wrapper appName is empty; default is rshell")
PY
  then ok "generateInvalidCloudDataWrapper uses \"\" and \$default defaults appName to rshell"
  else bad "generateInvalidCloudDataWrapper uses \"\" and \$default defaults appName to rshell"
  fi
else
  note "VASCommand.java absent -- arm skipped (gitignored)"
fi

# --- 16. C1: read-through is keyed on the retained id, not the cleared one --
contains "read-through is keyed on _last_command_id and" \
  "_last_command_id and" "$E"
try "the dead _current_command_id and (live form is absent" \
  bash -c "! grep -qF '_current_command_id and (live' '$E'"
n_clear=$( { grep -cF '_current_command_id = None' "$E" || true; } | tr -d ' ')
if [ "${n_clear:-0}" -eq 1 ]; then
  ok "_current_command_id = None appears exactly once (the finally-clear is neither removed nor duplicated)"
else
  bad "_current_command_id = None appears ${n_clear:-0} times, expected 1"
fi

# --- 17. M1: refresh is not gated on terminality ----------------------------
n_refresh=$( { grep -cF 'async_update_listeners' "$C" || true; } | tr -d ' ')
if [ "${n_refresh:-0}" -ge 4 ]; then
  ok "coordinator.py calls async_update_listeners $n_refresh times (>= 4)"
else
  bad "coordinator.py calls async_update_listeners ${n_refresh:-0} times, expected >= 4"
fi
if "$VENV_PY" - "$C" <<'PY'
import sys, pathlib, ast
src = pathlib.Path(sys.argv[1]).read_text()
tree = ast.parse(src)

class Finder(ast.NodeVisitor):
    def __init__(self):
        self.proc = None
        self.unsub = None
    def visit_FunctionDef(self, node):
        if node.name == "_process_command_state":
            self.proc = node
        elif node.name == "_unsubscribe_command_state":
            self.unsub = node
        self.generic_visit(node)
    visit_AsyncFunctionDef = visit_FunctionDef

f = Finder()
f.visit(tree)
if f.proc is None:
    raise SystemExit("_process_command_state not found")
if f.unsub is None:
    raise SystemExit("_unsubscribe_command_state not found")

def call_lines(fn):
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr == "async_update_listeners":
                out.append(n)
    return out

proc_calls = call_lines(f.proc)
unsub_calls = call_lines(f.unsub)
if not proc_calls:
    raise SystemExit("_process_command_state does not call async_update_listeners")
if not unsub_calls:
    raise SystemExit("_unsubscribe_command_state does not call async_update_listeners")

# Every async_update_listeners in _process_command_state must sit at function
# body indent -- not inside an `if terminal_reached` / `is_lifecycle` arm.
parent = {child: node for node in ast.walk(f.proc) for child in ast.iter_child_nodes(node)}
for call in proc_calls:
    cur = parent.get(call)
    while cur is not None and cur is not f.proc:
        if isinstance(cur, ast.If):
            test = ast.dump(cur.test)
            if "terminal_reached" in test or "is_lifecycle" in test:
                raise SystemExit(
                    "async_update_listeners in _process_command_state is inside a "
                    "terminality test -- the refresh must be unconditional"
                )
        cur = parent.get(cur)
print("per-frame refresh is unconditional; unsubscribe also refreshes")
PY
then ok "async_update_listeners in _process_command_state is not inside a terminality branch"
else bad "async_update_listeners in _process_command_state is not inside a terminality branch"
fi

summary F9
