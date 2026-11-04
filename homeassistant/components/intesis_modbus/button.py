"""Buttons for the one-shot commands an Intesis gateway accepts."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final, override

from intesis_gw_modbus import IndoorUnitView, IntesisSingleUnitGateway

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IntesisConfigEntry, IntesisCoordinator
from .entity import MULTI_UNIT_ONLY, IntesisEntity, IntesisEntityDescription

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class IntesisButtonDescription[TargetT](
    ButtonEntityDescription, IntesisEntityDescription
):
    """Describe a command on the gateway, or on one of its indoor units."""

    press_fn: Callable[[TargetT], Awaitable[None]]


BUTTONS: Final[tuple[IntesisButtonDescription[IntesisSingleUnitGateway], ...]] = (
    IntesisButtonDescription(
        key="reset_error",
        translation_key="reset_error",
        report_name="control",
        device_class=ButtonDeviceClass.RESTART,
        press_fn=lambda d: d.async_reset_error(),
    ),
    IntesisButtonDescription(
        key="reset_gateway",
        translation_key="reset_gateway",
        report_name="control",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda d: d.async_reset_gateway(),
    ),
)

INDOOR_UNIT_BUTTONS: Final[tuple[IntesisButtonDescription[IndoorUnitView], ...]] = (
    IntesisButtonDescription(
        key="reset_filter",
        translation_key="reset_filter",
        report_name="units",
        families=MULTI_UNIT_ONLY,
        device_class=ButtonDeviceClass.RESTART,
        press_fn=lambda u: u.async_reset_filter(),
    ),
    IntesisButtonDescription(
        key="reset_error",
        translation_key="reset_error",
        report_name="units",
        families=MULTI_UNIT_ONLY,
        device_class=ButtonDeviceClass.RESTART,
        press_fn=lambda u: u.async_reset_error(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntesisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons the gateway family offers."""
    runtime_data = entry.runtime_data
    coordinator = runtime_data.coordinator
    device = runtime_data.device
    if isinstance(device, IntesisSingleUnitGateway):
        async_add_entities(
            IntesisButton(coordinator, device, description) for description in BUTTONS
        )
        return
    async_add_entities(
        IntesisButton(coordinator, unit, description, unit_number=number)
        for number, unit in sorted(device.indoor_units.items())
        for description in INDOOR_UNIT_BUTTONS
    )


class IntesisButton[TargetT](IntesisEntity, ButtonEntity):
    """A command sent to the gateway or one of its indoor units."""

    entity_description: IntesisButtonDescription[TargetT]

    def __init__(
        self,
        coordinator: IntesisCoordinator,
        target: TargetT,
        description: IntesisButtonDescription[TargetT],
        *,
        unit_number: int | None = None,
    ) -> None:
        """Bind to the object the description commands."""
        super().__init__(coordinator, description, unit_number=unit_number)
        self._target: TargetT = target

    @override
    async def async_press(self) -> None:
        await self._async_write(lambda: self.entity_description.press_fn(self._target))
