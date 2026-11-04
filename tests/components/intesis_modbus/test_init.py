"""Tests for the Intesis Modbus integration setup."""

from datetime import timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusConnection
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from homeassistant.components.intesis_modbus.const import (
    DOMAIN,
    MANUFACTURER,
    SCAN_INTERVAL,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.loader import async_get_integration

from . import seed_initialising_single_unit


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
    [device] = dr.async_entries_for_config_entry(
        device_registry, init_integration.entry_id
    )
    assert (DOMAIN, init_integration.entry_id) in device.identifiers
    assert device.manufacturer == MANUFACTURER
    assert device.model == "INMBSMHI001R000"
    assert device.sw_version == "20"
    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
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


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(seconds=SCAN_INTERVAL + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_format_drift_raises_repair_issue(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
    issue_registry: ir.IssueRegistry,
) -> None:
    """A flipped SW4 switch raises a repair issue, cleared once it matches again."""
    issue_id = f"temperature_format_{init_integration.entry_id}"
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None
    unit = mock_connection.for_unit(1)
    unit.holding[4] = 22  # the gateway now reports whole degrees
    await _poll(hass, freezer)
    issue = issue_registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.config_entry_id == init_integration.entry_id
    assert issue.translation_placeholders is None
    unit.holding[4] = 215
    await _poll(hass, freezer)
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None


async def test_repair_issue_is_removed_with_the_entry(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Deleting the entry takes its open repair issue with it."""
    mock_connection.for_unit(1).holding[4] = 22
    await _poll(hass, freezer)
    issue_id = f"temperature_format_{init_integration.entry_id}"
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is not None
    await hass.config_entries.async_remove(init_integration.entry_id)
    await hass.async_block_till_done()
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None


async def test_initialising_does_not_raise_issue(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
    mock_connection: MockModbusConnection,
    issue_registry: ir.IssueRegistry,
) -> None:
    """While the format cannot be detected no issue is raised."""
    seed_initialising_single_unit(mock_connection.for_unit(1))
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert not issue_registry.issues
