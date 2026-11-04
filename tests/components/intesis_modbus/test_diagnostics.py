"""Tests for the Intesis Modbus diagnostics."""

from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusConnection
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.components.diagnostics import get_diagnostics_for_config_entry
from pytest_homeassistant.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion

from homeassistant.core import HomeAssistant


async def test_diagnostics_snapshot(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    """The download carries the raw register map and the last report."""
    result = await get_diagnostics_for_config_entry(hass, hass_client, init_integration)
    assert result == snapshot
    assert result["entry"]["device"] == "**REDACTED**"
    assert result["registers"]["holding"]["49"] == 0x0F00


async def test_diagnostics_read_error(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """A gateway that stops answering still yields a download."""
    mock_connection.for_unit(1).fail_requests(ModbusTimeoutError())
    result = await get_diagnostics_for_config_entry(hass, hass_client, init_integration)
    assert result["registers"] is None
    assert result["read_error"] == "ModbusTimeoutError"
