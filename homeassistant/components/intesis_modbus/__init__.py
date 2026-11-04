"""The Intesis Modbus integration."""

from intesis_gw_modbus import MODELS

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_MODEL, CONF_UNIT_ID
from .coordinator import IntesisConfigEntry, IntesisCoordinator, IntesisRuntimeData
from .helpers import create_device, create_modbus_params

PLATFORMS: list[Platform] = [Platform.CLIMATE]


async def async_setup_entry(hass: HomeAssistant, entry: IntesisConfigEntry) -> None:
    """Set up Intesis Modbus from a config entry."""
    unit = async_get_unit(
        hass, entry, create_modbus_params(entry.data), entry.data[CONF_UNIT_ID]
    )
    device = create_device(unit, entry.data)
    coordinator = IntesisCoordinator(hass, entry, device)
    await coordinator.async_config_entry_first_refresh()
    # Up front: an indoor unit's device must name a gateway that has an id.
    gateway = dr.async_get(hass).async_get_or_create_from_info(
        config_entry_id=entry.entry_id, device_info=coordinator.gateway_device_info
    )
    coordinator.gateway_device_id = gateway.id
    entry.runtime_data = IntesisRuntimeData(
        coordinator, device, MODELS[entry.data[CONF_MODEL]].family
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def async_unload_entry(hass: HomeAssistant, entry: IntesisConfigEntry) -> None:
    """Unload a config entry."""
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
