"""Data update coordinator for Intesis Modbus gateways."""

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import override

from intesis_gw_modbus import GatewayFamily, IntesisSingleUnitGateway, WrongGatewayError
from modbus_connection import ModbusError
from modbus_connection.model import UpdateReport
from propcache.api import cached_property

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_MODEL, DOMAIN, MANUFACTURER, SCAN_INTERVAL
from .helpers import IntesisDevice

_LOGGER = logging.getLogger(__name__)


class IntesisCoordinator(DataUpdateCoordinator[UpdateReport]):
    """Poll one gateway and hand its update report to the entities."""

    config_entry: IntesisConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: IntesisConfigEntry, device: IntesisDevice
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.device = device
        self.gateway_device_id: str | None = None  # set once the device exists
        self._failing: set[str] = set()

    @override
    async def _async_update_data(self) -> UpdateReport:
        try:
            report: UpdateReport = await self.device.async_update()
        except WrongGatewayError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN, translation_key="wrong_model"
            ) from err
        except ModbusError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="modbus_error"
            ) from err
        if not report.updated:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="no_component_answered"
            ) from ExceptionGroup(
                "every sub-system failed to refresh", list(report.failed.values())
            )
        self._log_component_changes(report)
        return report

    def _log_component_changes(self, report: UpdateReport) -> None:
        """Log a sub-system's first failure and its recovery, once each."""
        for name, cause in report.failed.items():
            if name not in self._failing:
                self._failing.add(name)
                _LOGGER.warning(
                    "%s: %s failed to refresh, its entities are unavailable: %s",
                    self.name,
                    name,
                    cause,
                )
        for name in report.updated & self._failing:
            self._failing.discard(name)
            _LOGGER.info("%s: %s is available again", self.name, name)

    @cached_property
    def gateway_device_info(self) -> dr.DeviceInfo:
        """Describe the gateway to the device registry."""
        entry = self.config_entry
        info = dr.DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=entry.data[CONF_MODEL],
            name=entry.title,
        )
        if isinstance(self.device, IntesisSingleUnitGateway) and (
            version := self.device.software_version
        ):
            info["sw_version"] = version
        return info

    def indoor_unit_device_info(self, number: int) -> dr.DeviceInfo:
        """Describe one indoor unit behind a multi-unit gateway."""
        entry = self.config_entry
        return dr.DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_unit_{number}")},
            via_device_id=self.gateway_device_id,
            manufacturer=MANUFACTURER,
            model=entry.data[CONF_MODEL],
            translation_key="indoor_unit",
            translation_placeholders={"number": str(number)},
        )


@dataclass
class IntesisRuntimeData:
    """What the entry holds while it is loaded."""

    coordinator: IntesisCoordinator
    device: IntesisDevice
    family: GatewayFamily


type IntesisConfigEntry = ConfigEntry[IntesisRuntimeData]
