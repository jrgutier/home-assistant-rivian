"""Navigation Protocol Buffer messages for Parallax protocol."""

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


class TripProgress(_message.Message):
    """Trip progress.

    RVM: navigation.navigation_service.trip_progress

    Attributes:
        destination_name: Destination name
        distance_remaining_km: Distance remaining (kilometers)
        time_remaining_mins: Time remaining (minutes)
        battery_at_destination_percent: Estimated battery at destination (%)
        charging_stops_remaining: Number of charging stops remaining
    """

    def __init__(
        self,
        destination_name: str = "",
        distance_remaining_km: float = 0.0,
        time_remaining_mins: int = 0,
        battery_at_destination_percent: int = 0,
        charging_stops_remaining: int = 0,
    ):
        """Initialize TripProgress message."""
        super().__init__()
        self.destination_name = destination_name
        self.distance_remaining_km = distance_remaining_km
        self.time_remaining_mins = time_remaining_mins
        self.battery_at_destination_percent = battery_at_destination_percent
        self.charging_stops_remaining = charging_stops_remaining

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "destination_name": self.destination_name,
            "distance_remaining_km": self.distance_remaining_km,
            "time_remaining_mins": self.time_remaining_mins,
            "battery_at_destination_percent": self.battery_at_destination_percent,
            "charging_stops_remaining": self.charging_stops_remaining,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.destination_name:
            output.extend(self._encode_field_value(1, self.destination_name, 2))
        if self.distance_remaining_km:
            output.extend(self._encode_field_value(2, self.distance_remaining_km, 1))
        if self.time_remaining_mins:
            output.extend(self._encode_field_value(3, self.time_remaining_mins, 0))
        if self.battery_at_destination_percent:
            output.extend(
                self._encode_field_value(4, self.battery_at_destination_percent, 0)
            )
        if self.charging_stops_remaining:
            output.extend(self._encode_field_value(5, self.charging_stops_remaining, 0))
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


class Waypoint(_message.Message):
    """A single waypoint in a trip.

    Attributes:
        latitude: Latitude in decimal degrees
        longitude: Longitude in decimal degrees
        name: Waypoint name or address
        arrival_time: Estimated arrival time (ISO timestamp)
        is_charging_stop: Whether this waypoint is a charging stop
    """

    def __init__(
        self,
        latitude: float = 0.0,
        longitude: float = 0.0,
        name: str = "",
        arrival_time: str = "",
        is_charging_stop: bool = False,
    ):
        """Initialize Waypoint message."""
        super().__init__()
        self.latitude = latitude
        self.longitude = longitude
        self.name = name
        self.arrival_time = arrival_time
        self.is_charging_stop = is_charging_stop

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "name": self.name,
            "arrival_time": self.arrival_time,
            "is_charging_stop": self.is_charging_stop,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.latitude:
            output.extend(self._encode_field_value(1, self.latitude, 1))
        if self.longitude:
            output.extend(self._encode_field_value(2, self.longitude, 1))
        if self.name:
            output.extend(self._encode_field_value(3, self.name, 2))
        if self.arrival_time:
            output.extend(self._encode_field_value(4, self.arrival_time, 2))
        if self.is_charging_stop:
            output.extend(
                self._encode_field_value(5, 1 if self.is_charging_stop else 0, 0)
            )
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


class TripInfo(_message.Message):
    """Complete trip information.

    RVM: navigation.navigation_service.trip_info

    Attributes:
        trip_id: Unique trip identifier
        waypoints: List of Waypoint messages
        total_distance_km: Total trip distance in kilometers
        total_duration_minutes: Total trip duration in minutes
        estimated_arrival_soc: Estimated state of charge at arrival (%)
        is_active: Whether the trip is currently active
    """

    def __init__(
        self,
        trip_id: str = "",
        waypoints: list["Waypoint"] | None = None,
        total_distance_km: float = 0.0,
        total_duration_minutes: int = 0,
        estimated_arrival_soc: float = 0.0,
        is_active: bool = False,
    ):
        """Initialize TripInfo message."""
        super().__init__()
        self.trip_id = trip_id
        self.waypoints = waypoints if waypoints is not None else []
        self.total_distance_km = total_distance_km
        self.total_duration_minutes = total_duration_minutes
        self.estimated_arrival_soc = estimated_arrival_soc
        self.is_active = is_active

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "trip_id": self.trip_id,
            "waypoints": [waypoint.to_dict() for waypoint in self.waypoints],
            "total_distance_km": self.total_distance_km,
            "total_duration_minutes": self.total_duration_minutes,
            "estimated_arrival_soc": self.estimated_arrival_soc,
            "is_active": self.is_active,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.trip_id:
            output.extend(self._encode_field_value(1, self.trip_id, 2))
        # Field 2: repeated waypoints (each is length-delimited)
        for waypoint in self.waypoints:
            waypoint_bytes = waypoint.SerializeToString()
            output.extend(self._encode_field_value(2, waypoint_bytes, 2))
        if self.total_distance_km:
            output.extend(self._encode_field_value(3, self.total_distance_km, 1))
        if self.total_duration_minutes:
            output.extend(self._encode_field_value(4, self.total_duration_minutes, 0))
        if self.estimated_arrival_soc:
            output.extend(self._encode_field_value(5, self.estimated_arrival_soc, 1))
        if self.is_active:
            output.extend(self._encode_field_value(6, 1 if self.is_active else 0, 0))
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
        elif wire_type == 2:  # Length-delimited (string/bytes)
            if isinstance(value, str):
                value_bytes = value.encode("utf-8")
            else:
                value_bytes = value
            return tag_bytes + _encode_varint(len(value_bytes)) + value_bytes
        return tag_bytes
