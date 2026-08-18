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

## s12a — devcontainer on HA 2026.8.2 / Python 3.14

Upgraded to the latest HA rather than pinning to production's 2026.8.1, per the
answer given at the open-questions checkpoint ("Rebuild devcontainer to latest
version").

The jump is larger than it looks: 2026.8.2 requires Python >= 3.14.2, so the
interpreter moved with it in all three places that declare one (requirements.txt,
.devcontainer/devcontainer.json, .github/workflows/test.yaml). s12a's gate now
asserts they agree, because any one of them lagging turns CI or the container red
in a way that reads as a code failure.

Measured cost of ~10 months of HA drift, against the warning that it could be
large: one new test dependency (serialx, imported by homeassistant.components.usb
via bluetooth) and three lines of test hygiene. test_coordinator_base's three
interval tests each left a refresh timer pending; HA 2026.8's verify_cleanup fails
on that and older HA did not check, so they had been leaking one on every run.
Four pins also became unnecessary -- pycares<5, habluetooth==5.6.4,
bleak-retry-connector==4.4.3 and dbus-fast==2.44.3 every one of which now pulls a
package *backwards* under the new resolve.

scripts/seed_config_entry.py writes the entry config_flow would have produced:
data from _async_create_entry, options from validate_vehicle_control. It is
idempotent, keeps entry_id across reseeds so the device and entity registries stay
attached, leaves other domains' entries alone, chmod 600s the file, and never
prints a value. Verified shape-identical to the real production entry.

Not done here, deliberately: booting HA against the live vehicle. That is s13 and
is human-gated, because one Parallax subscription is allowed per session token and
a second HA would contend with the running production integration.

## s12b — release hardening

Both workflows published a bare recursive zip of custom_components/rivian, which
ships whatever is sitting in that directory. pre-release.yaml fires on every push
to dev and dev-*, and what it publishes is what beta users install, so this
mattered more there, not less. Both now use an allow-list and both run
scripts/scan_artifact.sh before publishing -- one definition of "safe to publish"
rather than three copies of a grep.

Two further defects in release.yaml, neither of which anything would have caught:
`sed -i '/version/c\...'` rewrites every line containing the substring "version"
rather than the version key, and `::set-output` was disabled by GitHub in 2023, so
that step had been setting nothing for two years.

scripts/load_test.sh is the check that earns its keep. The suite cannot catch a
missing manifest entry -- its venv carries HA's full test extra, so a module
importing something HA core does not ship still resolves and fails only for users.
Installing exactly what manifest.json declares and importing every module out of
the built zip found button.py importing homeassistant.components.bluetooth at
module scope. That component's requirements belong to the bluetooth integration
and it reaches homeassistant.components.usb, whose aiousbwatcher and serialx are
absent from HA core's metadata, so on any install without the bluetooth
integration the entire button platform -- wake button included -- would have failed
to load. All 1244 tests were green throughout.

Gate note: the first version of s12b's gate reported four failures against a tree
that was already fixed, because it grepped the workflows' raw text and their
comments name the bugs they fixed ("was ::set-output", "was sed -i /version/c").
That is the same self-triggering-comment defect found six times earlier in this
project. scripts/gates/workflow_runs.py now yields the shell a workflow actually
runs, with comments stripped and backslash continuations joined.

Also synced const.VERSION (1.4.2-beta16) to the manifest (1.5.4-beta1). It is
logged at startup next to "Please report issues at", so every bug report was
citing a version that never existed. A test now asserts the two agree.

## s14 — upstream tracking

The story assumed one upstream flow. There are two, and only one is a git merge.

The integration still merges from `upstream/main` normally. Rehearsing that today
returns "Already up to date" -- `HEAD..upstream/main` is empty and the merge base
IS upstream's head, because s05 merged 1.5.3b5 and upstream has not moved. A no-op
merge rehearses nothing, so the merge was replayed from the `pre-merge-1.5.3b5`
tag in a throwaway worktree: 18 files conflicted, all of them now listed in
docs/UPSTREAM_MERGE_REHEARSAL.md, then `merge --abort` and the worktree removed.

The vendored client has no merge path -- that is the part vendoring removed along
with the moving git URL, and nothing had replaced it.
scripts/sync_upstream_client.sh is that path. It fetches
bretterer/rivian-python-client directly into this repo as `client-upstream` rather
than going through the sibling checkout, because that repo is slated for archival
and a process that only works on one laptop is not a process.

Rehearsed against upstream's newest client commit (fb7d7a5). It reports the range
is already vendored, which is the useful answer and validates the mechanism end to
end: the patch reverse-applies against rivian_client/, proving both that the commit
is present and that the -p3 path mapping is correct. Forward-applying the same
patch fails, so the two states are distinguishable -- they need opposite responses
and both fail a naive forward --check.

CLAUDE.md's Dependencies section still presented the git-URL requirement as
current, months after it stopped being true. Rewritten, with the old form kept as
explicitly historical and a note that adding a manifest requirement is not free.

19 of 20 stories now pass. s13 remains, and is mode:human by design.

## s13 — E2E against the real vehicle: five defects the suite could not see

Ran live, per the decision at the open-questions checkpoint. The result justifies
the story existing: 1244 passing unit tests, and the integration did not survive
its first contact with the real gateway.

1. The response envelope was never unwrapped. Every client method returns an
   aiohttp ClientResponse; the base _async_update_data returned it as data. Setup
   died at once with "'HassClientResponse' object has no attribute 'get'". Upstream
   checks status, awaits .json() and returns data["data"][key]; the s05 merge
   dropped it, and nothing failed because the tests mock the api as already
   returning the inner dict -- the wrong boundary. self.key sat unread on four
   coordinators the whole time. This is exactly the failure the plan's own s05
   review checkpoint predicted.
2. VEHICLE_STATE_API_FIELDS is derived from every sensor's field, so the
   wheels_installed sensor added in s09b injected wheelsInstalled into the GraphQL
   subscription. Rivian rejected the whole subscription, which then delivered
   nothing -- no battery, no odometer, no tyre pressures.
3. "Off" was missing from the preconditioning enum, though the decoder documents
   emitting it.
4. INVALID_SENSOR_STATES listed signal_not_available but the vehicle sends SNA.
5. The invalid-state fallback was guarded by `and key in prev_items`, so a field
   seen for the first time leaked its invalid value -- both on the first update and,
   the case that survived the first fix, whenever Parallax had already populated
   other keys.

Final run is clean: 0 errors, 0 tracebacks, 0 rejections, 13 Parallax topics with 0
raw payloads, odometer and all four tyre pressures live.

Not done: the climate hold write. It actuates the vehicle and needs its own
approval; running the read path is not consent to command the car.

All 20 stories now pass.

## s13 — the climate hold write, exercised

Owner approved actuating the vehicle on two conditions: restore steady state, and
stop if anyone is in it. Both honoured.

Occupancy gate before writing: all six closures closed, powerState `ready` (awake,
parked, not `go`). Doors re-checked throughout and never changed.

Round trip through the live subscription: baseline 0 -> write 5 minutes -> 300 ->
write 0 -> 0. Both writes returned SendVehicleOperationSuccess and the change came
back in about three seconds, well inside the one-update threshold. The vehicle was
left exactly as found.

Two things this proves that no offline test could. 5 minutes encodes to exactly 300
seconds on the real vehicle, which validates the hand-rolled varint encoder that
replaced protobuf in s10 -- the golden-bytes tests could only compare it against
the generated code it replaced, not against what Rivian actually accepts. And the
16-raw-byte phone_id (uuid.UUID(vasPhoneId).bytes, not the 36-character string)
resolves and authorises correctly, which is the single detail most likely to be
wrong in that path.

climateHoldStatus stayed 'off' throughout, consistently: the write sets the hold
duration, and storing a duration does not by itself start the hold.
