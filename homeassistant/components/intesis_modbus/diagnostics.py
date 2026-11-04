"""Diagnostics support for Intesis Modbus gateways."""

from typing import Any

from modbus_connection import ModbusError

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_DEVICE, CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import IntesisConfigEntry

TO_REDACT = {CONF_DEVICE, CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: IntesisConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry: the live raw register map."""
    runtime_data = entry.runtime_data
    coordinator = runtime_data.coordinator
    registers = read_error = None
    try:
        registers = await runtime_data.device.async_read_raw()
    except ModbusError as err:
        read_error = type(err).__name__
    report = coordinator.data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "family": runtime_data.family,
        "updated": sorted(report.updated) if report else None,
        "failed": {name: str(err) for name, err in report.failed.items()}
        if report
        else None,
        "read_error": read_error,
        "registers": registers,
    }
