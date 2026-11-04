"""Tests for the Intesis Modbus binary sensor platform."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from modbus_connection.mock import MockModbusConnection
import pytest
from pytest_homeassistant.common import (
    MockConfigEntry,
    async_fire_time_changed,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.intesis_modbus.const import SCAN_INTERVAL
from homeassistant.const import STATE_OFF, STATE_ON, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

PREFIX = "binary_sensor.inmbsmhi001r000_"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_all_binary_sensors_snapshot(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
) -> None:
    """Every binary sensor matches its snapshot."""
    with patch(
        "homeassistant.components.intesis_modbus.PLATFORMS", [Platform.BINARY_SENSOR]
    ):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


async def test_alarm_and_window(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """Alarm and window status follow registers 10 and 31."""
    assert hass.states.get(PREFIX + "alarm").state == STATE_OFF
    assert hass.states.get(PREFIX + "window").state == STATE_OFF
    unit = mock_connection.for_unit(1)
    unit.holding[10] = 1
    unit.holding[31] = 1
    freezer.tick(timedelta(seconds=SCAN_INTERVAL + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(PREFIX + "alarm").state == STATE_ON
    assert hass.states.get(PREFIX + "window").state == STATE_ON
