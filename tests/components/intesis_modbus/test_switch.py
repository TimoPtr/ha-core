"""Tests for the Intesis Modbus switch platform."""

from unittest.mock import MagicMock, patch

from modbus_connection.mock import MockModbusConnection, WriteEvent
import pytest
from pytest_homeassistant.common import MockConfigEntry, snapshot_platform
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

PREFIX = "switch.inmbsmhi001r000_"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_all_switches_snapshot(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
) -> None:
    """Every switch matches its snapshot."""
    with patch("homeassistant.components.intesis_modbus.PLATFORMS", [Platform.SWITCH]):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_switches_write(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
    mock_connection: MockModbusConnection,
) -> None:
    """Each switch writes its register and reads it back."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    expected = {
        "remote_controller_lock": 8,
        "window_contact": 6,
        "gateway_disabled": 7,
        "block_repeated_commands": 97,
        "xy_bus_master": 98,
    }
    writes: list[WriteEvent] = []
    mock_connection.for_unit(1).on_write(writes.append)
    for key, address in expected.items():
        assert hass.states.get(PREFIX + key).state == STATE_OFF
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: PREFIX + key},
            blocking=True,
        )
        assert writes[-1].address == address
        assert writes[-1].values[0] == 1
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: PREFIX + key},
            blocking=True,
        )
        assert writes[-1].address == address
        assert writes[-1].values[0] == 0
    assert len(writes) == 10


async def test_switch_reflects_register(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """A register the wall remote flips shows as on."""
    assert hass.states.get(PREFIX + "window_contact").state == STATE_OFF
    mock_connection.for_unit(1).holding[6] = 1
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: PREFIX + "remote_controller_lock"},
        blocking=True,
    )
    assert hass.states.get(PREFIX + "window_contact").state == STATE_ON
