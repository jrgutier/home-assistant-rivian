#!/usr/bin/env bash
# S1 — real coverage baseline recorded and wired into pytest.ini as the ratchet floor.
source "$(dirname "$0")/_lib.sh"
echo "S1 — coverage baseline"
on_branch "$HA" vendor-client
have_path "docs/COVERAGE_BASELINE.md written" "$HA/docs/COVERAGE_BASELINE.md"
if grep -qE '^\s*--cov-fail-under=[0-9.]+' "$HA/pytest.ini" 2>/dev/null \
   || grep -qE 'cov-fail-under' "$HA/pytest.ini" 2>/dev/null; then
  floor=$(grep -oE 'cov-fail-under=[0-9.]+' "$HA/pytest.ini" | head -1 | cut -d= -f2)
  if awk "BEGIN{exit !($floor > 0)}"; then ok "pytest.ini floor set to $floor (> 0)"
  else bad "pytest.ini floor is $floor — a zero floor is not a ratchet"; fi
else
  bad "pytest.ini has no --cov-fail-under"
fi
note "the committed .coverage/htmlcov disagree with each other; neither is a valid baseline"
summary S1
