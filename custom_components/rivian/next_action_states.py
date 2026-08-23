"""Next Action State enums for Rivian vehicle components.

These enums match the Android app's NextActionState implementations
and provide helper methods for determining component states.
"""

from __future__ import annotations

from enum import Enum
from typing import TypeVar

_NextActionStateT = TypeVar("_NextActionStateT", bound="NextActionStateMixin")


class NextActionStateMixin:
    """The `from_api_value` every state enum below shares.

    Six byte-identical copies lived on the six enums, differing only in the
    return annotation. A plain mixin rather than a shared Enum base: an Enum
    that already has members cannot be subclassed, and the six vocabularies
    are deliberately separate -- they mirror the app's own per-closure
    NextActionState types (see this module's docstring). Only the conversion
    is shared; no member list moves.
    """

    # PYI019 is suppressed below: ruff would rewrite this TypeVar to `Self`,
    # which it imports from `typing_extensions` -- a runtime import the manifest
    # does not declare and `scripts/load_test.sh` would not have installed.
    @classmethod
    def from_api_value(  # noqa: PYI019
        cls: type[_NextActionStateT], value: str | None
    ) -> _NextActionStateT | None:
        """Convert API value to enum."""
        if not value:
            return None
        try:
            return cls(value.lower())
        except ValueError:
            return None


class FrunkNextActionState(NextActionStateMixin, Enum):
    """Front trunk next action states."""

    SNA = "sna"
    OPEN_ALLOWED = "open_allowed"
    CLOSE_ALLOWED = "close_allowed"
    OPENING = "opening"
    CLOSING = "closing"
    OPEN_NOT_AVAILABLE = "open_not_available"
    CLOSE_NOT_AVAILABLE = "close_not_available"
    OPEN_NOT_ALLOWED_FAULTED = "open_not_allowed_faulted"
    CLOSE_NOT_ALLOWED_FAULTED = "close_not_allowed_faulted"
    OPEN_ALLOWED_NO_POWERED_OPERATION = "open_allowed_no_powered_operation"
    CLOSE_NOT_ALLOWED_NO_POWERED_OPERATION = "close_not_allowed_no_powered_operation"
    OBSTRUCTED_WHILE_OPENING_CLOSE_ALLOWED = "obstructed_while_opening_close_allowed"
    OBSTRUCTED_WHILE_CLOSING_OPEN_ALLOWED = "obstructed_while_closing_open_allowed"

    def is_open(self) -> bool:
        """Check if frunk is opened (not closed)."""
        return self in (
            self.CLOSE_ALLOWED,
            self.CLOSING,
            self.CLOSE_NOT_AVAILABLE,
            self.CLOSE_NOT_ALLOWED_FAULTED,
            self.CLOSE_NOT_ALLOWED_NO_POWERED_OPERATION,
            self.OBSTRUCTED_WHILE_OPENING_CLOSE_ALLOWED,
            self.OBSTRUCTED_WHILE_CLOSING_OPEN_ALLOWED,
        )

    def is_closed(self) -> bool:
        """Check if frunk is closed."""
        return self in (
            self.OPEN_ALLOWED,
            self.OPENING,
            self.OPEN_NOT_AVAILABLE,
            self.OPEN_NOT_ALLOWED_FAULTED,
            self.OPEN_ALLOWED_NO_POWERED_OPERATION,
        )

    def is_opening(self) -> bool:
        """Check if frunk is currently opening."""
        return self == self.OPENING

    def is_closing(self) -> bool:
        """Check if frunk is currently closing."""
        return self == self.CLOSING

    def is_faulted(self) -> bool:
        """Check if there's a fault condition."""
        return self in (
            self.OPEN_NOT_ALLOWED_FAULTED,
            self.CLOSE_NOT_ALLOWED_FAULTED,
        )

    def is_obstructed(self) -> bool:
        """Check if there's an obstruction."""
        return self in (
            self.OBSTRUCTED_WHILE_OPENING_CLOSE_ALLOWED,
            self.OBSTRUCTED_WHILE_CLOSING_OPEN_ALLOWED,
        )


class LiftgateNextActionState(NextActionStateMixin, Enum):
    """Liftgate next action states."""

    SNA = "sna"
    OPEN_ALLOWED = "open_allowed"
    CLOSE_ALLOWED = "close_allowed"
    OPENING = "opening"
    CLOSING = "closing"
    OPEN_NOT_AVAILABLE = "open_not_available"
    CLOSE_NOT_AVAILABLE = "close_not_available"
    OPEN_ALLOWED_TRAILER_DETECTED = "open_allowed_trailer_detected"
    CLOSE_ALLOWED_TRAILER_DETECTED = "close_allowed_trailer_detected"
    OPEN_NOT_ALLOWED_FAULTED = "open_not_allowed_faulted"
    CLOSE_NOT_ALLOWED_FAULTED = "close_not_allowed_faulted"
    OPEN_ALLOWED_NO_POWERED_OPERATION = "open_allowed_no_powered_operation"
    CLOSE_NOT_ALLOWED_NO_POWERED_OPERATION = "close_not_allowed_no_powered_operation"
    OBSTRUCTED_WHILE_OPENING_CLOSE_ALLOWED = "obstructed_while_opening_close_allowed"
    OBSTRUCTED_WHILE_CLOSING_CLOSE_ALLOWED = "obstructed_while_closing_close_allowed"
    LOWER_GATE_OPEN_CLOSE_NOT_ALLOWED = "lower_gate_open_close_not_allowed"
    OPENING_PAUSE_NOT_ALLOWED = "opening_pause_not_allowed"
    CLOSING_PAUSE_NOT_ALLOWED = "closing_pause_not_allowed"
    OPEN_ALLOWED_OBSTACLE_DETECTED = "open_allowed_obstacle_detected"
    CLOSE_ALLOWED_OBSTACLE_DETECTED = "close_allowed_obstacle_detected"
    PROCESSING = "processing"

    def is_open(self) -> bool:
        """Check if liftgate is opened (not closed)."""
        return self in (
            self.CLOSE_ALLOWED,
            self.CLOSING,
            self.CLOSE_NOT_AVAILABLE,
            self.CLOSE_NOT_ALLOWED_FAULTED,
            self.CLOSE_NOT_ALLOWED_NO_POWERED_OPERATION,
            self.OBSTRUCTED_WHILE_OPENING_CLOSE_ALLOWED,
            self.OBSTRUCTED_WHILE_CLOSING_CLOSE_ALLOWED,
            self.LOWER_GATE_OPEN_CLOSE_NOT_ALLOWED,
            self.CLOSE_ALLOWED_OBSTACLE_DETECTED,
            self.CLOSE_ALLOWED_TRAILER_DETECTED,
        )

    def is_closed(self) -> bool:
        """Check if liftgate is closed."""
        return self in (
            self.OPEN_ALLOWED,
            self.OPENING,
            self.OPEN_NOT_AVAILABLE,
            self.OPEN_NOT_ALLOWED_FAULTED,
            self.OPEN_ALLOWED_NO_POWERED_OPERATION,
            self.OPEN_ALLOWED_TRAILER_DETECTED,
            self.OPEN_ALLOWED_OBSTACLE_DETECTED,
        )

    def is_opening(self) -> bool:
        """Check if liftgate is currently opening."""
        return self in (self.OPENING, self.OPENING_PAUSE_NOT_ALLOWED)

    def is_closing(self) -> bool:
        """Check if liftgate is currently closing."""
        return self in (self.CLOSING, self.CLOSING_PAUSE_NOT_ALLOWED)

    def is_faulted(self) -> bool:
        """Check if there's a fault condition."""
        return self in (
            self.OPEN_NOT_ALLOWED_FAULTED,
            self.CLOSE_NOT_ALLOWED_FAULTED,
        )

    def is_obstructed(self) -> bool:
        """Check if there's an obstruction."""
        return self in (
            self.OBSTRUCTED_WHILE_OPENING_CLOSE_ALLOWED,
            self.OBSTRUCTED_WHILE_CLOSING_CLOSE_ALLOWED,
        )

    def has_trailer_detected(self) -> bool:
        """Check if a trailer is detected."""
        return self in (
            self.OPEN_ALLOWED_TRAILER_DETECTED,
            self.CLOSE_ALLOWED_TRAILER_DETECTED,
        )

    def has_obstacle_detected(self) -> bool:
        """Check if an obstacle is detected."""
        return self in (
            self.OPEN_ALLOWED_OBSTACLE_DETECTED,
            self.CLOSE_ALLOWED_OBSTACLE_DETECTED,
        )


class TailgateNextActionState(NextActionStateMixin, Enum):
    """Tailgate next action states."""

    SNA = "sna"
    OPEN_ALLOWED = "open_allowed"
    OPEN_ALLOWED_TRAILER_DETECTED = "open_allowed_trailer_detected"
    OPENING = "opening"
    OPEN_NOT_AVAILABLE = "open_not_available"
    OPEN_NOT_ALLOWED_FAULTED = "open_not_allowed_faulted"
    STUCK_AJAR_WHILE_OPENING_OPEN_ALLOWED = "stuck_ajar_while_opening_open_allowed"
    OPEN_ALREADY_NO_ACTION_AVAILABLE = "open_already_no_action_available"
    OPEN_ALLOWED_CONFIRM_VEHICLE_ANGLE = "open_allowed_confirm_vehicle_angle"
    OPEN_ALLOWED_OBSTACLE_DETECTED = "open_allowed_obstacle_detected"

    def is_open(self) -> bool:
        """Check if tailgate is opened (dropped)."""
        return self in (
            self.STUCK_AJAR_WHILE_OPENING_OPEN_ALLOWED,
            self.OPEN_ALREADY_NO_ACTION_AVAILABLE,
        )

    def is_closed(self) -> bool:
        """Check if tailgate is closed (latched)."""
        return self in (
            self.OPEN_ALLOWED,
            self.OPENING,
            self.OPEN_NOT_AVAILABLE,
            self.OPEN_NOT_ALLOWED_FAULTED,
            self.OPEN_ALLOWED_TRAILER_DETECTED,
            self.OPEN_ALLOWED_CONFIRM_VEHICLE_ANGLE,
            self.OPEN_ALLOWED_OBSTACLE_DETECTED,
        )

    def is_opening(self) -> bool:
        """Check if tailgate is currently opening."""
        return self == self.OPENING

    def is_faulted(self) -> bool:
        """Check if there's a fault condition."""
        return self == self.OPEN_NOT_ALLOWED_FAULTED

    def has_trailer_detected(self) -> bool:
        """Check if a trailer is detected."""
        return self == self.OPEN_ALLOWED_TRAILER_DETECTED

    def has_obstacle_detected(self) -> bool:
        """Check if an obstacle is detected."""
        return self == self.OPEN_ALLOWED_OBSTACLE_DETECTED

    def needs_vehicle_angle_confirmation(self) -> bool:
        """Check if vehicle angle confirmation is needed."""
        return self == self.OPEN_ALLOWED_CONFIRM_VEHICLE_ANGLE


class ChargePortDoorNextActionState(NextActionStateMixin, Enum):
    """Charge port door next action states."""

    SNA = "sna"
    OPEN_ALLOWED = "open_allowed"
    OPEN_NOT_AVAILABLE = "open_not_available"
    OPEN_NOT_ALLOWED_FAULTED = "open_not_allowed_faulted"
    OPENING = "opening"
    CLOSE_ALLOWED = "close_allowed"
    OBSTRUCTED_WHILE_OPENING_CLOSE_ALLOWED = "obstructed_while_opening_close_allowed"
    OBSTRUCTED_WHILE_OPENING_OPEN_ALLOWED = "obstructed_while_opening_open_allowed"
    OBSTRUCTED_WHILE_CLOSING_CLOSE_ALLOWED = "obstructed_while_closing_close_allowed"
    CLOSE_NOT_AVAILABLE = "close_not_available"
    CLOSE_NOT_ALLOWED_FAULTED = "close_not_allowed_faulted"
    CLOSING = "closing"

    def is_open(self) -> bool:
        """Check if charge port door is opened."""
        return self in (
            self.CLOSE_ALLOWED,
            self.CLOSING,
            self.CLOSE_NOT_AVAILABLE,
            self.CLOSE_NOT_ALLOWED_FAULTED,
            self.OBSTRUCTED_WHILE_OPENING_CLOSE_ALLOWED,
            self.OBSTRUCTED_WHILE_CLOSING_CLOSE_ALLOWED,
        )

    def is_closed(self) -> bool:
        """Check if charge port door is closed."""
        return self in (
            self.OPEN_ALLOWED,
            self.OPENING,
            self.OPEN_NOT_AVAILABLE,
            self.OPEN_NOT_ALLOWED_FAULTED,
            self.OBSTRUCTED_WHILE_OPENING_OPEN_ALLOWED,
        )

    def is_opening(self) -> bool:
        """Check if charge port door is currently opening."""
        return self == self.OPENING

    def is_closing(self) -> bool:
        """Check if charge port door is currently closing."""
        return self == self.CLOSING

    def is_faulted(self) -> bool:
        """Check if there's a fault condition."""
        return self in (
            self.OPEN_NOT_ALLOWED_FAULTED,
            self.CLOSE_NOT_ALLOWED_FAULTED,
        )

    def is_obstructed(self) -> bool:
        """Check if there's an obstruction."""
        return self in (
            self.OBSTRUCTED_WHILE_OPENING_CLOSE_ALLOWED,
            self.OBSTRUCTED_WHILE_OPENING_OPEN_ALLOWED,
            self.OBSTRUCTED_WHILE_CLOSING_CLOSE_ALLOWED,
        )


class WindowsNextActionState(NextActionStateMixin, Enum):
    """Windows next action states."""

    SNA = "sna"
    OPEN_ALLOWED = "open_allowed"
    OBSTRUCTED_WHILE_CLOSING_CLOSE_ALLOWED = "obstructed_while_closing_close_allowed"
    CLOSE_NOT_ALLOWED_UNCALIBRATED = "close_not_allowed_uncalibrated"
    OPEN_NOT_ALLOWED_UNCALIBRATED = "open_not_allowed_uncalibrated"
    CLOSE_ALLOWED = "close_allowed"
    OPENING = "opening"
    CLOSING = "closing"
    MOVING = "moving"
    OPEN_NOT_AVAILABLE = "open_not_available"
    CLOSE_NOT_AVAILABLE = "close_not_available"
    OPEN_NOT_ALLOWED_FAULTED = "open_not_allowed_faulted"
    CLOSE_NOT_ALLOWED_FAULTED = "close_not_allowed_faulted"

    def is_open(self) -> bool:
        """Check if windows are opened (not fully closed)."""
        return self in (
            self.CLOSE_ALLOWED,
            self.OPENING,
            self.CLOSING,
            self.CLOSE_NOT_AVAILABLE,
            self.CLOSE_NOT_ALLOWED_FAULTED,
            self.OBSTRUCTED_WHILE_CLOSING_CLOSE_ALLOWED,
            self.CLOSE_NOT_ALLOWED_UNCALIBRATED,
            self.MOVING,
        )

    def is_closed(self) -> bool:
        """Check if windows are closed."""
        return self in (
            self.OPEN_ALLOWED,
            self.OPEN_NOT_AVAILABLE,
            self.OPEN_NOT_ALLOWED_FAULTED,
            self.OPEN_NOT_ALLOWED_UNCALIBRATED,
        )

    def is_opening(self) -> bool:
        """Check if windows are currently opening."""
        return self in (self.OPENING, self.MOVING)

    def is_closing(self) -> bool:
        """Check if windows are currently closing."""
        return self in (self.CLOSING, self.MOVING)

    def is_faulted(self) -> bool:
        """Check if there's a fault condition."""
        return self in (
            self.OPEN_NOT_ALLOWED_FAULTED,
            self.CLOSE_NOT_ALLOWED_FAULTED,
        )

    def is_obstructed(self) -> bool:
        """Check if there's an obstruction."""
        return self == self.OBSTRUCTED_WHILE_CLOSING_CLOSE_ALLOWED

    def needs_calibration(self) -> bool:
        """Check if windows need calibration."""
        return self in (
            self.CLOSE_NOT_ALLOWED_UNCALIBRATED,
            self.OPEN_NOT_ALLOWED_UNCALIBRATED,
        )


class SideBinNextActionState(NextActionStateMixin, Enum):
    """Side bin (gear tunnel) next action states."""

    SNA = "sna"
    OPEN_ALLOWED = "open_allowed"
    OPENING = "opening"
    OPEN_NOT_AVAILABLE = "open_not_available"
    OPEN_NOT_ALLOWED_FAULTED = "open_not_allowed_faulted"
    STUCK_AJAR_WHILE_OPENING_OPEN_ALLOWED = "stuck_ajar_while_opening_open_allowed"
    OPEN_ALREADY_NO_ACTION_AVAILABLE = "open_already_no_action_available"
    OPEN_ALLOWED_CONFIRM_VEHICLE_ANGLE = "open_allowed_confirm_vehicle_angle"

    def is_open(self) -> bool:
        """Check if side bin is opened."""
        return self in (
            self.STUCK_AJAR_WHILE_OPENING_OPEN_ALLOWED,
            self.OPEN_ALREADY_NO_ACTION_AVAILABLE,
        )

    def is_closed(self) -> bool:
        """Check if side bin is closed."""
        return self in (
            self.OPEN_ALLOWED,
            self.OPENING,
            self.OPEN_NOT_AVAILABLE,
            self.OPEN_NOT_ALLOWED_FAULTED,
            self.OPEN_ALLOWED_CONFIRM_VEHICLE_ANGLE,
        )

    def is_opening(self) -> bool:
        """Check if side bin is currently opening."""
        return self == self.OPENING

    def is_faulted(self) -> bool:
        """Check if there's a fault condition."""
        return self == self.OPEN_NOT_ALLOWED_FAULTED

    def needs_vehicle_angle_confirmation(self) -> bool:
        """Check if vehicle angle confirmation is needed."""
        return self == self.OPEN_ALLOWED_CONFIRM_VEHICLE_ANGLE
