# Coverage baseline — story S1

Measured 2026-08-16 on a freshly rebuilt environment. This supersedes the committed
`.coverage` / `htmlcov/` artifacts, which are **not** a valid baseline.

## Headline

| Metric | Value |
|---|---|
| Statements | 2318 |
| Missing | 490 |
| **Global coverage** | **78.86%** (75% at s01, 76% after s01b) |
| Tests collected | 812 |
| Passing | **812 — all of them** |
| Failing | **0** — fixed in story s01b |
| Ratchet floor now set in `pytest.ini` | `--cov-fail-under=78` (79 fails: the true value is 78.86, which the report rounds up) |

Target remains **80% global and per-file**, closed in story S11 / Phase 4b.
The gap is ~5 points globally, not the ~58 the stale artifact implied.

## The 22% figure was a subset-run artifact — confirmed, and refuted

The committed report showed 22% with 14 modules at 0%. Two competing explanations were
on the table: *import-before-coverage-start*, or *a partial run*. The partial-run
explanation is correct, and the earlier hypothesis is disproven:

- `pytest.ini:8-10` puts `--cov=custom_components.rivian` in `addopts`, so pytest-cov
  starts the tracer at plugin init, before collection. Import-before-coverage-start is
  therefore impossible under this configuration.
- Running the **full** suite puts every one of those 14 modules above 0%. `sensor.py`,
  reported at 0/102, measures **100%**. `binary_sensor.py`, `climate.py`,
  `device_tracker.py`, `diagnostics.py`, `image.py`, `lock.py`, `notify.py` and
  `recorder.py` are all at 100%.
- Collection alone (`--collect-only`) already yields 38%, because importing a module
  covers its module-level statements.

The old `.coverage` DB held line data for only nine files — exactly the modules imported
by nine of the 22 test files. It was one partial invocation, not a measurement.

> **This particular refutation is no longer independently reproducible.** `.coverage` and
> `htmlcov/` are gitignored (`.gitignore:40,43`), never committed — so "the committed
> artifacts", used in earlier notes and in `prd.json`, was always loose wording. Both have
> since been overwritten by this session's runs and now show the current numbers. The
> *substantive* claim — the real baseline — reproduces on demand from a clean venv; the
> forensic evidence for the 22% figure specifically does not survive. Recorded here so the
> claim is not mistaken for something still checkable.

## Per-file — snapshot taken AT s01 (pre-s01b, pre-s11)

Retained as the historical baseline. These numbers are **stale by design** — s01b and the
partial s11 work moved several of them (e.g. `__init__.py` 37% -> 52%, `coordinator.py`
67% -> 69%, `next_action_states.py` 69% -> 100%), because fixing the 10 failures let more
code execute. Re-measure before using this as a work list:
`pytest -q && coverage report --show-missing`.

Below the 80% target at the time of s01:

| Module | Stmts | Miss | Cover |
|---|---:|---:|---:|
| `__init__.py` | 174 | 110 | 37% |
| `config_flow.py` | 159 | 97 | 39% |
| `button.py` | 84 | 42 | 50% |
| `coordinator.py` | 651 | 213 | 67% |
| `entity.py` | 123 | 35 | 72% |
| `const.py` | 52 | 11 | 79% |

At or above target: `binary_sensor` 100%, `climate` 100%, `data_classes` 100%,
`device_tracker` 100%, `diagnostics` 100%, `image` 100%, `lock` 100%, `notify` 100%,
`recorder` 100%, `sensor` 100%, `cover` 98%, `select` 98%, `number` 94%, `switch` 93%,
`update` 93%, `helpers` 93%.

`coordinator.py` is the dominant gap in absolute terms: 213 of the missing
statements, 36% of the total shortfall, in the file S6a/S6b also refactor.

## The suite WAS not green: 10 order-dependent failures — RESOLVED in s01b

**These were test-infrastructure defects, not product bugs.** Every one passed in
isolation and failed in a full run. Resolved — see the s01b section at the end.

```
tests/test_coordinator_base.py  5 failures
tests/test_init.py              3 failures
tests/test_update.py            2 failures
```

Mechanism — several test modules permanently replace the client in `sys.modules` at
**import time**, with no teardown:

```
tests/test_button.py:19-21,30-31   sys.modules["homeassistant.components.bluetooth"], ["home_assistant_bluetooth"], ["bleak"], ["rivian"], ["rivian.ble"]
tests/test_select.py:23            sys.modules["rivian"]
tests/test_update.py:20-21         sys.modules["rivian"], ["rivian.exceptions"]
tests/test_coordinator_base.py:25  sys.modules["rivian.exceptions"]
tests/test_lock.py:15              sys.modules["rivian"]
```

`test_coordinator_base.py` builds a careful mock whose attributes are the *real*
exception classes. `test_update.py` installs a bare `Mock()` whose attributes are
auto-Mocks. Collection is alphabetical, so `test_update` imports last and wins, and
`pytest.raises(RivianApiRateLimitError)` then receives a Mock:

```
TypeError: expected exception must be a BaseException type, not 'Mock'
```

Reproduce:

```bash
pytest tests/test_coordinator_base.py                          # 18 passed
pytest tests/test_update.py tests/test_coordinator_base.py     # 5 failed
```

### Why this matters beyond the baseline

1. **It will break silently at S7.** After vendoring, the integration imports
   `custom_components.rivian.rivian_client`, so `sys.modules["rivian"] = Mock()` will no
   longer intercept anything. These stubs stop working the moment the rename lands.
2. **It makes an autonomous loop unstable.** Order-dependent failures mean a story's gate
   can pass or fail depending on what ran before it — the loop will thrash or, worse,
   record a false pass.
3. It is why the suite cannot currently be used as the merge oracle that S3/S5 would want.

**Recommendation:** fix this before S7 — replace the module-level `sys.modules`
assignments with fixture-scoped `patch.dict(sys.modules, ...)` that tears down. It is a
contained change across five test files and it unblocks a trustworthy gate everywhere
downstream.

## Environment

The previously checked-in `venv/` was unusable: built from Homebrew `python@3.13`, which
brew has since replaced with `python@3.14`, leaving a dangling interpreter symlink. It was
rebuilt with `uv`:

```bash
uv python install 3.13                 # cpython-3.13.13, satisfies HA's >=3.13.2
uv venv --python 3.13 venv
VIRTUAL_ENV=$PWD/venv uv pip install -r requirements_test.txt
VIRTUAL_ENV=$PWD/venv uv pip install 'pycares<5' \
    'habluetooth==5.6.4' 'bleak-retry-connector==4.4.3' 'dbus-fast==2.44.3'
```

Two pins were needed because `uv pip install` does **not** apply HA's
`package_constraints.txt` the way HA does at runtime:

- `pycares` resolved to 5.0.1, which dropped `ares_query_a_result`; `aiodns==3.5.0` still
  references it. HA pins `aiodns` but not `pycares`.
- `habluetooth` resolved to 6.1.0 against HA's 5.6.4, and 6.x expects a bleak API that
  `bleak==1.0.1` does not expose (`ImportError: cannot import name 'BleakBackend'`).

That second one is a live instance of the dependency thesis in the plan: the client
declares `bleak>=0.21` with no ceiling, and an unconstrained resolve lands somewhere HA
cannot run. Story S4 gives it an honest bound.

Resolved HA version in the test env is **2025.10.4**, pinned transitively by
`pytest-homeassistant-custom-component` — not the 2025.12.0 the plan's dependency section
cites. The plan's conclusions hold on both: on 2025.10.4, `gql<4.0.0` (line 226),
`protobuf==6.32.0` (148) and `bleak==1.0.1` (24) are all *constraints* with zero
`Requires-Dist` entries, while `aiohttp` and `cryptography` are genuine core dependencies.


---

## s01b resolution (2026-08-16)

All 307 tests pass in a full run. Two distinct defects, not one:

**1. `sys.modules` pollution (10 files, 17 assignments).** Each test module permanently replaced
the client at import time with no teardown. Removed entirely rather than scoped — the mocks were
legacy scaffolding. Verified unnecessary first: the real `rivian.exceptions` exports all ten
classes the tests need, and every mocked `VehicleCommand` member is a `StrEnum` whose value equals
its name, so the mocks were exactly equivalent to the real objects.

`test_button.py` additionally stubbed `homeassistant.components.bluetooth`, which genuinely failed
to import. Root cause was two missing transitive dependencies, now installed rather than mocked:
`aiousbwatcher` and `pyserial`.

**2. Class-level `PropertyMock` leak (4 sites).** `type(mock_config_entry).options = PropertyMock(...)`
mutates the shared `MockConfigEntry` class for the entire session, so every later `entry.options`
returned the wrong dict. That silently skipped the 2FA branch and the disenroll loop in
`__init__.py`, producing "mock called 0 times" failures in `test_init.py` far from the cause.
Replaced with `monkeypatch.setattr(..., raising=False)`, which restores on teardown.
(`test_config_flow.py:110` uses the same idiom but is safe — a spec'd `MagicMock` gets its own
subclass, verified.)

**3. A stale fixture.** `test_init.py::mock_vehicle_coordinator` was never updated when `f3e62e3`
added `parallax_coordinator`, so `__init__.py:110` awaited a plain `MagicMock`. Two tests failed in
isolation for this reason — genuinely broken since that commit, previously masked.

Coverage rose 75% → 76% purely from tests that now execute to completion.


---

## Partial s11 progress (2026-08-16)

`next_action_states.py`: **69% -> 100%** (211 statements, 0 missing). Global **76% -> 78.86%**.

Chosen deliberately as the only remaining low-coverage module that is **ours-only** — upstream has
no such file, and the plan keeps it — so the tests cannot be invalidated by the s03/s05 merges.
Every other module below target (`coordinator.py` 67%, `__init__.py` 37%, `config_flow.py` 39%,
`button.py` 50%, `entity.py` 72%) is rewritten by those merges, which is why s11 is sequenced after
them and the rest of the gap is intentionally left open.

The tests are written as **invariants over all 77 enum members**, not hand-picked examples, because
the failure mode here is silent misclassification. Six invariants were verified against the
implementation before being asserted:

- `from_api_value(member.value) is member` — catches duplicate values, which `Enum` silently aliases
- case-insensitive parsing (Rivian has shipped mixed casing)
- `is_open()` and `is_closed()` mutually exclusive — both are hand-maintained tuples
- `is_faulted()` true iff `FAULTED` in the member name
- `is_obstructed()` true iff `OBSTRUCTED` in the member name
- `has_trailer_detected()` true iff `TRAILER` in the member name

The name-derived ones are the point: add a new `*_FAULTED` member, forget the `is_faulted()` tuple,
and the suite fails. A test that merely called each predicate and asserted a bool would pass forever
and is exactly the coverage-theatre pre-mortem S3 warns about.

Two `is_opening` exceptions were found and confirmed legitimate rather than bugs:
`LiftgateNextActionState.OPENING_PAUSE_NOT_ALLOWED` and `WindowsNextActionState.MOVING` are not
"opening". No skips — predicate-specific tests parametrise over the members that expose them.
