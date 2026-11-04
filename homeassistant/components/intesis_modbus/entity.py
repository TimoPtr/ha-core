"""Base entity for Intesis Modbus gateways."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import override

from intesis_gw_modbus import GatewayFamily, IndoorUnitView, UnsupportedValueError
from modbus_connection import ModbusError

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IntesisCoordinator

SINGLE_UNIT_ONLY = frozenset({GatewayFamily.SINGLE_UNIT})
MULTI_UNIT_ONLY = frozenset({GatewayFamily.MULTI_UNIT})


@dataclass(frozen=True, kw_only=True)
class IntesisEntityDescription(EntityDescription):
    """Describe an Intesis entity."""

    report_name: str
    """The sub-system name the update report mentions for this value."""
    families: frozenset[GatewayFamily] = SINGLE_UNIT_ONLY


class IntesisEntity(CoordinatorEntity[IntesisCoordinator]):
    """Defines a base Intesis entity."""

    _attr_has_entity_name = True
    entity_description: IntesisEntityDescription

    def __init__(
        self,
        coordinator: IntesisCoordinator,
        description: IntesisEntityDescription,
        *,
        indoor_unit: IndoorUnitView | None = None,
    ) -> None:
        """Place the entity on the gateway, or on one of its indoor units."""
        super().__init__(coordinator)
        self.entity_description = description
        self._indoor_unit = indoor_unit
        entry_id = coordinator.config_entry.entry_id
        if indoor_unit is None:
            self._attr_unique_id = f"{entry_id}_{description.key}"
            self._attr_device_info = coordinator.gateway_device_info
        else:
            number = indoor_unit.number
            self._attr_unique_id = f"{entry_id}_unit_{number}_{description.key}"
            self._attr_device_info = coordinator.indoor_unit_device_info(number)

    @property
    @override
    def available(self) -> bool:
        """Whether this entity's value was read in the most recent poll."""
        if (
            not super().available
            or self.entity_description.report_name not in self.coordinator.data.updated
        ):
            return False
        return self._indoor_unit is None or self._indoor_unit.present

    async def _async_write(self, write: Callable[[], Awaitable[None]]) -> None:
        """Run one write against the gateway, then ask for a refresh."""
        try:
            await write()
        except UnsupportedValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_value",
                translation_placeholders={"error": str(err)},
            ) from err
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.coordinator.async_request_refresh()
