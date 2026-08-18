"""Security and access-related Protocol Buffer messages for Parallax protocol."""

import struct
from typing import Any

from google.protobuf import message as _message

from .base import _encode_varint


class GeoFence(_message.Message):
    """A single geofence definition.

    Attributes:
        fence_id: Unique identifier for the geofence
        name: Human-readable name for the geofence
        latitude: Center latitude (-90 to 90)
        longitude: Center longitude (-180 to 180)
        radius_meters: Radius in meters
        enabled: Whether the geofence is active
    """

    def __init__(
        self,
        fence_id: str = "",
        name: str = "",
        latitude: float = 0.0,
        longitude: float = 0.0,
        radius_meters: float = 0.0,
        enabled: bool = True,
    ):
        """Initialize GeoFence message."""
        super().__init__()
        self.fence_id = fence_id
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.radius_meters = radius_meters
        self.enabled = enabled

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "fence_id": self.fence_id,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "radius_meters": self.radius_meters,
            "enabled": self.enabled,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.fence_id:
            output.extend(self._encode_field_value(1, self.fence_id, 2))
        if self.name:
            output.extend(self._encode_field_value(2, self.name, 2))
        if self.latitude:
            output.extend(self._encode_field_value(3, self.latitude, 1))
        if self.longitude:
            output.extend(self._encode_field_value(4, self.longitude, 1))
        if self.radius_meters:
            output.extend(self._encode_field_value(5, self.radius_meters, 1))
        if self.enabled:
            output.extend(self._encode_field_value(6, 1 if self.enabled else 0, 0))
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


class VehicleGeoFences(_message.Message):
    """Collection of geofences for a vehicle.

    RVM: location.geofence.vehicle_geo_fences

    Attributes:
        fences: List of geofence definitions
        max_fences: Maximum allowed geofences
    """

    def __init__(
        self,
        fences: list[GeoFence] | None = None,
        max_fences: int = 10,
    ):
        """Initialize VehicleGeoFences message."""
        super().__init__()
        self.fences = fences or []
        self.max_fences = max_fences

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "fences": [fence.to_dict() for fence in self.fences],
            "max_fences": self.max_fences,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        # Repeated field: encode each fence as a separate field
        for fence in self.fences:
            output.extend(self._encode_field_value(1, fence, 2))
        if self.max_fences:
            output.extend(self._encode_field_value(2, self.max_fences, 0))
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
            if isinstance(value, GeoFence):
                value_bytes = value.SerializeToString()
            else:
                value_bytes = value
            return tag_bytes + _encode_varint(len(value_bytes)) + value_bytes
        return tag_bytes


class GearGuardConsents(_message.Message):
    """GearGuard consent settings.

    RVM: security.gear_guard.consents

    Attributes:
        video_enabled: Whether video recording is enabled
        audio_enabled: Whether audio recording is enabled
        cloud_storage_enabled: Whether cloud storage is enabled
        local_storage_enabled: Whether local storage is enabled
        consent_timestamp: ISO timestamp of consent
    """

    def __init__(
        self,
        video_enabled: bool = False,
        audio_enabled: bool = False,
        cloud_storage_enabled: bool = False,
        local_storage_enabled: bool = False,
        consent_timestamp: str = "",
    ):
        """Initialize GearGuardConsents message."""
        super().__init__()
        self.video_enabled = video_enabled
        self.audio_enabled = audio_enabled
        self.cloud_storage_enabled = cloud_storage_enabled
        self.local_storage_enabled = local_storage_enabled
        self.consent_timestamp = consent_timestamp

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "video_enabled": self.video_enabled,
            "audio_enabled": self.audio_enabled,
            "cloud_storage_enabled": self.cloud_storage_enabled,
            "local_storage_enabled": self.local_storage_enabled,
            "consent_timestamp": self.consent_timestamp,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.video_enabled:
            output.extend(
                self._encode_field_value(1, 1 if self.video_enabled else 0, 0)
            )
        if self.audio_enabled:
            output.extend(
                self._encode_field_value(2, 1 if self.audio_enabled else 0, 0)
            )
        if self.cloud_storage_enabled:
            output.extend(
                self._encode_field_value(3, 1 if self.cloud_storage_enabled else 0, 0)
            )
        if self.local_storage_enabled:
            output.extend(
                self._encode_field_value(4, 1 if self.local_storage_enabled else 0, 0)
            )
        if self.consent_timestamp:
            output.extend(self._encode_field_value(5, self.consent_timestamp, 2))
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
        elif wire_type == 2:  # Length-delimited (string)
            if isinstance(value, str):
                value_bytes = value.encode("utf-8")
            else:
                value_bytes = value
            return tag_bytes + _encode_varint(len(value_bytes)) + value_bytes
        return tag_bytes


class GearGuardDailyLimits(_message.Message):
    """Daily GearGuard usage limits and current usage.

    RVM: security.gear_guard.daily_limits

    Attributes:
        daily_limit_minutes: Daily limit in minutes
        used_minutes: Minutes used today
        remaining_minutes: Minutes remaining today
        reset_time: ISO timestamp for daily reset
    """

    def __init__(
        self,
        daily_limit_minutes: int = 0,
        used_minutes: int = 0,
        remaining_minutes: int = 0,
        reset_time: str = "",
    ):
        """Initialize GearGuardDailyLimits message."""
        super().__init__()
        self.daily_limit_minutes = daily_limit_minutes
        self.used_minutes = used_minutes
        self.remaining_minutes = remaining_minutes
        self.reset_time = reset_time

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "daily_limit_minutes": self.daily_limit_minutes,
            "used_minutes": self.used_minutes,
            "remaining_minutes": self.remaining_minutes,
            "reset_time": self.reset_time,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.daily_limit_minutes:
            output.extend(self._encode_field_value(1, self.daily_limit_minutes, 0))
        if self.used_minutes:
            output.extend(self._encode_field_value(2, self.used_minutes, 0))
        if self.remaining_minutes:
            output.extend(self._encode_field_value(3, self.remaining_minutes, 0))
        if self.reset_time:
            output.extend(self._encode_field_value(4, self.reset_time, 2))
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
        elif wire_type == 2:  # Length-delimited (string)
            if isinstance(value, str):
                value_bytes = value.encode("utf-8")
            else:
                value_bytes = value
            return tag_bytes + _encode_varint(len(value_bytes)) + value_bytes
        return tag_bytes


class PassiveEntrySetting(_message.Message):
    """Passive entry configuration.

    RVM: access.passive_entry.setting

    Attributes:
        enabled: Whether passive entry is enabled
        unlock_on_approach: Whether to unlock when phone approaches
        lock_on_walk_away: Whether to lock when phone walks away
        approach_distance_meters: Distance threshold for approach (meters)
    """

    def __init__(
        self,
        enabled: bool = False,
        unlock_on_approach: bool = False,
        lock_on_walk_away: bool = False,
        approach_distance_meters: float = 0.0,
    ):
        """Initialize PassiveEntrySetting message."""
        super().__init__()
        self.enabled = enabled
        self.unlock_on_approach = unlock_on_approach
        self.lock_on_walk_away = lock_on_walk_away
        self.approach_distance_meters = approach_distance_meters

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "enabled": self.enabled,
            "unlock_on_approach": self.unlock_on_approach,
            "lock_on_walk_away": self.lock_on_walk_away,
            "approach_distance_meters": self.approach_distance_meters,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.enabled:
            output.extend(self._encode_field_value(1, 1 if self.enabled else 0, 0))
        if self.unlock_on_approach:
            output.extend(
                self._encode_field_value(2, 1 if self.unlock_on_approach else 0, 0)
            )
        if self.lock_on_walk_away:
            output.extend(
                self._encode_field_value(3, 1 if self.lock_on_walk_away else 0, 0)
            )
        if self.approach_distance_meters:
            output.extend(self._encode_field_value(4, self.approach_distance_meters, 1))
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


class PassiveEntryStatus(_message.Message):
    """Current passive entry status.

    RVM: access.passive_entry.status

    Attributes:
        is_active: Whether passive entry is currently active
        phone_in_range: Whether authorized phone is in range
        last_interaction_time: ISO timestamp of last interaction
        approach_distance_meters: Current approach distance (meters)
    """

    def __init__(
        self,
        is_active: bool = False,
        phone_in_range: bool = False,
        last_interaction_time: str = "",
        approach_distance_meters: float = 0.0,
    ):
        """Initialize PassiveEntryStatus message."""
        super().__init__()
        self.is_active = is_active
        self.phone_in_range = phone_in_range
        self.last_interaction_time = last_interaction_time
        self.approach_distance_meters = approach_distance_meters

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "is_active": self.is_active,
            "phone_in_range": self.phone_in_range,
            "last_interaction_time": self.last_interaction_time,
            "approach_distance_meters": self.approach_distance_meters,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.is_active:
            output.extend(self._encode_field_value(1, 1 if self.is_active else 0, 0))
        if self.phone_in_range:
            output.extend(
                self._encode_field_value(2, 1 if self.phone_in_range else 0, 0)
            )
        if self.last_interaction_time:
            output.extend(self._encode_field_value(3, self.last_interaction_time, 2))
        if self.approach_distance_meters:
            output.extend(self._encode_field_value(4, self.approach_distance_meters, 1))
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
