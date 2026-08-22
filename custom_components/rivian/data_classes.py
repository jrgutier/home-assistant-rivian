"""Rivian Specific Data Classes"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.components.button import ButtonEntityDescription
from homeassistant.components.climate import ClimateEntityDescription
from homeassistant.components.cover import CoverEntityDescription
from homeassistant.components.lock import LockEntityDescription
from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.components.time import TimeEntityDescription
from homeassistant.helpers.entity import EntityDescription

from .rivian_client import VehicleCommand

if TYPE_CHECKING:
    from .coordinator import VehicleCoordinator


@dataclass(kw_only=True)
class RivianVehicleControlAvailableMixin:
    """Rivian vehicle control available mixin."""

    available: Callable[[VehicleCoordinator], bool] | None = None


@dataclass(kw_only=True)
class RivianGateMixin:
    """The three EVIDENCE fields `helpers.py`'s `vehicle_supports()` reads.

    s19 §A: plumbing only. Nothing constructs a description with any of these
    set yet, and nothing calls `vehicle_supports()` outside its own tests --
    switching a platform's `async_setup_entry` over to it is a later story.
    Every field defaults to `None`, so adding this mixin changes no existing
    description's behaviour.

    Deliberately NO `required_field`. `RivianCoverEntityDescription
    .required_field` (below) is a fourth, SEPARATE gate this mixin does not
    touch: "does the vehicle report a usable value for this field", which
    docs/development/GATE_FIELD_EVIDENCE.md found inverted on real hardware
    (an R1T reads a usable value for one of its three liftgate fields,
    hardware it does not have) and is why field-presence was never
    generalised into this mixin.

    feature: the server's `supportedFeatures[].name` string (or several, ANY
        of which counts) -- `vehicle["supported_features"]`
        (coordinator.py:825-829), NOT this integration's own group/key names.
    option_code: an entry in the vehicle's option codes. Matched by
        CONTAINMENT, never equality -- the Rivian app itself checks with
        Kotlin `contains`, so `"LFGT" in "XLFGTY"` is meant to match. No
        vehicle dict populates option codes yet (`vehicle.get("option_codes")`
        reads as absent for every vehicle today), so this evidence source
        never fires until a later story wires it in.
    legacy_group: one of `legacy_grants.py`'s group names ("R1T", "R1S",
        "LIFTGATE", ...), matched against what `groups_for_model()` returns
        for the vehicle. The permanent floor -- see that module's docstring.
    """

    feature: str | tuple[str, ...] | None = None
    option_code: str | None = None
    legacy_group: str | None = None


@dataclass(kw_only=True)
class RivianBinarySensorEntityDescription(
    BinarySensorEntityDescription, RivianGateMixin
):
    """Describes a Rivian binary sensor."""

    field: str | set[str]
    # Value to consider binary sensor to be "on"
    on_value: bool | float | int | str | list[str] = True
    negate: bool = False


@dataclass(kw_only=True)
class RivianButtonEntityDescription(
    ButtonEntityDescription, RivianVehicleControlAvailableMixin, RivianGateMixin
):
    """Rivian button entity description."""

    command: VehicleCommand | None = None
    command_params: dict[str, Any] | None = None
    press_fn: Callable[[VehicleCoordinator], Awaitable[str | None]] | None = None


@dataclass(kw_only=True)
class RivianClimateEntityDescription(ClimateEntityDescription, RivianGateMixin):
    """Rivian climate entity description.

    So climate.py's single CLIMATE description goes through the same
    RivianGateMixin call path as every other platform, even though it is
    ungated today (`available` is unset, so `vehicle_supports()` would
    return `{"ungated"}` for it -- see that function's docstring).
    """


@dataclass(kw_only=True)
class RivianCoverEntityDescription(CoverEntityDescription, RivianGateMixin):
    """Rivian cover entity description."""

    is_closed: Callable[[VehicleCoordinator], bool]
    # Create this cover only for vehicles that actually report `required_field`.
    #
    # The alternative -- a capability flag -- is what hid the tonneau cover from
    # everyone: `TONNEAU_CMD` is in no vehicle's supportedFeatures and in none of
    # the app's 32,941 decompiled files, while both tonneau commands are live-proven
    # to move the physical cover. A field the vehicle names is evidence; a flag
    # nothing emits is not.
    required_field: str | None = None
    command_open: VehicleCommand | None = None
    command_open_params: dict[str, Any] | None = None
    command_close: VehicleCommand | None = None
    command_close_params: dict[str, Any] | None = None
    close_cover: Callable[[VehicleCoordinator], Awaitable[str | None]] | None = None
    open_cover: Callable[[VehicleCoordinator], Awaitable[str | None]] | None = None


@dataclass(kw_only=True)
class RivianLockEntityDescription(LockEntityDescription, RivianGateMixin):
    """Rivian lock entity description."""

    is_locked: Callable[[VehicleCoordinator], bool | None]
    command_lock: VehicleCommand | None = None
    command_lock_params: dict[str, Any] | None = None
    command_unlock: VehicleCommand | None = None
    command_unlock_params: dict[str, Any] | None = None
    lock: Callable[[VehicleCoordinator], Awaitable[str | None]] | None = None
    unlock: Callable[[VehicleCoordinator], Awaitable[str | None]] | None = None


@dataclass(kw_only=True)
class RivianNumberEntityDescription(NumberEntityDescription, RivianGateMixin):
    """Rivian number entity description."""

    field: str
    set_fn: Callable[[VehicleCoordinator, float], Awaitable[None]]


@dataclass(kw_only=True)
class RivianSelectEntityDescription(SelectEntityDescription, RivianGateMixin):
    """Rivian select entity description."""

    field: str
    select: Callable[[VehicleCoordinator, str], Awaitable[None]]


@dataclass(kw_only=True)
class RivianSensorEntityDescription(SensorEntityDescription, RivianGateMixin):
    """Rivian Sensor Entity Description"""

    field: str
    value_fn: Callable[[VehicleCoordinator], Any] | None = None
    value_lambda: Callable[[Any], Any] | None = None


@dataclass(kw_only=True)
class RivianSwitchEntityDescription(
    SwitchEntityDescription, RivianVehicleControlAvailableMixin, RivianGateMixin
):
    """Rivian switch entity description."""

    is_on: Callable[[VehicleCoordinator], bool]
    command_on: VehicleCommand | None = None
    command_on_params: dict[str, Any] | None = None
    command_off: VehicleCommand | None = None
    command_off_params: dict[str, Any] | None = None
    turn_off: Callable[[VehicleCoordinator], Awaitable[str | None]] | None = None
    turn_on: Callable[[VehicleCoordinator], Awaitable[str | None]] | None = None


@dataclass(kw_only=True)
class RivianTrackerEntityDescription(EntityDescription, RivianGateMixin):
    """Rivian tracker entity Description."""


@dataclass(kw_only=True)
class RivianWallboxSensorEntityDescription(SensorEntityDescription, RivianGateMixin):
    """A class that describes Rivian wallbox sensor entities.

    Carries RivianGateMixin for consistency with every other description
    class, even though `vehicle_supports()` is a vehicle-gate predicate and a
    wallbox is not a vehicle -- these three fields simply stay unset here.
    """

    field: str


@dataclass(kw_only=True)
class RivianTimeEntityDescription(TimeEntityDescription, RivianGateMixin):
    """Rivian time entity description."""

    value_fn: Callable[[VehicleCoordinator], Any]
    set_fn: Callable[[VehicleCoordinator, Any], Awaitable[None]]
