"""Energy-related Protocol Buffer messages for Parallax protocol."""

import struct
from typing import Any

from google.protobuf import message as _message


def _encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value & 0x7F)
    return bytes(result)


class ParkedEnergyMonitor(_message.Message):
    """Parked energy consumption monitoring data.

    RVM: energy_edge_compute.graphs.parked_energy_distributions

    Attributes:
        total_energy_kwh: Total energy consumed while parked (kWh)
        climate_kwh: Energy used for climate control (kWh)
        battery_management_kwh: Energy used for battery management (kWh)
        cabin_comfort_kwh: Energy used for cabin comfort features (kWh)
        sentry_mode_kwh: Energy used for sentry/Gear Guard (kWh)
        period_hours: Monitoring period duration (hours)
        avg_power_watts: Average power consumption (watts)
    """

    def __init__(
        self,
        total_energy_kwh: float = 0.0,
        climate_kwh: float = 0.0,
        battery_management_kwh: float = 0.0,
        cabin_comfort_kwh: float = 0.0,
        sentry_mode_kwh: float = 0.0,
        period_hours: int = 0,
        avg_power_watts: float = 0.0,
    ):
        """Initialize ParkedEnergyMonitor message."""
        super().__init__()
        self.total_energy_kwh = total_energy_kwh
        self.climate_kwh = climate_kwh
        self.battery_management_kwh = battery_management_kwh
        self.cabin_comfort_kwh = cabin_comfort_kwh
        self.sentry_mode_kwh = sentry_mode_kwh
        self.period_hours = period_hours
        self.avg_power_watts = avg_power_watts

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "total_energy_kwh": self.total_energy_kwh,
            "climate_kwh": self.climate_kwh,
            "battery_management_kwh": self.battery_management_kwh,
            "cabin_comfort_kwh": self.cabin_comfort_kwh,
            "sentry_mode_kwh": self.sentry_mode_kwh,
            "period_hours": self.period_hours,
            "avg_power_watts": self.avg_power_watts,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.total_energy_kwh:
            output.extend(self._encode_field_value(1, self.total_energy_kwh, 1))
        if self.climate_kwh:
            output.extend(self._encode_field_value(2, self.climate_kwh, 1))
        if self.battery_management_kwh:
            output.extend(self._encode_field_value(3, self.battery_management_kwh, 1))
        if self.cabin_comfort_kwh:
            output.extend(self._encode_field_value(4, self.cabin_comfort_kwh, 1))
        if self.sentry_mode_kwh:
            output.extend(self._encode_field_value(5, self.sentry_mode_kwh, 1))
        if self.period_hours:
            output.extend(self._encode_field_value(6, self.period_hours, 0))
        if self.avg_power_watts:
            output.extend(self._encode_field_value(7, self.avg_power_watts, 1))
        return bytes(output)

    def _encode_field_value(
        self, field_number: int, value: Any, wire_type: int
    ) -> bytes:
        """Encode a field value with tag.

        Args:
            field_number: Protobuf field number
            value: Field value
            wire_type: Wire type (0=varint, 1=64-bit, 2=length-delimited, 5=32-bit)

        Returns:
            Encoded field bytes
        """
        tag = (field_number << 3) | wire_type
        tag_bytes = _encode_varint(tag)

        if wire_type == 0:  # Varint
            return tag_bytes + _encode_varint(value)
        elif wire_type == 1:  # 64-bit (double)
            return tag_bytes + struct.pack("<d", value)
        return tag_bytes
