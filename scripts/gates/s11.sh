#!/usr/bin/env bash
# S11 — 80% global AND per-file. --cov-fail-under is global-only, so per-file needs coverage json.
source "$(dirname "$0")/_lib.sh"
echo "S11 — coverage at 80%"
J="${COV_JSON:-$HA/coverage.json}"
if [ ! -f "$J" ]; then bad "no coverage.json at $J (run: coverage json -o coverage.json)"; summary S11; exit 1; fi
python3 - "$J" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
tot=d['totals']['percent_covered']
watch=('coordinator.py','sensor.py','switch.py','number.py','select.py','button.py',
       'cover.py','binary_sensor.py','update.py','time.py','config_flow.py')
bad=[(f,round(v['summary']['percent_covered'],1)) for f,v in d['files'].items()
     if any(w in f for w in watch) and v['summary']['percent_covered'] < 80]
print(f"  global: {tot:.1f}%")
for f,p in bad: print(f"  under 80: {f} {p}%")
sys.exit(1 if bad or tot < 80 else 0)
PY
check "80% global and per-file" $?

# S11 also forbids buying coverage with suppressions. Scoped to code we AUTHOR:
# the vendored client is maintained in its own repo and carries four inherited
# `# pragma: no cover`, which vendoring copied rather than this story adding.
added=$(cd "$HA" && git diff pre-merge-1.5.3b5 -- \
          ':(exclude)custom_components/rivian/rivian_client' \
          ':(exclude)tests/client' custom_components/ tests/ \
        | grep -cE '^\+.*(pytest\.mark\.(skip|xfail)|# pragma: no cover)' || true)
if [ "${added:-0}" -eq 0 ]; then
  ok "no skip/xfail/pragma added to our own code"
else
  bad "$added coverage suppression(s) added to our own code"
  (cd "$HA" && git diff pre-merge-1.5.3b5 -- \
     ':(exclude)custom_components/rivian/rivian_client' ':(exclude)tests/client' \
     custom_components/ tests/ \
   | grep -E '^\+.*(pytest\.mark\.(skip|xfail)|# pragma: no cover)' | sed 's/^/      /')
fi

summary S11
