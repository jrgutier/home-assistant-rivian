# Capability matrix

Capability × available on this vehicle × exposed by this integration.

Three columns, and the third is almost always empty. That is the point: the
integration gates **four** entities on a capability flag and creates everything
else unconditionally, which is deliberate. See "What this table is not" below.

## How to read it

- **featureName** — the string the *server* emits in `supportedFeatures`. This is
  what a gate must match.
- **member** — the `VehicleFeature` enum member in the app. `=` means it is
  identical to the featureName; **19 of 64 are not**, and gating on a member name
  where they differ silently never matches. `—` means the server emits this name
  and the app declares no member for it at all.
- **on this R1T** — present and `AVAILABLE` in
  `tests/fixtures/supported_features_observed.json`, dumped with
  `scripts/dump_supported_features.py`. One 2022 R1T, one account.
- **gates an entity** — the entities `cover.py` or `button.py` will not create
  without this flag.

## What this table is not

**It is not a list of what the vehicle can do**, and nothing may be deleted
because a row is empty. Three separate measurements say the app and the flag list
are both lower bounds:

1. `TONNEAU_CMD` appears nowhere — not in the 64 members, not in this vehicle's
   55 live flags, not in any of the app's 32,941 decompiled files. `cover.py`
   gated the tonneau cover on it, so the cover was never created for anyone.
   Tested on the vehicle: `OPEN_TONNEAU_COVER` was accepted and the cover
   **physically opened**; `CLOSE_TONNEAU_COVER` returned it to closed and locked.
2. Fifteen `vehicleState` fields this integration subscribes to appear in zero
   decompiled files. Three carry live data as of this writing.
3. **Seven** names below are emitted by the server with `—` in the member column:
   `CHARG_CLEAN_NRG`, `CLM_HOLD_AUTO_VENT`, `CONNECT_PLUS`, `PIN_KEY_DRIVE`,
   `PREMIUM_SPEAKER`, `TRIP_ADD_STOP`, `WATCH_GEN1_PAIRING`. App 3.15.0 does not
   declare them.

So the lint in `tests/test_apk_transcription.py` checks a gate string against
**`VehicleFeature` featureNames ∪ the names observed live**, not against the app
alone. It exists to catch a string that matches *nothing anywhere* — the
`TONNEAU_CMD` class of typo — and not to constrain the integration to the app's
vocabulary.

## Out of scope: `switch.py`

`switch.py` applies **no** capability filter at all — zero `supported_features`
references. That is recorded here as a decision rather than left as an oversight:
it is consistent with defaulting to keeping a control, and it is why the lint
covers only `cover.py` and `button.py`. A test fails if `switch.py` ever grows a
gate, so one cannot slide in unchecked.

## The matrix

| featureName | member | on this R1T | gates an entity |
|---|---|:--:|---|
| `ACTIVE_TRIP` | = | — | — |
| `ACTV_USR` | `ACTIVE_USR` | yes | — |
| `AUTONOMY_PLUS` | = | — | — |
| `AUTO_VENT` | = | yes | — |
| `CAR_WASH_MODE` | = | yes | — |
| `CHARG_CLEAN_NRG` | `—` | yes | — |
| `CHARG_DATA_PX` | `CHARGING_SESSION_OVER_PARALLAX` | yes | — |
| `CHARG_NTW_EA` | = | yes | — |
| `CHARG_NTW_IONNA` | = | yes | — |
| `CHARG_PORT_DOOR_COMMAND` | `CHARGE_PORT_DOOR_COMMAND` | yes | cover.charge_port |
| `CHARG_TRIP_TARGET` | `CHARGING_TRIP_TARGET` | yes | — |
| `CLM_HOLD` | = | yes | — |
| `CLM_HOLD_AUTO_VENT` | `—` | yes | — |
| `CONNECT_PLUS` | `—` | yes | — |
| `CONN_SUB` | = | yes | — |
| `ENRG_CLD_WTHR` | `COLD_WEATHER_BAR` | yes | — |
| `ENRG_MONTR_ACTIVE` | `ACTIVE_ENERGY_MONITOR` | yes | — |
| `ENRG_MONTR_PARK` | `PARKED_ENERGY_MONITOR` | yes | — |
| `HEATED_SEATS_THIRD` | = | — | — |
| `HLWN_25` | = | — | — |
| `HLWN_25_G2` | = | — | — |
| `HMAC_TIMEOUT_90S` | = | yes | — |
| `HONK_AND_FLASH_COMMAND` | = | — | — |
| `ICE_RESTART` | = | — | — |
| `INTERIOR_CAMERA` | = | — | — |
| `KEY_FOB_2` | = | — | — |
| `KEY_PAAK` | = | yes | — |
| `LIFTGATE_CMD` | = | — | cover.liftgate |
| `LIVE_CAM` | = | yes | `camera.gear_guard_live` |
| `MOBILE_WHEEL_SWAP` | = | yes | — |
| `MOTION_CAM` | = | yes | `camera.gear_guard_live` |
| `ORPHANED_PHONE_KEY_RECOVERY_HANDLING` | = | — | — |
| `PASSIVE_ENTRY_PROTO_V2` | = | yes | — |
| `PET_COMFORT_CONTROL` | = | — | — |
| `PET_MODE_LOW_TEMP` | `LOWER_PET_MODE_TEMPERATURE` | yes | — |
| `PIN_KEY_DRIVE` | `—` | yes | — |
| `PIN_PROFILE` | = | yes | — |
| `PREMIUM_SPEAKER` | `—` | yes | — |
| `PRIV_PREF` | = | — | — |
| `PVS_BD_CMD` | `PARALLAX_BODY_COMMAND` | yes | — |
| `PVS_COMF_CMD` | `PARALLAX_COMFORT_COMMAND` | yes | — |
| `PVS_ENRG_CMD` | `PARALLAX_ENERGY_COMMAND` | yes | — |
| `PVS_OTA_CMD` | `PARALLAX_OTA_COMMAND` | yes | — |
| `PVS_SEC_CMD` | `PARALLAX_SECURITY_COMMAND` | yes | — |
| `PX_STATE_ALL` | `PARALLAX_VEHICLE_STATE` | — | — |
| `RVA` | = | yes | — |
| `RVA_MEM` | = | yes | — |
| `SAVED_LOCATIONS` | = | yes | — |
| `SCHED_DPRT` | = | yes | — |
| `SCHED_DPRT_3RD_ROW` | = | — | — |
| `SCHED_OTA` | = | yes | — |
| `SD_CHARG_ENDS_AT` | = | yes | — |
| `SIDE_BIN_NXT_ACT` | = | yes | button.open_gear_tunnel_left, button.open_gear_tunnel_right |
| `SMART_CHARG` | = | yes | — |
| `TAILGATE_CMD` | = | yes | button.drop_tailgate |
| `TAILGATE_NXT_ACT` | = | yes | — |
| `TESLA_NACS` | = | yes | — |
| `TRAILER_STATUS` | = | yes | — |
| `TRIP_ADD_STOP` | `—` | yes | — |
| `TRIP_NAV_PX` | = | yes | — |
| `TRIP_PLANNER_TRAILERS` | = | yes | — |
| `TWO_FACTOR_DRIVE` | = | yes | — |
| `VEHICLE_CONNECTIVITY_PARALLAX` | = | yes | — |
| `VIDEO_DOWNLOADING` | `VIDEO_DOWNLOADING_FW_SUPPORT` | yes | — |
| `V_GGVD` | `GEAR_GUARD_VIDEO_DOWNLOADING` | — | — |
| `V_GGVS` | `GEAR_GUARD_STREAMING` | yes | — |
| `V_SATMAP` | = | yes | — |
| `V_SRCH_PLUS` | `SEARCH_PLUS` | yes | — |
| `V_TRIP` | `ACTIVE_TRIP_PLUS` | yes | — |
| `WATCH_GEN1_PAIRING` | `—` | yes | — |
| `WINDOWS_CMD` | = | yes | — |

<!-- 71 rows: 64 VehicleFeature members plus 7 names the server emits that the app does not declare -->
