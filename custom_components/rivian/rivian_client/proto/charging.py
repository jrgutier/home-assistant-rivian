"""Charging-related Protocol Buffer messages for Parallax protocol."""

import struct
from typing import Any

from google.protobuf import message as _message

from .base import SessionCost, TimeOfDay, _encode_varint


class ChargingSessionLiveData(_message.Message):
    """Live charging session data.

    Based on protobuf message C19106b from Android app analysis.
    RVM: energy_edge_compute.graphs.charge_session_breakdown

    Attributes:
        total_kwh: Total energy delivered (kWh)
        pack_kwh: Energy to battery pack (kWh)
        thermal_kwh: Thermal management energy (kWh)
        outlets_kwh: Energy to outlets/accessories (kWh)
        system_kwh: Vehicle system energy (kWh)
        session_duration_mins: Session duration (minutes)
        time_remaining_mins: Estimated time remaining (minutes)
        range_added_kms: Range added (kilometers)
        current_power: Current charging power (kW)
        current_range_per_hour: Current range gain rate (km/h)
        session_cost: Session cost
        is_free_session: Whether session is free
        charging_state: Charging state (0=idle, 1=charging, 2=complete)
    """

    def __init__(
        self,
        total_kwh: float = 0.0,
        pack_kwh: float = 0.0,
        thermal_kwh: float = 0.0,
        outlets_kwh: float = 0.0,
        system_kwh: float = 0.0,
        session_duration_mins: int = 0,
        time_remaining_mins: int = 0,
        range_added_kms: int = 0,
        current_power: float = 0.0,
        current_range_per_hour: int = 0,
        session_cost: SessionCost | None = None,
        is_free_session: bool = False,
        charging_state: int = 0,
    ):
        """Initialize ChargingSessionLiveData message."""
        super().__init__()
        self.total_kwh = total_kwh
        self.pack_kwh = pack_kwh
        self.thermal_kwh = thermal_kwh
        self.outlets_kwh = outlets_kwh
        self.system_kwh = system_kwh
        self.session_duration_mins = session_duration_mins
        self.time_remaining_mins = time_remaining_mins
        self.range_added_kms = range_added_kms
        self.current_power = current_power
        self.current_range_per_hour = current_range_per_hour
        self.session_cost = session_cost or SessionCost()
        self.is_free_session = is_free_session
        self.charging_state = charging_state

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "total_kwh": self.total_kwh,
            "pack_kwh": self.pack_kwh,
            "thermal_kwh": self.thermal_kwh,
            "outlets_kwh": self.outlets_kwh,
            "system_kwh": self.system_kwh,
            "session_duration_mins": self.session_duration_mins,
            "time_remaining_mins": self.time_remaining_mins,
            "range_added_kms": self.range_added_kms,
            "current_power": self.current_power,
            "current_range_per_hour": self.current_range_per_hour,
            "session_cost": self.session_cost.to_dict() if self.session_cost else None,
            "is_free_session": self.is_free_session,
            "charging_state": self.charging_state,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.total_kwh:
            output.extend(self._encode_field_value(1, self.total_kwh, 1))
        if self.pack_kwh:
            output.extend(self._encode_field_value(2, self.pack_kwh, 1))
        if self.thermal_kwh:
            output.extend(self._encode_field_value(3, self.thermal_kwh, 1))
        if self.outlets_kwh:
            output.extend(self._encode_field_value(4, self.outlets_kwh, 1))
        if self.system_kwh:
            output.extend(self._encode_field_value(5, self.system_kwh, 1))
        if self.session_duration_mins:
            output.extend(self._encode_field_value(6, self.session_duration_mins, 0))
        if self.time_remaining_mins:
            output.extend(self._encode_field_value(7, self.time_remaining_mins, 0))
        if self.range_added_kms:
            output.extend(self._encode_field_value(8, self.range_added_kms, 0))
        if self.current_power:
            output.extend(self._encode_field_value(9, self.current_power, 1))
        if self.current_range_per_hour:
            output.extend(self._encode_field_value(10, self.current_range_per_hour, 0))
        if self.session_cost:
            output.extend(self._encode_field_value(11, self.session_cost, 2))
        if self.is_free_session:
            output.extend(
                self._encode_field_value(12, 1 if self.is_free_session else 0, 0)
            )
        if self.charging_state:
            output.extend(self._encode_field_value(13, self.charging_state, 0))
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
        elif wire_type == 2:  # Length-delimited (embedded message)
            if isinstance(value, SessionCost):
                value_bytes = value.SerializeToString()
            else:
                value_bytes = value
            return tag_bytes + _encode_varint(len(value_bytes)) + value_bytes
        return tag_bytes


class ChargingSessionChartData(_message.Message):
    """Historical charging session data for charts.

    RVM: energy_edge_compute.graphs.charging_graph_global

    Attributes:
        session_id: Unique session identifier
        timestamps: Unix timestamps for chart points
        power_values: Power (kW) at each timestamp
        soc_values: State of charge (%) at each timestamp
        voltage_values: Voltage at each timestamp
        current_values: Current (A) at each timestamp
        total_energy_kwh: Total energy delivered
        duration_minutes: Session duration
    """

    def __init__(
        self,
        session_id: str = "",
        timestamps: list[int] | None = None,
        power_values: list[float] | None = None,
        soc_values: list[float] | None = None,
        voltage_values: list[float] | None = None,
        current_values: list[float] | None = None,
        total_energy_kwh: float = 0.0,
        duration_minutes: int = 0,
    ):
        """Initialize ChargingSessionChartData message."""
        super().__init__()
        self.session_id = session_id
        self.timestamps = timestamps or []
        self.power_values = power_values or []
        self.soc_values = soc_values or []
        self.voltage_values = voltage_values or []
        self.current_values = current_values or []
        self.total_energy_kwh = total_energy_kwh
        self.duration_minutes = duration_minutes

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "session_id": self.session_id,
            "timestamps": self.timestamps,
            "power_values": self.power_values,
            "soc_values": self.soc_values,
            "voltage_values": self.voltage_values,
            "current_values": self.current_values,
            "total_energy_kwh": self.total_energy_kwh,
            "duration_minutes": self.duration_minutes,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.session_id:
            output.extend(self._encode_field_value(1, self.session_id, 2))
        # Repeated fields use multiple tags with same field number
        for timestamp in self.timestamps:
            output.extend(self._encode_field_value(2, timestamp, 0))
        for power in self.power_values:
            output.extend(self._encode_field_value(3, power, 1))
        for soc in self.soc_values:
            output.extend(self._encode_field_value(4, soc, 1))
        for voltage in self.voltage_values:
            output.extend(self._encode_field_value(5, voltage, 1))
        for current in self.current_values:
            output.extend(self._encode_field_value(6, current, 1))
        if self.total_energy_kwh:
            output.extend(self._encode_field_value(7, self.total_energy_kwh, 1))
        if self.duration_minutes:
            output.extend(self._encode_field_value(8, self.duration_minutes, 0))
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
        elif wire_type == 2:  # Length-delimited (string)
            if isinstance(value, str):
                value_bytes = value.encode("utf-8")
            else:
                value_bytes = value
            return tag_bytes + _encode_varint(len(value_bytes)) + value_bytes
        return tag_bytes


class ChargingScheduleTimeWindow(_message.Message):
    """Charging schedule time window.

    RVM: charging.schedule.time_window

    Attributes:
        start_time: Start time of day
        end_time: End time of day
        start_day_of_week: Start day (0=Sunday, 6=Saturday)
        end_day_of_week: End day (0=Sunday, 6=Saturday)
    """

    def __init__(
        self,
        start_time: TimeOfDay | None = None,
        end_time: TimeOfDay | None = None,
        start_day_of_week: int = 0,
        end_day_of_week: int = 6,
    ):
        """Initialize ChargingScheduleTimeWindow message."""
        super().__init__()
        self.start_time = start_time or TimeOfDay()
        self.end_time = end_time or TimeOfDay()
        self.start_day_of_week = start_day_of_week
        self.end_day_of_week = end_day_of_week

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "start_time": self.start_time.to_dict() if self.start_time else None,
            "end_time": self.end_time.to_dict() if self.end_time else None,
            "start_day_of_week": self.start_day_of_week,
            "end_day_of_week": self.end_day_of_week,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.start_time:
            output.extend(self._encode_field_value(1, self.start_time, 2))
        if self.end_time:
            output.extend(self._encode_field_value(2, self.end_time, 2))
        if self.start_day_of_week:
            output.extend(self._encode_field_value(3, self.start_day_of_week, 0))
        if self.end_day_of_week:
            output.extend(self._encode_field_value(4, self.end_day_of_week, 0))
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
        elif wire_type == 2:  # Length-delimited (embedded message)
            if isinstance(value, TimeOfDay):
                value_bytes = value.SerializeToString()
            else:
                value_bytes = value
            return tag_bytes + _encode_varint(len(value_bytes)) + value_bytes
        return tag_bytes
