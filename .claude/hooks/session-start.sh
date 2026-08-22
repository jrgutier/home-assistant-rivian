#!/usr/bin/env bash
# SessionStart hook: build .venv/ before the session begins, so a web session can
# run pytest, ruff and the gates in scripts/gates/ on its first turn.
#
# Without this a remote session has no usable environment at all, and the failure
# is actively misleading: the distro ships CPython 3.10-3.13, homeassistant
# (pinned in requirements_test.txt) requires >=3.14.2, and pip responds to a
# too-old interpreter by filtering the index and offering a two-year-old release.
# That looks exactly like a stale package index, so the time goes into the wrong
# problem. scripts/setup_dev_env.sh carries the actual fix and the full
# explanation.
#
# Synchronous on purpose: an async hook lets the first turn start before the venv
# exists, and a session that reaches for pytest a second too early gets a
# ModuleNotFoundError that reads as a code failure.
set -euo pipefail

# Local checkouts are left alone -- a developer's environment is theirs, and this
# would rebuild it out from under them. Run scripts/setup_dev_env.sh by hand for
# the same result.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

exec bash "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}/scripts/setup_dev_env.sh"
