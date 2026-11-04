"""Tests for the Intesis Modbus button platform."""

from unittest.mock import MagicMock, patch

from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusConnection, WriteEvent
import pytest
from pytest_homeassistant.common import MockConfigEntry, snapshot_platform
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

PREFIX = "button.inmbsmhi001r000_"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_all_buttons_snapshot(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
) -> None:
    """Every button matches its snapshot."""
    with patch("homeassistant.components.intesis_modbus.PLATFORMS", [Platform.BUTTON]):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_buttons_write(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
    mock_connection: MockModbusConnection,
) -> None:
    """Reset error and reset gateway write the write-only registers."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    writes: list[WriteEvent] = []
    mock_connection.for_unit(1).on_write(writes.append)
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: PREFIX + "reset_error"},
        blocking=True,
    )
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: PREFIX + "reset_gateway"},
        blocking=True,
    )
    assert [(w.address, w.values[0]) for w in writes] == [(45, 1), (99, 1)]


async def test_button_write_failure_raises(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """A press the gateway does not answer surfaces as an error."""
    mock_connection.for_unit(1).fail_write(45, ModbusTimeoutError())
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: PREFIX + "reset_error"},
            blocking=True,
        )
