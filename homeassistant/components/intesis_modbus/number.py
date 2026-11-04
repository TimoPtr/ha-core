"""Numbers for the settings an Intesis gateway accepts."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final, override

from intesis_gw_modbus import IntesisSingleUnitGateway

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IntesisConfigEntry, IntesisCoordinator
from .entity import IntesisEntity, IntesisEntityDescription

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class IntesisNumberDescription(NumberEntityDescription, IntesisEntityDescription):
    """Describe a number on a single-unit gateway."""

    value_fn: Callable[[IntesisSingleUnitGateway], float | None]
    set_fn: Callable[[IntesisSingleUnitGateway, float], Awaitable[None]]
    step_fn: Callable[[IntesisSingleUnitGateway], float] | None = None


NUMBERS: Final[tuple[IntesisNumberDescription, ...]] = (
    IntesisNumberDescription(
        key="external_temperature",
        translation_key="external_temperature",
        report_name="limits",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=10,
        native_max_value=38,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda d: d.external_temperature,
        set_fn=lambda d, value: d.async_set_external_temperature(value),
        step_fn=lambda d: d.setpoint_step,
    ),
    IntesisNumberDescription(
        key="window_timeout",
        translation_key="window_timeout",
        report_name="control",
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        native_min_value=0,
        native_max_value=30,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.window_timeout_minutes,
        set_fn=lambda d, value: d.async_set_window_timeout(int(value)),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntesisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the numbers a single-unit gateway offers."""
    runtime_data = entry.runtime_data
    device = runtime_data.device
    if not isinstance(device, IntesisSingleUnitGateway):
        return
    async_add_entities(
        IntesisNumber(runtime_data.coordinator, device, description)
        for description in NUMBERS
    )


class IntesisNumber(IntesisEntity, NumberEntity):
    """A setting on a single-unit gateway."""

    entity_description: IntesisNumberDescription

    def __init__(
        self,
        coordinator: IntesisCoordinator,
        device: IntesisSingleUnitGateway,
        description: IntesisNumberDescription,
    ) -> None:
        """Bind to the gateway the description reads and writes."""
        super().__init__(coordinator, description)
        self._device = device

    @property
    @override
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self._device)

    @property
    @override
    def native_step(self) -> float | None:
        if (step_fn := self.entity_description.step_fn) is not None:
            return step_fn(self._device)
        return super().native_step

    @override
    async def async_set_native_value(self, value: float) -> None:
        await self._async_write(
            lambda: self.entity_description.set_fn(self._device, value)
        )
