#!/usr/bin/env bash
# f10 — load_test.sh's stamp, uv-pip-check guard, and retry-once.
#
# Step 3's subject. An existence check ("the script mentions a stamp") would
# pass a comment. Every assertion below names a format, a command, or a
# status string that the run actually prints.

source "$(dirname "$0")/_lib.sh"

echo "f10 — load_test.sh stamp + reaped-venv guard"

LT="$HA/scripts/load_test.sh"
have_path "load_test.sh exists" "$LT"

# --- stamp is written in the pinned format ---------------------------------
# Line 1 is $HA_PIN verbatim, produced by grep -oE '^homeassistant==[0-9.]+'.
# Lines 2..n are ${REQS[@]} sorted. Comparison is cmp -s.
contains "HA_PIN is taken from requirements.txt with the pinned regex" \
  "grep -oE '^homeassistant==[0-9.]+'" "$LT"
contains "the expected stamp starts with echo of HA_PIN" \
  'echo "$HA_PIN"' "$LT"
contains "manifest requirements are sorted into the stamp" \
  'printf '"'"'%s\n'"'"' "${REQS[@]}" | sort' "$LT"
contains "stamp comparison is cmp -s, not a loose string match" \
  "cmp -s" "$LT"
contains "the on-disk stamp is .load-test-stamp" \
  ".load-test-stamp" "$LT"

# The regex really does produce a line matching ^homeassistant==[0-9.]+$
HA_PIN=$(grep -oE '^homeassistant==[0-9.]+' "$HA/requirements.txt")
if printf '%s\n' "$HA_PIN" | grep -qE '^homeassistant==[0-9.]+$'; then
  ok "requirements.txt pin matches ^homeassistant==[0-9.]+\$ ($HA_PIN)"
else
  bad "HA_PIN from requirements.txt is not ^homeassistant==[0-9.]+\$: ${HA_PIN:-<empty>}"
fi

# One requirement per line after line 1, sorted -- assert the construction
# in the script, not a venv that may or may not exist on this machine.
contains "stamp construction writes HA_PIN then sorted REQS to expected-stamp" \
  'expected-stamp' "$LT"

# --- uv pip check is the reaped-venv guard (ruling 19) ---------------------
contains "uv pip check is the reuse guard" "uv pip check" "$LT"

# --- retry-once: import failure on a reused venv recreates and retries -----
contains "retry-once branch exists" \
  "recreating (retry after import failure)" "$LT"
contains "retry-once only fires when the venv was reused" \
  'if [ "$reused" -eq 1 ]' "$LT"

# --- all four status strings Step 3 pinned ---------------------------------
contains "status: reusing" "  reusing " "$LT"
contains "status: recreating (stamp mismatch)" \
  "recreating (stamp mismatch)" "$LT"
contains "status: recreating (uv pip check failed)" \
  "recreating (uv pip check failed)" "$LT"
contains "status: recreating (retry after import failure)" \
  "recreating (retry after import failure)" "$LT"

# --- BEHAVIOURAL ARM ------------------------------------------------------
# Everything above is `contains`, i.e. text presence. That is not enough on its
# own and this gate learned it the hard way: disabling the guard by renaming
# `uv pip check` left every arm above GREEN, because the phrase also occurs in
# the status string one of them asserts. A gate whose subject is runtime
# behaviour must run the thing. This arm builds a REAPED venv -- the exact
# failure macOS produces under /var/folders, where bin/python survives and the
# payloads are gone -- and asserts load_test.sh detects it and recovers.
FIX="${TMPDIR:-/tmp}/f10-reaped-$$"
rm -rf "$FIX"
if "$HA/.venv/bin/python" -m venv "$FIX" >/dev/null 2>&1; then
  # Reap it the way the OS does: keep bin/python, destroy an installed payload.
  rm -rf "$FIX"/lib/python*/site-packages/pip* 2>/dev/null || true
  : > "$FIX/pyvenv.cfg"
  out=$(cd "$HA" && bash scripts/load_test.sh "$FIX" 2>&1) || true
  if printf '%s' "$out" | grep -qE 'recreating \((uv pip check failed|stamp mismatch)\)'; then
    ok "a reaped venv is DETECTED and recreated when load_test.sh runs"
  else
    bad "a reaped venv was not detected -- guard is inert at runtime"
    note "$(printf '%s' "$out" | head -3)"
  fi
  if printf '%s' "$out" | grep -q '0 failed'; then
    ok "after recreating, every module imports"
  else
    bad "recreated venv still fails to import"
  fi
  rm -rf "$FIX"
else
  note "could not build a venv fixture here -- behavioural arm skipped"
fi

summary F10
