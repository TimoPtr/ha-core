"""Base entity for Intesis Modbus gateways."""

from dataclasses import dataclass
from typing import NoReturn, override

from intesis_gw_modbus import GatewayFamily, UnsupportedValueError
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
        unit_number: int | None = None,
    ) -> None:
        """Place the entity on the gateway, or on one of its indoor units."""
        super().__init__(coordinator)
        self.entity_description = description
        entry_id = coordinator.config_entry.entry_id
        if unit_number is None:
            self._attr_unique_id = f"{entry_id}_{description.key}"
            self._attr_device_info = coordinator.gateway_device_info
        else:
            self._attr_unique_id = f"{entry_id}_unit_{unit_number}_{description.key}"
            self._attr_device_info = coordinator.indoor_unit_device_info(unit_number)

    @property
    @override
    def available(self) -> bool:
        """Whether this entity's sub-system answered the most recent poll."""
        if not super().available or self.coordinator.data is None:
            return False
        return self.entity_description.report_name in self.coordinator.data.updated

    def _raise_for_write(self, err: Exception) -> NoReturn:
        """Turn a library error from a write into the right HA exception."""
        if isinstance(err, UnsupportedValueError):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_value",
                translation_placeholders={"error": str(err)},
            ) from err
        if isinstance(err, ModbusError):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        raise err
