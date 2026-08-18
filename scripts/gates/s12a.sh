#!/usr/bin/env bash
# S12a — devcontainer boots real HA with a seeded, authenticated entry.
source "$(dirname "$0")/_lib.sh"
echo "S12a — devcontainer runs HA"

have_path "seed script exists" "$HA/scripts/seed_config_entry.py"
have_path "seed script has tests" "$HA/tests/test_seed_config_entry.py"

# A floor let requirements.txt, config/.HA_VERSION and the venv sit on three
# different HA versions at once. A .storage seeded by a newer HA is unreadable by
# an older one, so "pre-authenticated" is not reproducible without an exact pin.
if grep -qE '^homeassistant==[0-9]{4}\.[0-9]+\.[0-9]+' "$HA/requirements.txt"; then
  ok "HA version pinned exactly"
  ha_ver=$(grep -oE '^homeassistant==[0-9.]+' "$HA/requirements.txt" | cut -d= -f3)
else
  bad "HA version is floored, not pinned"
  ha_ver=""
fi

# pytest-homeassistant-custom-component pins homeassistant itself, so an unpinned
# floor there silently overrides requirements.txt.
if grep -qE '^pytest-homeassistant-custom-component==' "$HA/requirements_test.txt"; then
  ok "test harness pinned exactly"
else
  bad "pytest-homeassistant-custom-component unpinned — it pins HA and would override the pin above"
fi

# The interpreter has to move with HA: 2026.8.2 requires >= 3.14.2. Three places
# declare it and any one lagging turns CI or the container red.
pyvers=$(
  { grep -oE 'python:1-3\.[0-9]+-' "$HA/.devcontainer/devcontainer.json" | grep -oE '3\.[0-9]+'
    grep -oE 'uv (python install|venv --python) 3\.[0-9]+' "$HA/.github/workflows/test.yaml" | grep -oE '3\.[0-9]+'
  } | sort -u
)
if [ "$(echo "$pyvers" | wc -l | tr -d ' ')" = "1" ] && [ -n "$pyvers" ]; then
  ok "devcontainer and CI agree on Python $pyvers"
else
  bad "Python version disagrees across devcontainer/CI: $(echo "$pyvers" | tr '\n' ' ')"
fi

# The container must install the pins, not just the runtime.
if grep -q 'requirements_test.txt' "$HA/.devcontainer/setup"; then
  ok "devcontainer installs requirements_test.txt"
else
  bad "devcontainer installs only requirements.txt — container cannot run the suite"
fi
if grep -q 'seed_config_entry.py' "$HA/.devcontainer/setup"; then
  ok "devcontainer seeds the config entry"
else
  bad "devcontainer does not seed — the entry needs a password and an OTP to create by hand"
fi

# Secrets discipline, both directions.
if [ -f "$HA/scripts/seed_config_entry.py" ]; then
  absent "seed script inlines no secret value" '(RIVIAN_[A-Z_]+ *= *["'"'"'][^"'"'"']{8,})' "$HA/scripts"
fi
if grep -qE '^/?\.env$' "$HA/.gitignore" && grep -qE '^/?config/$' "$HA/.gitignore"; then
  ok ".env and config/ are both gitignored"
else
  bad "a seeded entry or .env could be committed"
fi

# Positive assertion: the seeded shape actually constructs as a real HA
# ConfigEntry. Grep can only prove the script exists; this proves it works.
if (cd "$HA" && .venv/bin/pytest tests/test_seed_config_entry.py -q --no-cov >/dev/null 2>&1); then
  ok "seeded entry loads as a homeassistant ConfigEntry"
else
  bad "tests/test_seed_config_entry.py fails — the seeded entry would not load"
fi

note "booting HA against the live vehicle is s13 (mode:human): one Parallax"
note "subscription per session token, so a second HA contends with production"
summary S12a
