#!/usr/bin/env bash
# S12a — devcontainer boots real HA.
source "$(dirname "$0")/_lib.sh"
echo "S12a — devcontainer runs HA"
have_path "seed script exists" "$HA/scripts/seed_config_entry.py"
if grep -qE 'homeassistant==' "$HA/requirements.txt"; then ok "HA version pinned"
else bad "HA version unpinned (>=2025.1.0) — a .storage seeded by a newer HA is unreadable by an older one"; fi
if [ -f "$HA/scripts/seed_config_entry.py" ]; then
  absent "seed script inlines no secret value" '(RIVIAN_[A-Z_]+ *= *["'"'"'][^"'"'"']{8,})' "$HA/scripts"
fi
summary S12a
