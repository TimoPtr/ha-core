"""Switches for the on/off settings of an Intesis gateway."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Final, override

from intesis_gw_modbus import IndoorUnitView, IntesisSingleUnitGateway

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IntesisConfigEntry, IntesisCoordinator
from .entity import (
    MULTI_UNIT_ONLY,
    IntesisEntity,
    IntesisEntityDescription,
    async_add_indoor_unit_entities,
)

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class IntesisSwitchDescription[TargetT](
    SwitchEntityDescription, IntesisEntityDescription
):
    """Describe a switch on the gateway, or on one of its indoor units."""

    value_fn: Callable[[TargetT], bool | None]
    set_fn: Callable[[TargetT, bool], Awaitable[None]]


SWITCHES: Final[tuple[IntesisSwitchDescription[IntesisSingleUnitGateway], ...]] = (
    IntesisSwitchDescription(
        key="window_contact",
        translation_key="window_contact",
        report_name="control",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda d: d.window_contact,
        set_fn=lambda d, on: d.async_set_window_contact(on),
    ),
    IntesisSwitchDescription(
        key="remote_controller_lock",
        translation_key="remote_controller_lock",
        report_name="control",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda d: d.remote_control_disabled,
        set_fn=lambda d, on: d.async_set_remote_control_disabled(on),
    ),
    IntesisSwitchDescription(
        key="gateway_disabled",
        translation_key="gateway_disabled",
        report_name="control",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.gateway_disabled,
        set_fn=lambda d, on: d.async_set_gateway_disabled(on),
    ),
    IntesisSwitchDescription(
        key="block_periodic_sendings",
        translation_key="block_periodic_sendings",
        report_name="diagnostics",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.block_periodic_sendings,
        set_fn=lambda d, on: d.async_set_block_periodic_sendings(on),
    ),
    IntesisSwitchDescription(
        key="master",
        translation_key="master",
        report_name="diagnostics",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.is_master,
        set_fn=lambda d, on: d.async_set_master(on),
    ),
)

INDOOR_UNIT_SWITCHES: Final[tuple[IntesisSwitchDescription[IndoorUnitView], ...]] = (
    IntesisSwitchDescription(
        key="remote_controller_lock",
        translation_key="remote_controller_lock",
        report_name="units",
        families=MULTI_UNIT_ONLY,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda u: u.remote_control_locked,
        set_fn=lambda u, on: u.async_set_remote_control_locked(on),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntesisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches the gateway family offers."""
    runtime_data = entry.runtime_data
    coordinator = runtime_data.coordinator
    device = runtime_data.device
    if isinstance(device, IntesisSingleUnitGateway):
        async_add_entities(
            IntesisSwitch(coordinator, device, description) for description in SWITCHES
        )
        return
    async_add_indoor_unit_entities(
        entry,
        device,
        async_add_entities,
        lambda unit: [
            IntesisSwitch(coordinator, unit, description, indoor_unit=unit)
            for description in INDOOR_UNIT_SWITCHES
        ],
    )


class IntesisSwitch[TargetT](IntesisEntity, SwitchEntity):
    """An on/off setting on the gateway or one of its indoor units."""

    entity_description: IntesisSwitchDescription[TargetT]

    def __init__(
        self,
        coordinator: IntesisCoordinator,
        target: TargetT,
        description: IntesisSwitchDescription[TargetT],
        *,
        indoor_unit: IndoorUnitView | None = None,
    ) -> None:
        """Bind to the object the description reads and writes."""
        super().__init__(coordinator, description, indoor_unit=indoor_unit)
        self._target: TargetT = target

    @property
    @override
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self._target)

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_write(
            lambda: self.entity_description.set_fn(self._target, True)
        )

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_write(
            lambda: self.entity_description.set_fn(self._target, False)
        )
