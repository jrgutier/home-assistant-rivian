# Community fixture provenance

Fixtures in this directory are real Home Assistant integration diagnostics
downloads (`config_entry-rivian-*.json`), attached as **file attachments** to
public GitHub issues on `bretterer/home-assistant-rivian` by vehicle owners
who are not maintainers of this project. They are landed here to evaluate
whether the five R1S-group compatibility-shim gate fields
(`closure_liftgate_next_action`, `closure_liftgate_closed`,
`closure_liftgate_locked`, `seat_third_row_left_heat`,
`seat_third_row_right_heat` — API fields `closureLiftgateNextAction`,
`closureLiftgateClosed`, `closureLiftgateLocked`, `seatThirdRowLeftHeat`,
`seatThirdRowRightHeat`) are reported with usable (non-`INVALID_SENSOR_STATES`)
values by real vehicles.

`INVALID_SENSOR_STATES = {"fault", "signal_not_available", "sna", "undefined"}`
(`custom_components/rivian/const.py:89`).

## VIN handling

**No fixture in this directory ever passed through this sweep with a raw
VIN.** Home Assistant's own diagnostics redaction
(`async_redact_data`/`TO_REDACT`) had already replaced `vin`, vehicle `id`,
`vas`, and `gnssLocation.latitude/longitude` with `**REDACTED**` *before* the
file was ever uploaded to GitHub — the diagnostics download itself is
pre-redacted at capture time. Because of this, the task's requested
"`sha256(salt‖VIN)[:12]` computed before redaction" is **not obtainable from
this source**: we only ever received the already-redacted file, so there is
no raw VIN to salt-hash.

As a substitute distinct-vehicle proof, the digest below is
`sha256(salt ‖ fingerprint)[:12]` where `fingerprint` is a stable JSON
object of non-VIN, non-redacted vehicle metadata that HA's diagnostics
redaction does **not** scrub: `model`, `modelYear`, vehicle nickname
(`name`), `createdAt`, `expectedBuildDate`, `actualGeneralAssemblyDate`.
These are per-vehicle build/registration fields, not shared across vehicles,
so three distinct digests below are sufficient to establish three distinct
vehicles even without a VIN. The salt lives in `.salt` in this directory
(gitignored, never committed).

## Fixtures

| Fixture | Issue | Capture date | Model | source | Gate fields granted (usable) | Vehicle digest | Posted by |
|---|---|---|---|---|---|---|---|
| `issue-171.json` | [bretterer/home-assistant-rivian#171](https://github.com/bretterer/home-assistant-rivian/issues/171) | 2024-08-08 | **R1T** | attached | `closureLiftgateLocked` ("locked"), `seatThirdRowLeftHeat` ("Off"), `seatThirdRowRightHeat` ("Off") — **NOT** `closureLiftgateNextAction` (`SNA`, invalid), **NOT** `closureLiftgateClosed` (`signal_not_available`, invalid) | `dd6a2cc6a7ac` | @TonyMontuna |
| `issue-222.json` | [bretterer/home-assistant-rivian#222](https://github.com/bretterer/home-assistant-rivian/issues/222) | 2025-08-26 | **R1S** (2024, "QUAD") | attached | **all five**: `closureLiftgateNextAction` ("Open_Allowed"), `closureLiftgateClosed` ("closed"), `closureLiftgateLocked` ("unlocked"), `seatThirdRowLeftHeat` ("Off"), `seatThirdRowRightHeat` ("Off") | `2d184e02d16c` | @jkosharek |
| `issue-245.json` | [bretterer/home-assistant-rivian#245](https://github.com/bretterer/home-assistant-rivian/issues/245) | 2026-03-09 | **R1S** (2023, "Monster Truck") | attached | **all five**: `closureLiftgateNextAction` ("Open_Allowed"), `closureLiftgateClosed` ("closed"), `closureLiftgateLocked` ("unlocked"), `seatThirdRowLeftHeat` ("Off"), `seatThirdRowRightHeat` ("Off") | `9bf14e81de4f` | @adamsperber87 |

## Admission bar (per fixture)

1. Genuine HA diagnostics download (not hand-typed) — yes, all three are the
   real `custom_components.rivian.diagnostics` JSON payload shape
   (`home_assistant` / `custom_components` / `data.user` /
   `data.vehicle` / `data.charging` / `data.drivers` / `data.wallbox`).
2. Vehicle model determinable — yes, via `data.user.vehicles[0].vehicle.model`.
3. At least one of the five gate fields with a usable value — yes for all three.
4. Posted by someone other than the repo owner (`bretterer`) or this project
   (`jrgutier`, `tmack8001`, `natekspencer` are the other repo collaborators
   checked) — confirmed; none of TonyMontuna, jkosharek, adamsperber87 are
   collaborators.

**Admission ≠ satisfaction.** `issue-171.json` is admitted on 3/5 fields but
is an **R1T**, not R1S/R2 — the R1T has neither a physical third row nor a
liftgate, so its `usable` values for those three fields are very likely
inert defaults the vehicle never actually exercises, not evidence the field
is meaningful on that body style. It should not be counted toward the R1S
"all five fields, n ≥ 2 distinct vehicles" condition.

`issue-222.json` and `issue-245.json` are both **R1S** and each independently
report **all five** gate fields with usable values, and their digests above
confirm they are two distinct vehicles (different model years, build dates,
and owners). Whether this satisfies the shim's removal condition is a
decision for team-lead/architect review, not this sweep — but the raw
evidence for "R1S, all five fields, n ≥ 2" now exists.

## Search method (for the record of what returned nothing)

Ran against both `bretterer/home-assistant-rivian` (140 issues, all states)
and `bretterer/rivian-python-client` (7 issues, all states) — full issue
bodies + all comments fetched locally and grepped, not relying solely on
GitHub's tokenized full-text search (which does not do literal
phrase/substring matching on snake_case/camelCase field names reliably).

- `gh search issues` queries tried on both repos (returned mostly noise —
  GitHub issue search does not do literal substring matching on
  `closure_liftgate`, `seat_third_row`, etc.): `closure_liftgate`,
  `seat_third_row`, `gear_guard_video`, `attachment diagnostics`,
  `R1S diagnostics`, `download diagnostics R1S`, `diagnostics`, `R1S`,
  `liftgate`, `third row`, `heated seat`, `vehicleState`.
- **Fenced JSON path**: grepped all 147 fetched issue bodies+comments for
  ```` ```json ```` fences and for `closureLiftgate`/`closure_liftgate`/
  `seatThirdRow`/`seat_third_row` (and case variants) directly in text.
  One issue (#264, "expose unmapped vehicle state ... fields") is a feature
  request listing API field names in a Markdown table, not a data dump — no
  fenced JSON payload and no gate-field values. No admissible fenced-JSON
  candidates found in either repo.
- **Attachment path**: grepped all fetched issues for
  `user-attachments/files/...` links. 12 file-attachment links found across
  10 distinct issues in the HA repo (none in the client repo); of those, 3
  matched the `config_entry-rivian-*.json` HA-diagnostics naming convention
  (the other 9 were `.log`/`.txt` debug logs, not diagnostics JSON, and out
  of scope). All 3 diagnostics JSON attachments were downloaded and are the
  3 fixtures landed here.
- `bretterer/rivian-python-client` issues (7 total, all states) returned
  zero hits on every query above and zero file attachments of any kind —
  it does not appear to be a place where owners post gateway payloads or
  diagnostics, contrary to the initial assumption in the task brief.
- No GitHub Discussions exist on either repo (`gh api
  repos/.../discussions` — Discussions feature is disabled on both).
- PRs were not separately searched for diagnostics payloads; PR bodies on
  both repos are overwhelmingly code-change descriptions, and the issue
  sweep already covers 100% of the issues (147/147) where such attachments
  would plausibly be posted in response to a maintainer request for
  diagnostics.

## Redaction verification

Before landing, each of the 3 raw downloaded files (and again after landing,
independently) was grepped for: 17-character VIN-shaped tokens not already
marked `**REDACTED**`, email addresses, raw `lat`/`lon`/`gnssLocation`
numeric values, and `ssid` occurrences. All three came back clean on every
check — HA's own diagnostics redaction had already scrubbed `vin`, vehicle
`id`, `vas`, and `gnssLocation.latitude/longitude` at capture time, before
the owner ever uploaded the file to GitHub. No email addresses, SSIDs, or
raw coordinates were present in any of the three files. No additional
redaction was needed beyond what HA's diagnostics tooling already applied.
