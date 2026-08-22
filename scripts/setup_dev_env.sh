#!/usr/bin/env bash
# Build the development virtualenv at .venv/ -- what pytest, ruff and every gate
# in scripts/gates/ expect to find (resolve_pytest in gates/_lib.sh looks there
# first).
#
# Mirrors .github/workflows/test.yaml step for step -- uv, an explicitly pinned
# 3.14, then requirements_test.txt and nothing else -- because the whole point of
# a local venv is to reproduce CI. Two setup recipes that drift are how "green
# locally, red in CI" starts, which is the same reason the workflow keeps its pins
# in requirements_test.txt rather than in the workflow body.
#
# Idempotent: a .venv already on a qualifying interpreter is kept and its
# requirements re-synced, so re-running is cheap and safe.
set -euo pipefail

cd "$(dirname "$0")/.."

# Pinned, not floored, for the reason the workflow gives: HA's own floor moves
# with its releases, and an environment picking a different minor than CI is how
# a suite goes green in one place and red in the other.
PYTHON_VERSION=3.14

# The floor that actually bites, and the reason `python3 -m venv` does not work
# here. requirements_test.txt pins pytest-homeassistant-custom-component, which
# pins homeassistant==2026.8.2, which declares requires-python >=3.14.2. On any
# older interpreter pip does not error usefully -- it filters the index by
# Requires-Python and reports the newest version that DOES match (2024.3.3 on
# 3.11), which reads as a stale or broken index rather than an interpreter that is
# too old. Bump this with the pins in requirements_test.txt.
MIN_PYTHON='>=3.14.2'

log() { printf '  %s\n' "$*"; }

# --- uv ------------------------------------------------------------------------
# uv is the installer CI uses, and it is also the only one here that can PROVIDE
# a 3.14: the distro ships 3.10-3.13, so an interpreter has to be fetched.
if ! command -v uv >/dev/null 2>&1; then
  log "uv not found — installing it from PyPI"
  python3 -m pip install --quiet --user --upgrade uv
  export PATH="$HOME/.local/bin:$PATH"
fi

# A uv that is merely PRESENT is not enough, and this is the trap worth naming: a
# uv older than the 3.14 release knows only the prereleases, so `uv python install
# 3.14` installs 3.14.0rc2 -- which is BELOW 3.14.2 under PEP 440 and so fails
# HA's floor. The symptom is an unresolvable homeassistant pin, not a word about
# the interpreter. So the check is on the interpreter uv can actually produce, and
# uv is upgraded only when it cannot produce a qualifying one.
ensure_python() {
  uv python install "$PYTHON_VERSION" >/dev/null 2>&1 || true
  # --system: without it uv answers with .venv's own interpreter, which is
  # circular -- a stale .venv would then be judged qualified by itself.
  uv python find --system "$MIN_PYTHON" 2>/dev/null
}

PYTHON_BIN="$(ensure_python || true)"
if [ -z "$PYTHON_BIN" ]; then
  log "no interpreter satisfying $MIN_PYTHON — upgrading uv and retrying"
  # `uv self update` first because it is the supported path, but it fails on an
  # unauthenticated GitHub API rate limit in sandboxed environments; PyPI is the
  # fallback that works there. Either way this runs at most once.
  uv self update >/dev/null 2>&1 || python3 -m pip install --quiet --user --upgrade uv
  hash -r
  PYTHON_BIN="$(ensure_python || true)"
fi

if [ -z "$PYTHON_BIN" ]; then
  echo "FAILED: no CPython $MIN_PYTHON available and uv could not fetch one." >&2
  echo "        homeassistant (pinned in requirements_test.txt) will not install" >&2
  echo "        on anything older, so this is an interpreter problem, NOT a" >&2
  echo "        broken package index." >&2
  exit 1
fi
log "interpreter: $PYTHON_BIN"

# --- venv ----------------------------------------------------------------------
# Rebuild only when the existing .venv is missing or is on an interpreter that no
# longer qualifies. Recreating a good one on every session start would throw away
# the container's warm state for nothing.
if [ -x .venv/bin/python ] \
   && .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info[:3] >= (3, 14, 2) else 1)' 2>/dev/null; then
  log ".venv already on a qualifying interpreter — keeping it"
else
  log "creating .venv on $PYTHON_VERSION"
  rm -rf .venv
  uv venv --python "$PYTHON_BIN" .venv >/dev/null
fi

log "installing requirements_test.txt"
VIRTUAL_ENV="$PWD/.venv" uv pip install --quiet -r requirements_test.txt

# --- proof ---------------------------------------------------------------------
# Assert what the venv EXISTS to provide rather than trusting the installer's exit
# code: every gate that shells out to python fails with ModuleNotFoundError if
# homeassistant is absent, and that failure reads as a finding rather than as an
# environment problem.
.venv/bin/python - <<'PY'
import pytest, ruff  # noqa: F401
import sys
from homeassistant.const import __version__ as ha_version

print(f"  ready: python {'.'.join(map(str, sys.version_info[:3]))}, "
      f"homeassistant {ha_version}")
PY
