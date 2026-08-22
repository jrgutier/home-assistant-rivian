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

    Deliberately NO field-presence evidence source ("does the vehicle report
    ANY value, valid or not, for this field"). `RivianCoverEntityDescription`
    carried exactly that as `required_field` until s19's tonneau fix removed
    it: `closureTonneauClosed` is in `VEHICLE_STATE_SUBSCRIPTION_FIELDS`
    (const.py) -- the ONE wire document sent identically to every vehicle --
    so the key is present in `coordinator.data` for every model regardless
    of hardware, confirmed directly on two R1S community fixtures (no
    tonneau at all) that both carry the key with an SNA value
    (docs/development/GATE_FIELD_EVIDENCE.md). Presence-in-data carries the
    same zero hardware information usability did for `closure_liftgate_locked`
    (that doc's Finding 1) -- worse here, since there is no ambiguous case,
    only a confirmed one. That is why this mixin never had a field-presence
    source to begin with, and why the tonneau is gated on `option_code`
    instead (cover.py).

    feature: the server's `supportedFeatures[].name` string (or several, ANY
        of which counts) -- `vehicle["supported_features"]`
        (coordinator.py:850-856), NOT this integration's own group/key names.
    option_code: a member of the vehicle's `option_codes` list
        (`vehicle["option_codes"]`, coordinator.py:859, built by
        `_extract_option_codes()` at coordinator.py:767). List MEMBERSHIP
        (`in` on the list), not comparing the whole field with `==` --
        confirmed against test_coordinator_base.py's own
        `"TON-P01" in option_codes` assertion, not guessed. `option_codes`
        can be `None` (the mobileConfiguration fragment was rejected) as
        well as `[]` (accepted, no matching options); this mixin does not
        distinguish the two, since both mean no evidence.
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

    @property
    def on_values(self) -> list[Any]:
        """`on_value` as a list, however it was spelled.

        Both of `binary_sensor.py`'s `is_on` branches need this, and they had
        drifted: the single-field branch normalized, the aggregate branch
        compared `on_value` against a generator directly, which silently
        evaluates False for every frame once `on_value` is a list. Normalizing
        on the description -- the thing that owns `on_value` -- is what keeps a
        future third caller from having to rediscover that.

        Tests `list` rather than `str`, which the call sites did. Same result for
        every description shipping today (all five distinct `on_value`s are
        strings or lists), but the declared type also admits `bool | float | int`
        -- and those fell through the old `isinstance(..., str)` test unwrapped,
        leaving `val in True` to raise TypeError if anyone ever used one.
        """
        value = self.on_value
        return value if isinstance(value, list) else [value]


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
