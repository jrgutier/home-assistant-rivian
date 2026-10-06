"""The bytes sent to the vehicle are the bytes the hand-rolled encoders produced.

`fixtures/parallax_golden/send_path.json` was recorded from the hand-rolled
`proto/vehicle_operation.py` and `encode_climate_hold_setting` before s49 moved
both onto generated protobuf classes (`scripts/record_parallax_golden.py`).

A decoder that drifts shows a wrong sensor. An encoder that drifts sends the
vehicle a different command, so this is compared byte for byte, including the
rows a generated class gets wrong by default: the hand encoder omits a scalar at
its default but emits EVERY submessage, even an empty one (`0a00`, `2a00`).
"""

from __future__ import annotations

from datetime import datetime
import json
import pathlib
from typing import Any

import pytest

from custom_components.rivian.rivian_client import parallax
from custom_components.rivian.rivian_client.proto import vehicle_operation as vo

CASES: list[dict[str, Any]] = json.loads(
    (
        pathlib.Path(__file__).parent
        / "fixtures"
        / "parallax_golden"
        / "send_path.json"
    ).read_text()
)["cases"]


def _cases(call: str) -> list[Any]:
    found = [
        pytest.param(c, id=str(c["args"])[:60]) for c in CASES if c["call"] == call
    ]
    assert found, f"no recorded cases for {call}"
    return found


@pytest.mark.parametrize("case", _cases("encode_climate_hold_setting"))
def test_climate_hold_payload(case: dict[str, Any]) -> None:
    assert parallax.encode_climate_hold_setting(*case["args"]).hex() == case["hex"]


def test_climate_hold_rejects_a_negative_duration() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        parallax.encode_climate_hold_setting(-1)


@pytest.mark.parametrize("case", _cases("build_climate_hold_command"))
def test_climate_hold_command(case: dict[str, Any]) -> None:
    command = parallax.build_climate_hold_command(*case["args"])
    assert command.payload_b64 == case["payload_b64"]
    assert command.rvm == parallax.RVMType.CLIMATE_HOLD_SETTING


@pytest.mark.parametrize("case", _cases("VehicleOperationRequest"))
def test_operation_envelope(case: dict[str, Any]) -> None:
    version, phone, request_id, rvm, op_type, op_id, payload, stamp = case["args"]
    request = vo.VehicleOperationRequest(
        metadata=vo.Metadata(
            phone_info=vo.PhoneInfo(version=version, phone_id=bytes.fromhex(phone)),
            request_id=request_id,
        ),
        operation=vo.Operation(
            rvm_type=rvm,
            operation_type=op_type,
            operation_id=bytes.fromhex(op_id),
            payload=bytes.fromhex(payload),
            timestamp=vo.Timestamp(*stamp),
        ),
    )
    assert request.SerializeToString().hex() == case["hex"]


@pytest.mark.parametrize("cls", ["Timestamp", "PhoneInfo", "Metadata"])
def test_default_constructed_message(cls: str) -> None:
    (case,) = [c for c in CASES if c["call"] == f"{cls}()"]
    assert getattr(vo, cls)().SerializeToString().hex() == case["hex"]


@pytest.mark.parametrize("case", _cases("Timestamp.from_datetime"))
def test_timestamp_from_datetime(case: dict[str, Any]) -> None:
    """The nanos arithmetic is the encoder's own and is float-rounded.

    google.protobuf's Timestamp.FromDatetime computes nanos exactly and gives a
    different last digit for some moments, which would change the bytes.
    """
    stamp = vo.Timestamp.from_datetime(datetime.fromisoformat(case["args"][0]))
    assert (stamp.seconds, stamp.nanos) == (case["seconds"], case["nanos"])
    assert stamp.SerializeToString().hex() == case["hex"]
    assert stamp.ToDatetime().isoformat() == case["roundtrip"]


def test_mutating_a_message_after_construction_changes_its_bytes() -> None:
    """The classes are plain attribute holders; callers may set fields late."""
    operation = vo.Operation(
        rvm_type="a.b.c", operation_id=bytes(16), timestamp=vo.Timestamp(1, 0)
    )
    before = operation.SerializeToString()
    operation.payload = b"\x08\x01"
    after = operation.SerializeToString()
    assert after != before
    assert b"\x22\x02\x08\x01" in after
