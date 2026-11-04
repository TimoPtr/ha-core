"""Binary sensors for the status flags an Intesis gateway reports."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, override

from intesis_gw_modbus import (
    IndoorUnitView,
    IntesisMultiUnitGateway,
    IntesisSingleUnitGateway,
)

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IntesisConfigEntry, IntesisCoordinator
from .entity import MULTI_UNIT_ONLY, IntesisEntity, IntesisEntityDescription

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class IntesisBinarySensorDescription[TargetT](
    BinarySensorEntityDescription, IntesisEntityDescription
):
    """Describe a flag read off the gateway, or off one of its indoor units."""

    value_fn: Callable[[TargetT], bool | None]


BINARY_SENSORS: Final[
    tuple[IntesisBinarySensorDescription[IntesisSingleUnitGateway], ...]
] = (
    IntesisBinarySensorDescription(
        key="alarm",
        translation_key="alarm",
        report_name="control",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.alarm,
    ),
    IntesisBinarySensorDescription(
        key="window_open",
        report_name="window",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=lambda d: d.window_open,
    ),
)

INDOOR_UNIT_BINARY_SENSORS: Final[
    tuple[IntesisBinarySensorDescription[IndoorUnitView], ...]
] = (
    IntesisBinarySensorDescription(
        key="filter_sign",
        translation_key="filter_sign",
        report_name="units",
        families=MULTI_UNIT_ONLY,
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda u: u.filter_sign,
    ),
    IntesisBinarySensorDescription(
        key="compressor",
        translation_key="compressor",
        report_name="units",
        families=MULTI_UNIT_ONLY,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_registry_enabled_default=False,
        value_fn=lambda u: u.compressor_on,
    ),
)

GATEWAY_BINARY_SENSORS: Final[
    tuple[IntesisBinarySensorDescription[IntesisMultiUnitGateway], ...]
] = (
    IntesisBinarySensorDescription(
        key="hw_communication",
        translation_key="hw_communication",
        report_name="status",
        families=MULTI_UNIT_ONLY,
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda d: d.hw_comm_ok,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntesisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors the gateway family offers."""
    runtime_data = entry.runtime_data
    coordinator = runtime_data.coordinator
    device = runtime_data.device
    if isinstance(device, IntesisSingleUnitGateway):
        async_add_entities(
            IntesisBinarySensor(coordinator, device, description)
            for description in BINARY_SENSORS
        )
        return
    entities: list[IntesisBinarySensor[Any]] = [
        IntesisBinarySensor(coordinator, device, description)
        for description in GATEWAY_BINARY_SENSORS
    ]
    entities.extend(
        IntesisBinarySensor(coordinator, unit, description, unit_number=number)
        for number, unit in sorted(device.indoor_units.items())
        for description in INDOOR_UNIT_BINARY_SENSORS
    )
    async_add_entities(entities)


class IntesisBinarySensor[TargetT](IntesisEntity, BinarySensorEntity):
    """A flag read off the gateway or one of its indoor units."""

    entity_description: IntesisBinarySensorDescription[TargetT]

    def __init__(
        self,
        coordinator: IntesisCoordinator,
        target: TargetT,
        description: IntesisBinarySensorDescription[TargetT],
        *,
        unit_number: int | None = None,
    ) -> None:
        """Bind to the object the description reads."""
        super().__init__(coordinator, description, unit_number=unit_number)
        self._target: TargetT = target

    @property
    @override
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self._target)
