"""Tests for the Intesis Modbus sensor platform."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from modbus_connection import IllegalDataAddressError, ModbusTimeoutError
from modbus_connection.mock import MockModbusConnection
import pytest
from pytest_homeassistant.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.intesis_modbus.const import SCAN_INTERVAL
from homeassistant.const import STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

PREFIX = "sensor.inmbsmhi001r000_"


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(seconds=SCAN_INTERVAL + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_all_sensors_snapshot(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
) -> None:
    """Every sensor matches its snapshot."""
    with patch("homeassistant.components.intesis_modbus.PLATFORMS", [Platform.SENSOR]):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_error_sensor_attributes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
    mock_connection: MockModbusConnection,
) -> None:
    """A unit error decodes to its state, code and description."""
    unit = mock_connection.for_unit(1)
    unit.holding[11] = 7
    unit.holding[81] = 2
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(PREFIX + "error")
    assert state is not None
    assert state.state == "unit_error"
    assert state.attributes["code"] == 7
    assert state.attributes["remote_controller_code"] == "E7"
    assert (
        state.attributes["description"]
        == "Indoor return air temperature thermistor anomaly"
    )
    assert state.attributes["error_address"] == 2


async def test_error_sensor_initialising(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
    mock_connection: MockModbusConnection,
) -> None:
    """The gateway's own init code maps to the initialising state."""
    mock_connection.for_unit(1).holding[11] = 65532
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(PREFIX + "error")
    assert state is not None
    assert state.state == "initialising"
    assert state.attributes["code"] == 65532
    assert state.attributes["remote_controller_code"] is None


async def test_temperatures_unavailable_when_block_fails(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """A refused temperature block hides only the sensors it backs."""
    assert hass.states.get(PREFIX + "outdoor_intake_temperature").state == "12.5"
    assert hass.states.get(PREFIX + "ambient_temperature").state == "20.3"
    mock_connection.for_unit(1).fail_read(60, IllegalDataAddressError())
    await _poll(hass, freezer)
    assert (
        hass.states.get(PREFIX + "outdoor_intake_temperature").state
        == STATE_UNAVAILABLE
    )
    assert hass.states.get(PREFIX + "ambient_temperature").state == "20.3"


async def test_operation_hours_keeps_last_value_when_offline(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """The long-term counter survives a silent gateway."""
    assert hass.states.get(PREFIX + "operation_time").state == "1234"
    mock_connection.for_unit(1).fail_requests(ModbusTimeoutError())
    await _poll(hass, freezer)
    assert hass.states.get(PREFIX + "operation_time").state == "1234"
    assert hass.states.get(PREFIX + "ambient_temperature").state == STATE_UNAVAILABLE


async def test_operation_hours_restores_until_the_gateway_reports(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
    mock_connection: MockModbusConnection,
) -> None:
    """A restored value stands in while the gateway still initialises."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(PREFIX + "operation_time", "1200"),
                {"native_value": 1200, "native_unit_of_measurement": "h"},
            )
        ],
    )
    unit = mock_connection.for_unit(1)
    unit.holding[9] = 0x8000
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(PREFIX + "operation_time").state == "1200"
    unit.holding[9] = 1234
    await _poll(hass, freezer)
    assert hass.states.get(PREFIX + "operation_time").state == "1234"


async def test_operation_hours_ignores_a_refused_control_block(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """When only the control block fails the counter keeps its value."""
    mock_connection.for_unit(1).fail_read(0, IllegalDataAddressError())
    await _poll(hass, freezer)
    assert hass.states.get(PREFIX + "operation_time").state == "1234"
    assert hass.states.get(PREFIX + "ambient_temperature").state == STATE_UNAVAILABLE
    assert hass.states.get(PREFIX + "outdoor_intake_temperature").state == "12.5"
