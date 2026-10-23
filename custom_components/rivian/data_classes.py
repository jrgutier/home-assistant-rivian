from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
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
    available: Callable[[VehicleCoordinator], bool] | None = None


@dataclass(kw_only=True)
class RivianGateMixin:
    feature: str | tuple[str, ...] | None = None
    option_code: str | None = None


@dataclass(kw_only=True)
class RivianBinarySensorEntityDescription(
    BinarySensorEntityDescription, RivianGateMixin
):
    field: str | set[str]
    on_value: bool | float | int | str | list[str] = True
    negate: bool = False

    @property
    def on_values(self) -> list[Any]:
        value = self.on_value
        return value if isinstance(value, list) else [value]


@dataclass(kw_only=True)
class RivianButtonEntityDescription(
    ButtonEntityDescription, RivianVehicleControlAvailableMixin, RivianGateMixin
):
    command: VehicleCommand | None = None
    command_params: dict[str, Any] | None = None
    press_fn: Callable[[VehicleCoordinator], Awaitable[str | None]] | None = None


@dataclass(kw_only=True)
class RivianCameraEntityDescription(EntityDescription, RivianGateMixin):
    camera: str = "left"


@dataclass(kw_only=True)
class RivianClimateEntityDescription(ClimateEntityDescription, RivianGateMixin):
    pass


@dataclass(kw_only=True)
class RivianCoverEntityDescription(CoverEntityDescription, RivianGateMixin):
    is_closed: Callable[[VehicleCoordinator], bool]
    command_open: VehicleCommand | None = None
    command_open_params: dict[str, Any] | None = None
    command_close: VehicleCommand | None = None
    command_close_params: dict[str, Any] | None = None
    close_cover: Callable[[VehicleCoordinator], Awaitable[str | None]] | None = None
    open_cover: Callable[[VehicleCoordinator], Awaitable[str | None]] | None = None


@dataclass(kw_only=True)
class RivianLockEntityDescription(LockEntityDescription, RivianGateMixin):
    is_locked: Callable[[VehicleCoordinator], bool | None]
    command_lock: VehicleCommand | None = None
    command_lock_params: dict[str, Any] | None = None
    command_unlock: VehicleCommand | None = None
    command_unlock_params: dict[str, Any] | None = None
    lock: Callable[[VehicleCoordinator], Awaitable[str | None]] | None = None
    unlock: Callable[[VehicleCoordinator], Awaitable[str | None]] | None = None


@dataclass(kw_only=True)
class RivianNumberEntityDescription(NumberEntityDescription, RivianGateMixin):
    field: str
    set_fn: Callable[[VehicleCoordinator, float], Awaitable[None]]


@dataclass(kw_only=True)
class RivianSelectEntityDescription(SelectEntityDescription, RivianGateMixin):
    field: str
    select: Callable[[VehicleCoordinator, str], Awaitable[None]]


@dataclass(kw_only=True)
class RivianSensorEntityDescription(SensorEntityDescription, RivianGateMixin):
    field: str
    value_fn: Callable[[VehicleCoordinator], Any] | None = None
    value_lambda: Callable[[Any], Any] | None = None
    attributes_lambda: Callable[[Any], Mapping[str, Any] | None] | None = None


@dataclass(kw_only=True)
class RivianSwitchEntityDescription(
    SwitchEntityDescription, RivianVehicleControlAvailableMixin, RivianGateMixin
):
    is_on: Callable[[VehicleCoordinator], bool]
    command_on: VehicleCommand | None = None
    command_on_params: dict[str, Any] | None = None
    command_off: VehicleCommand | None = None
    command_off_params: dict[str, Any] | None = None
    turn_off: Callable[[VehicleCoordinator], Awaitable[str | None]] | None = None
    turn_on: Callable[[VehicleCoordinator], Awaitable[str | None]] | None = None


@dataclass(kw_only=True)
class RivianTrackerEntityDescription(EntityDescription, RivianGateMixin):
    pass


@dataclass(kw_only=True)
class RivianWallboxSensorEntityDescription(SensorEntityDescription, RivianGateMixin):
    field: str


@dataclass(kw_only=True)
class RivianTimeEntityDescription(TimeEntityDescription, RivianGateMixin):
    value_fn: Callable[[VehicleCoordinator], Any]
    set_fn: Callable[[VehicleCoordinator, Any], Awaitable[None]]
