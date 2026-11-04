"""Tests for the Intesis Modbus number platform."""

from unittest.mock import MagicMock, patch

from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusConnection, WriteEvent
import pytest
from pytest_homeassistant.common import MockConfigEntry, snapshot_platform
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

PREFIX = "number.inmbsmhi001r000_"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_all_numbers_snapshot(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
) -> None:
    """Every number matches its snapshot."""
    with patch("homeassistant.components.intesis_modbus.PLATFORMS", [Platform.NUMBER]):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


async def test_external_temperature_write(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """The external reference lands on register 22 in the gateway's format."""
    state = hass.states.get(PREFIX + "external_temperature_reference")
    assert state is not None
    assert state.state == "unknown"
    assert state.attributes["min"] == 10
    assert state.attributes["max"] == 38
    assert state.attributes["step"] == 0.5
    writes: list[WriteEvent] = []
    mock_connection.for_unit(1).on_write(writes.append)
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: PREFIX + "external_temperature_reference", ATTR_VALUE: 21.3},
        blocking=True,
    )
    assert [(w.address, w.values[0]) for w in writes] == [(22, 213)]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_window_timeout_write_and_validation(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
    mock_connection: MockModbusConnection,
) -> None:
    """The window timeout writes register 13 and rejects values past 30."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(PREFIX + "open_window_timeout").state == "30"
    writes: list[WriteEvent] = []
    mock_connection.for_unit(1).on_write(writes.append)
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: PREFIX + "open_window_timeout", ATTR_VALUE: 5},
        blocking=True,
    )
    assert [(w.address, w.values[0]) for w in writes] == [(13, 5)]
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: PREFIX + "open_window_timeout", ATTR_VALUE: 31},
            blocking=True,
        )


async def test_write_failure_raises(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_connection: MockModbusConnection,
) -> None:
    """A write the gateway does not answer surfaces as an error."""
    mock_connection.for_unit(1).fail_write(22, ModbusTimeoutError())
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: PREFIX + "external_temperature_reference", ATTR_VALUE: 20},
            blocking=True,
        )
