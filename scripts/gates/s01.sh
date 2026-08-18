#!/usr/bin/env bash
# S1 — real coverage baseline recorded and wired into pytest.ini as the ratchet floor.
source "$(dirname "$0")/_lib.sh"
echo "S1 — coverage baseline"
on_branch "$HA" vendor-client
have_path "docs/COVERAGE_BASELINE.md written" "$HA/docs/COVERAGE_BASELINE.md"
# The ratchet moved in s11. --cov-fail-under is a single global number and cannot
# express two populations -- the integration code we own and the vendored client --
# with different obligations, so pytest.ini deliberately does not set it and
# scripts/check_coverage.py enforces a floor for each. This gate asserted the old
# mechanism and went red the moment s11 landed, which is how a stale gate looks.
if [ -x "$HA/scripts/check_coverage.py" ] || [ -f "$HA/scripts/check_coverage.py" ]; then
  ok "scripts/check_coverage.py is the ratchet"
  int_floor=$(grep -oE 'INTEGRATION_FLOOR *= *[0-9.]+' "$HA/scripts/check_coverage.py" | grep -oE '[0-9.]+$')
  cli_floor=$(grep -oE 'CLIENT_FLOOR *= *[0-9.]+' "$HA/scripts/check_coverage.py" | grep -oE '[0-9.]+$')
  for pair in "integration:$int_floor" "client:$cli_floor"; do
    name=${pair%%:*}; val=${pair#*:}
    if [ -n "$val" ] && awk "BEGIN{exit !($val > 0)}"; then ok "$name floor $val (> 0)"
    else bad "$name floor is '${val:-unset}' — a zero or missing floor is not a ratchet"; fi
  done
  # A floor is only a ratchet if it is actually met right now.
  if (cd "$HA" && .venv/bin/python scripts/check_coverage.py >/dev/null 2>&1); then
    ok "both floors currently met"
  else
    bad "check_coverage.py does not pass against the current coverage.json"
  fi
else
  bad "no scripts/check_coverage.py and no --cov-fail-under — nothing ratchets"
fi
note "the committed .coverage/htmlcov disagree with each other; neither is a valid baseline"
summary S1
