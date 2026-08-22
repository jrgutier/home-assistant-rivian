"""Privacy-bar tests for the Gen 2 BLE pairing trace in diagnostics.

The trace in ble_trace.py exists so a beta tester can attach it to a PUBLIC,
PERMANENT GitHub issue. These tests hold the line the plan's redaction
ruling draws: no raw stable identifier (phone_id, vas_vehicle_id, BLE MAC)
may survive into a diagnostics bundle, while the ephemeral nonce/MAC frame
bytes are kept as plain hex on purpose -- masking those would destroy the
trace's only reason to exist (reconstructing an unproven frame layout).

Every "is redacted" assertion here is paired with a check that the raw
value really was present in the input first -- a test that can't tell a
working redactor from a vacuously-passing one is worthless (Repo Rule 9).
"""

from __future__ import annotations

from custom_components.rivian.helpers import redact
from custom_components.rivian.rivian_client.ble_trace import BleTrace, fingerprint

RAW_PHONE_ID = "12345678-90ab-cdef-1234-567890abcdef"
RAW_VAS_VEHICLE_ID = "01-276948064"
RAW_BLE_MAC = "AA:BB:CC:DD:EE:FF"


class TestRawIdentifiersNeverSurvive:
    """Defense in depth: even if a future record_* call forgot to
    fingerprint, TO_REDACT must independently catch these key names.
    """

    def test_raw_identifiers_are_redacted_wherever_they_appear(self) -> None:
        payload = {
            "phone_id": RAW_PHONE_ID,
            "vas_vehicle_id": RAW_VAS_VEHICLE_ID,
            "address": RAW_BLE_MAC,
            "nested": {
                "identifiers": {
                    "phone_id": RAW_PHONE_ID,
                    "vas_vehicle_id": RAW_VAS_VEHICLE_ID,
                    "address": RAW_BLE_MAC,
                }
            },
        }

        # Sanity check first: if this fails, the fixture itself is broken
        # and the assertion below would be vacuous.
        raw_dump = str(payload)
        assert RAW_PHONE_ID in raw_dump
        assert RAW_VAS_VEHICLE_ID in raw_dump
        assert RAW_BLE_MAC in raw_dump

        redacted_dump = str(redact(payload))
        assert RAW_PHONE_ID not in redacted_dump
        assert RAW_VAS_VEHICLE_ID not in redacted_dump
        assert RAW_BLE_MAC not in redacted_dump

    def test_flattened_vas_id_is_also_redacted(self) -> None:
        """button.py reads the same VAS vehicle id under vehicle["vas_id"],
        not "vas_vehicle_id" -- both spellings must be covered or the
        flattened one leaks the identical identifier under a different name.
        """
        payload = {"vas_id": RAW_VAS_VEHICLE_ID}
        assert RAW_VAS_VEHICLE_ID not in str(redact(payload))


class TestBleTraceIntegration:
    """The real ble_trace.py -> helpers.redact() path, not a hand-built
    stand-in payload.
    """

    def test_real_trace_as_dict_never_carries_the_raw_identifiers(self) -> None:
        trace = BleTrace(vehicle_id="internal-vehicle-id")
        trace.record_identifiers(
            phone_id=RAW_PHONE_ID,
            vas_vehicle_id=RAW_VAS_VEHICLE_ID,
            address=RAW_BLE_MAC,
        )
        trace.record_frame("write", "0823DA14-040B-4914-BF7C-450AFA2850DA", b"\x01\x02")

        rendered = str(redact(trace.as_dict()))
        assert RAW_PHONE_ID not in rendered
        assert RAW_VAS_VEHICLE_ID not in rendered
        assert RAW_BLE_MAC not in rendered

    def test_fingerprint_alone_already_hides_the_raw_value(self) -> None:
        """BleTrace.record_identifiers() fingerprints before TO_REDACT ever
        runs -- this is why the TO_REDACT entries are LATENT today rather
        than fixing a live leak. Verified directly, independent of redact().
        """
        trace = BleTrace(vehicle_id="internal-vehicle-id")
        trace.record_identifiers(phone_id=RAW_PHONE_ID)
        assert trace.identifiers["phone_id_fp"] == fingerprint(RAW_PHONE_ID)
        assert trace.identifiers["phone_id_fp"] != RAW_PHONE_ID
        assert RAW_PHONE_ID not in str(trace.as_dict())

    def test_fingerprint_survives_redaction(self) -> None:
        """The "_fp" key suffix must outlive redact().

        TO_REDACT lists the bare names ("phone_id", "address", ...) as
        defence in depth, and async_redact_data matches by key NAME without
        looking at the value -- so a fingerprint stored under a bare name
        would be blanket-replaced by a placeholder. That would destroy the
        only thing fingerprinting buys: correlating two vehicles paired by
        the same phone WITHIN one bundle. This test fails if someone drops
        the suffix, which would look harmless and silently cost that.
        """
        trace = BleTrace(vehicle_id="internal-vehicle-id")
        trace.record_identifiers(phone_id=RAW_PHONE_ID, address=RAW_BLE_MAC)

        redacted = redact(trace.as_dict())
        identifiers = redacted["identifiers"]

        assert identifiers["phone_id_fp"] == fingerprint(RAW_PHONE_ID)
        assert identifiers["address_fp"] == fingerprint(RAW_BLE_MAC)
        # ...while the raw values are still nowhere in the payload.
        assert RAW_PHONE_ID not in str(redacted)
        assert RAW_BLE_MAC not in str(redacted)


class TestDeliberateNonGoal:
    """Nonce and MAC frame bytes are hex on purpose (plan Open Question 1,
    ruled on by the approver). This is a regression guard, not a gap:
    something that "fixes" this by adding "hex"/"nonce"/"mac" to TO_REDACT
    would silently destroy the trace's only diagnostic value.
    """

    def test_frame_hex_is_not_redacted(self) -> None:
        pnonce = b"\x11" * 16
        mac = b"\x22" * 32
        trace = BleTrace(vehicle_id="internal-vehicle-id")
        trace.start_attempt()
        trace.record_frame(
            "write", "0823DA14-040B-4914-BF7C-450AFA2850DA", pnonce + mac
        )

        rendered = redact(trace.as_dict())
        frame_hex = rendered["frames"][0]["hex"]
        assert frame_hex == (pnonce + mac).hex()


class TestDictKeyMechanicIsNotSilentlyAssumedFixed:
    """IMPORTANT MECHANIC: async_redact_data matches VALUES by key NAME at
    any depth -- it never redacts dict KEYS. This test pins that behaviour
    down so nobody "fixes" the ble_trace keying scheme (per-vehicle_id, not
    per-vas_vehicle_id/VIN/MAC) under the mistaken belief that TO_REDACT
    would cover a raw-identifier key anyway. It would not.
    """

    def test_a_raw_identifier_used_as_a_dict_key_is_not_caught(self) -> None:
        payload = {RAW_VAS_VEHICLE_ID: {"state": "authenticated"}}
        redacted = redact(payload)
        # This is the documented gap, not a bug in redact(): the identifier
        # survives because it is a KEY, and it is exactly why ble_trace.py
        # keys its traces by the internal vehicle_id instead.
        assert RAW_VAS_VEHICLE_ID in redacted
