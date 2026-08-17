# Ralph progress — vendor-rivian-client-parallax
# PRD: hand-authored (19 stories). Do NOT regenerate: mode:human stories (s03, s08a, s13)
# must never be attempted by the loop, and that constraint lives in prose a generator would ignore.
# Guardrail: --no-deslop is REQUIRED by the approved plan. After s07 the changed-file set includes
# ~8,800 lines of vendored upstream code; ai-slop-cleaner would rewrite it and recreate the exact
# divergence the plan exists to eliminate. It would also break s10's byte-identical golden encoder test.

## iteration 0 — setup (pre-loop, human-assisted)
- Rebuilt home-assistant-rivian/venv: Homebrew python@3.13 is gone (brew ships 3.14 only), leaving a
  dangling interpreter. Rebuilt via `uv python install 3.13` -> cpython-3.13.13 (HA needs >=3.13.2).
- Two pins beyond requirements_test.txt, because `uv pip install` does NOT apply HA's
  package_constraints.txt the way HA does at runtime:
    pycares<5           (5.0.1 dropped ares_query_a_result, which aiodns==3.5.0 still calls)
    habluetooth==5.6.4, bleak-retry-connector==4.4.3, dbus-fast==2.44.3
                        (habluetooth 6.x wants a bleak API that bleak==1.0.1 lacks)
- s01 COMPLETE. Real baseline is 75% (2318 stmts, 589 missing), not the 22% in the committed
  artifacts — that was a nine-file subset run. --cov-fail-under=75 set in pytest.ini.
  Full write-up: home-assistant-rivian/docs/COVERAGE_BASELINE.md
- Discovered: the suite is NOT green. 10 order-dependent failures, all passing in isolation.
  Added story s01b to fix; it blocks s02 and s07.
- Test env resolves HA 2025.10.4 (pinned by pytest-homeassistant-custom-component), not 2025.12.0.
  Key dependency facts re-verified on 2025.10.4 and unchanged.

## learnings for future iterations
- Gates live at scripts/gates/sNN.sh, run from the workspace root, bash not zsh, exit 0 = pass.
- grep here is ugrep: inside `grep -E`, \| is a LITERAL PIPE. Use (a|b).
- grep exits 2 (not 1) on a missing path with empty stdout — an "absent" assertion can pass vacuously.
- zsh eats `:c` in `$TAG:path/to/file`; always quote git revspecs as "${TAG}:path".
- Never write `cmd; check "..." $?` under `set -e` — use the `try` helper in scripts/gates/_lib.sh.

## iteration 1 — s01b COMPLETE (307/307 green)
Gate scripts/gates/s01b.sh: 4/4 PASS, exit 0.

Three distinct defects behind the "10 order-dependent failures", not one:

1. sys.modules pollution — 11 files, 17 assignments, all removed (not scoped).
   Verified unnecessary BEFORE removing: real rivian.exceptions exports all 10 classes the tests
   need, and every mocked VehicleCommand member is a StrEnum whose value == its name, so the mocks
   were exactly equivalent to the real objects.
   test_button also stubbed homeassistant.components.bluetooth, which genuinely failed to import —
   root cause was two missing transitive deps. Installed aiousbwatcher + pyserial instead of mocking.

2. Class-level PropertyMock leak — 4 sites doing
       type(mock_config_entry).options = PropertyMock(...)
   which mutates the SHARED MockConfigEntry class for the whole session. Every later entry.options
   returned the wrong dict, silently skipping the 2FA branch and the disenroll loop in __init__.py.
   Symptom appeared in test_init as "mock called 0 times", far from the cause.
   Fixed with monkeypatch.setattr(..., raising=False) — raising=False is REQUIRED because `options`
   is defined on the parent ConfigEntry, not on MockConfigEntry; teardown then deletes the override
   and re-exposes the parent property.
   NOTE test_config_flow.py:110 uses the same idiom but is SAFE — a spec'd MagicMock gets its own
   subclass (verified: type(a) is type(b) -> False). Do not "fix" it.

3. Stale fixture — test_init.py::mock_vehicle_coordinator never updated when f3e62e3 added
   parallax_coordinator, so __init__.py:110 awaited a plain MagicMock. Two tests failed even in
   isolation for this reason: genuinely broken since that commit, previously masked by (1).

Coverage 75% -> 76% purely from tests now running to completion. Floor ratcheted to 76.

## learnings
- Debug order-dependence by bisecting: for f in tests/*; do pytest $f tests/<victim>.py; done
  then bisect WITHIN the poisoning file to the individual test. Found the culprit in two steps.
- "mock called 0 times" usually means an early-return, not a broken mock. Trace the branch condition.
- ruff format reshapes multi-line calls, which breaks regex-based edits written against the old
  shape. Edit line-based, or format afterwards and re-check.

## next
s02 (auto) — CI onto vendor-client. Then s03 is mode:human — the loop MUST halt there.

## iteration 2 — s02 COMPLETE
Gate scripts/gates/s02.sh: 9/9 PASS, exit 0.

- rivian-python-client/.github/workflows/ci.yaml: trigger extended to vendor-client (was main-only,
  so it never fired on a feature branch), and pytest now reports coverage.
- home-assistant-rivian/.github/workflows/test.yaml: NEW. uv + Python 3.13, the four dependency pins
  the environment needs, ruff, pytest. Triggers on push to main/vendor-client and PRs to
  main/dev/vendor-client — deliberately NOT push-on-dev/dev-*, which is pre-release.yaml's territory.
  Also greps for the two pollution patterns s01b removed, so they cannot come back.
- Lint scoping decision: blocking on tests/ only. custom_components/ has 25 pre-existing ruff errors
  and 5 unformatted files, and s03/s05 are about to rewrite much of that code — cleaning it now would
  only manufacture merge conflicts. Added story s02b (deps: s05) to do the repo-wide pass afterwards
  and flip continue-on-error off. Fixed the single tests/ error (DTZ001, missing tzinfo).

## HALT — next story is s03, mode:human
The loop must not attempt s03. It is the client merge onto upstream 2.1.0's transport:
  - parallax.py is add/add with ZERO common ancestry (ours 22218 bytes, theirs 21668). Resolve by
    taking upstream's file as the base and appending our builder half.
  - rivian.py: port only the ~20 methods with a reachable caller, delete the ~45 without one.
Both are judgement calls with no test oracle — the suites are part of what is being merged, so
"pytest green" cannot distinguish "correctly merged" from "took one side wholesale".
Verify with scripts/gates/s03.sh afterwards; it asserts upstream is a real ancestor plus a
preserved-symbol manifest, which is what catches resolve-by-deletion.

s08a (capture 4 RVM payload fixtures, live vehicle) has NO dependencies and should be batched into
the same supervised session — it unblocks a nine-story autonomous run afterwards.

## iteration 3 — partial s11 (loop otherwise blocked on s03/s08a, both mode:human)
Every remaining story chains through s03 (human) or s08a (live vehicle), so no story was
startable. Advanced the largest piece of s11 that carries ZERO merge-conflict risk instead.

- next_action_states.py: 69% -> 100% (211 stmts, 0 missing). Global 76% -> 78.86%.
  Floor ratcheted 76 -> 78. NOTE 79 fails: the true value is 78.86 and the report rounds up.
- Chosen because it is the only remaining sub-80% module that is OURS-ONLY (upstream has no such
  file; the plan keeps it). Every other gap — coordinator.py 67%, __init__.py 37%,
  config_flow.py 39%, button.py 50%, entity.py 72% — is in code s03/s05 rewrite, which is exactly
  why the plan sequences s11 after them. Deliberately left open; do NOT pre-cover them.
- tests/test_next_action_states.py is invariant-based over all 77 enum members, not example-based.
  Six invariants verified against the implementation before being asserted (round-trip,
  case-insensitivity, open/closed exclusivity, and three name-derived ones: FAULTED / OBSTRUCTED /
  TRAILER). The name-derived assertions are what make it falsifiable: add a new *_FAULTED member,
  forget the is_faulted() tuple, and the suite fails.
- Found and confirmed as NOT bugs: LiftgateNextActionState.OPENING_PAUSE_NOT_ALLOWED and
  WindowsNextActionState.MOVING are not is_opening(). Legitimate naming.
- Zero skips: predicate-specific tests parametrise over the members exposing them rather than
  skipping inside the test body.

s11 remains OPEN — 78.86% global, and the per-file 80% targets are unmet by design.

## STILL HALTED on s03 (mode:human). Nothing autonomous remains.

## iteration 4 — Architect review: s01 APPROVED, s01b APPROVED, s02 REJECTED -> fixed
Reviewer ran all three gates itself, mutation-tested the new enum tests, probed the PropertyMock
claim in the live suite, and ran the suite in reversed + 4 randomized orders. It confirmed:
custom_components/ untouched; zero assertions deleted (all 250 deleted lines are mock scaffolding);
no skips/xfail/pragma anywhere; 951 - 644 = 307 pre-existing tests, none removed.

BLOCKER it caught (real, mine): rivian-python-client/.github/workflows/ci.yaml ran
`pytest --cov=src/rivian`, but pytest-cov is in NEITHER pyproject.toml's dev group NOR poetry.lock
(0 locked packages match). pytest exits 4 "unrecognized arguments" before collecting — I had turned
a green CI job permanently red on main AND vendor-client.
  - Could not fix by adding the dep: poetry itself is broken here, by the SAME removed Homebrew
    python@3.13 that broke the venv, so poetry.lock cannot be regenerated. Adding to pyproject
    without a matching lock makes `poetry install` fail — worse. Reverted the --cov flags instead.
    Client-side coverage belongs with the uv/hatchling migration in s03.
  - Gate hardened: s02.sh no longer greps for the string '--cov' (that grep is exactly what let this
    through). It now asserts flags and dependency AGREE — --cov present requires pytest-cov declared
    and locked. Also strips comment lines first, or an explanatory comment mentioning --cov
    self-triggers the check.

Non-blocking findings, all addressed:
  - requirements_test.txt now carries aiousbwatcher, pyserial, pycares<5, habluetooth==5.6.4,
    bleak-retry-connector==4.4.3, dbus-fast==2.44.3. VERIFIED: a clean venv built from
    requirements_test.txt ALONE gives 812 passed. The CI workflow no longer duplicates the recipe.
  - COVERAGE_BASELINE.md: "Per-file, current" retitled as an at-s01 snapshot with a note that s01b
    moved several rows; "11 files" corrected to 10; the 22% refutation marked as no longer
    independently reproducible (.coverage/htmlcov are gitignored and have been overwritten — the
    substantive baseline still reproduces on demand, the forensic evidence does not).
  - Enum tests: reviewer's mutation harness found 6 survivors. Added 4 invariants (has_obstacle_detected
    iff OBSTACLE, needs_calibration iff CALIBRAT, needs_vehicle_angle_confirmation iff ANGLE — all
    verified 0 violations first — plus a TOTALITY invariant with an explicit NEITHER_OPEN_NOR_CLOSED
    allow-list). Mutation-tested the totality one myself: injecting an unclassified member is now
    KILLED. It was the worst survivor, because mutual exclusivity passes vacuously for a member in
    neither tuple. is_opening/is_closing resist a name invariant (two documented exceptions are real).

State: 951 passed, 0 failed, green in reversed order too. 78.86% global, floor 78.
Gates s01/s01b/s02 all exit 0.

## STILL HALTED — next actionable story is s03 (mode:human). Nothing autonomous remains.
