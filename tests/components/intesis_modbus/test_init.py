"""Tests for the Intesis Modbus integration setup."""

from datetime import timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from modbus_connection import IllegalDataAddressError, ModbusTimeoutError
from modbus_connection.mock import MockModbusConnection
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from homeassistant.components.intesis_modbus.const import (
    DOMAIN,
    MANUFACTURER,
    SCAN_INTERVAL,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.loader import async_get_integration


async def test_manifest_loads(hass: HomeAssistant) -> None:
    """The integration manifest declares what the quality scale needs."""
    integration = await async_get_integration(hass, DOMAIN)
    assert integration.quality_scale == "platinum"
    assert "modbus" in integration.dependencies


async def test_setup_and_unload(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """The entry loads, registers the gateway device, and unloads cleanly."""
    assert init_integration.state is ConfigEntryState.LOADED
    device = device_registry.async_get_device(
        identifiers={(DOMAIN, init_integration.entry_id)}
    )
    assert device is not None
    assert device.manufacturer == MANUFACTURER
    assert device.model == "INMBSMHI001R000"
    assert device.sw_version == "20"
    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED


async def test_setup_retries_when_silent(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
    mock_connection: MockModbusConnection,
) -> None:
    """A gateway that does not answer puts the entry in setup retry."""
    mock_connection.for_unit(1).fail_requests(ModbusTimeoutError())
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_wrong_model_is_setup_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
    mock_connection: MockModbusConnection,
) -> None:
    """A gateway of another brand than the entry says is a setup error."""
    mock_connection.for_unit(1).holding[49] = 0x0801
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_timeout_marks_unavailable_then_recovers(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_get_unit: MagicMock,
    mock_connection: MockModbusConnection,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A silent gateway makes the coordinator fail; it recovers without a reload."""
    coordinator = init_integration.runtime_data.coordinator
    assert coordinator.last_update_success
    mock_connection.for_unit(1).fail_requests(ModbusTimeoutError())
    freezer.tick(timedelta(seconds=SCAN_INTERVAL))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not coordinator.last_update_success
    assert init_integration.state is ConfigEntryState.LOADED
    mock_connection.for_unit(1).fail_requests(None)
    freezer.tick(timedelta(seconds=SCAN_INTERVAL))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.last_update_success
    assert mock_get_unit.call_count == 1


async def test_partial_failure_only_hides_that_subsystem(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One refused block lands in the report and is logged once."""
    mock_connection.for_unit(1).fail_read(60, IllegalDataAddressError())
    freezer.tick(timedelta(seconds=SCAN_INTERVAL))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    coordinator = init_integration.runtime_data.coordinator
    assert coordinator.last_update_success
    assert "temperatures" in coordinator.data.failed
    assert "control" in coordinator.data.updated
    assert caplog.text.count("temperatures failed to refresh") == 1
    freezer.tick(timedelta(seconds=SCAN_INTERVAL))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert caplog.text.count("temperatures failed to refresh") == 1
    mock_connection.for_unit(1).fail_read(60, None)
    freezer.tick(timedelta(seconds=SCAN_INTERVAL))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert "temperatures is available again" in caplog.text


async def test_every_subsystem_failing_is_an_update_failure(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
    freezer: FrozenDateTimeFactory,
) -> None:
    """When no block answers the coordinator reports a failed update."""
    unit = mock_connection.for_unit(1)
    for address in (0, 13, 21, 31, 46, 55, 60, 65, 81, 97):
        unit.fail_read(address, IllegalDataAddressError())
    freezer.tick(timedelta(seconds=SCAN_INTERVAL))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not init_integration.runtime_data.coordinator.last_update_success
