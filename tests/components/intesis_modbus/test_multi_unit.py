"""Tests for a multi-unit gateway end to end."""

from unittest.mock import patch

from modbus_connection.mock import MockModbusConnection, WriteEvent
import pytest
from pytest_homeassistant.common import MockConfigEntry, snapshot_platform
from pytest_homeassistant.typing import WebSocketGenerator
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.climate import (
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACAction,
    HVACMode,
)
from homeassistant.components.intesis_modbus.const import DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from . import MOCK_MULTI_ENTRY_DATA, seed_multi_unit

ENTRY_ID = "01JTESTINTESISMULTI0000000"


@pytest.fixture
def mock_multi_connection() -> MockModbusConnection:
    """A fake Modbus TCP connection seeded as a 48-unit gateway with 3 units."""
    connection = MockModbusConnection()
    seed_multi_unit(connection.for_unit(1), present=(0, 1, 7))
    return connection


@pytest.fixture
def mock_multi_entry() -> MockConfigEntry:
    """Mock a multi-unit gateway config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id=ENTRY_ID,
        unique_id="192.168.1.50:502:1",
        data=MOCK_MULTI_ENTRY_DATA,
        title="INMBSMHI048O000",
    )


@pytest.fixture
async def init_multi_integration(
    hass: HomeAssistant,
    mock_multi_entry: MockConfigEntry,
    mock_multi_connection: MockModbusConnection,
) -> MockConfigEntry:
    """Set up the multi-unit gateway."""
    with patch(
        "homeassistant.components.intesis_modbus.async_get_unit",
        side_effect=lambda hass, entry, params, unit_id: mock_multi_connection.for_unit(
            unit_id
        ),
    ):
        mock_multi_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_multi_entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
    return mock_multi_entry


async def test_multi_unit_devices(
    hass: HomeAssistant,
    init_multi_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """The gateway gets one child device per present indoor unit."""
    devices = dr.async_entries_for_config_entry(device_registry, ENTRY_ID)
    gateway = next(d for d in devices if (DOMAIN, ENTRY_ID) in d.identifiers)
    units = sorted(
        (d for d in devices if d.id != gateway.id), key=lambda d: d.name or ""
    )
    assert [d.name for d in units] == [
        "Indoor unit 0",
        "Indoor unit 1",
        "Indoor unit 7",
    ]
    assert all(d.via_device_id == gateway.id for d in units)
    assert gateway.model == "INMBSMHI048O000"
    assert gateway.sw_version is None


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize(
    "platform",
    [
        Platform.BINARY_SENSOR,
        Platform.BUTTON,
        Platform.CLIMATE,
        Platform.SENSOR,
        Platform.SWITCH,
    ],
)
async def test_multi_unit_snapshot(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_multi_entry: MockConfigEntry,
    mock_multi_connection: MockModbusConnection,
    platform: Platform,
) -> None:
    """Every entity of a multi-unit gateway matches its snapshot."""
    with (
        patch("homeassistant.components.intesis_modbus.PLATFORMS", [platform]),
        patch(
            "homeassistant.components.intesis_modbus.async_get_unit",
            side_effect=lambda hass, entry, params, unit_id: (
                mock_multi_connection.for_unit(unit_id)
            ),
        ),
    ):
        mock_multi_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_multi_entry.entry_id)
        await hass.async_block_till_done()
    await snapshot_platform(hass, entity_registry, snapshot, mock_multi_entry.entry_id)


async def test_multi_unit_climate(
    hass: HomeAssistant, init_multi_integration: MockConfigEntry
) -> None:
    """An indoor unit's climate entity reports its action and limits."""
    state = hass.states.get("climate.indoor_unit_7")
    assert state is not None
    assert state.state == HVACMode.HEAT
    attrs = state.attributes
    assert attrs[ATTR_HVAC_ACTION] == HVACAction.HEATING
    assert attrs["fan_modes"] == ["low", "medium", "high", "powerful"]
    assert attrs["hvac_modes"] == ["off", "cool", "heat", "fan_only", "auto", "dry"]
    assert attrs["min_temp"] == 16
    assert attrs["max_temp"] == 30
    assert attrs["target_temp_step"] == 1
    assert attrs["current_temperature"] == 21
    assert attrs["temperature"] == 22


@pytest.mark.parametrize(
    ("block", "expected_action"),
    [
        ({1: 0}, HVACAction.OFF),
        ({2: 2}, HVACAction.FAN),
        ({10: 0, 13: 0}, HVACAction.IDLE),
        ({2: 0}, HVACAction.COOLING),
        ({2: 4}, HVACAction.DRYING),
        ({1: 0x8000}, None),
        ({2: 9}, None),
    ],
)
async def test_multi_unit_hvac_action(
    hass: HomeAssistant,
    mock_multi_entry: MockConfigEntry,
    mock_multi_connection: MockModbusConnection,
    block: dict[int, int],
    expected_action: HVACAction | None,
) -> None:
    """The action follows power, mode and the compressor/thermo flags."""
    unit = mock_multi_connection.for_unit(1)
    for offset, value in block.items():
        unit.holding[140 + offset] = value
    with patch(
        "homeassistant.components.intesis_modbus.async_get_unit",
        side_effect=lambda hass, entry, params, unit_id: unit,
    ):
        mock_multi_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_multi_entry.entry_id)
        await hass.async_block_till_done()
    state = hass.states.get("climate.indoor_unit_7")
    assert state is not None
    assert state.attributes.get(ATTR_HVAC_ACTION) == expected_action


async def test_multi_unit_writes(
    hass: HomeAssistant,
    init_multi_integration: MockConfigEntry,
    mock_multi_connection: MockModbusConnection,
) -> None:
    """Writes for indoor unit 7 land in its block at 140."""
    writes: list[WriteEvent] = []
    mock_multi_connection.for_unit(1).on_write(writes.append)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: "climate.indoor_unit_7", ATTR_TEMPERATURE: 24},
        blocking=True,
    )
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: "climate.indoor_unit_7", ATTR_HVAC_MODE: HVACMode.COOL},
        blocking=True,
    )
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.indoor_unit_7_reset_filter_sign"},
        blocking=True,
    )
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.indoor_unit_7_remote_controller_lock"},
        blocking=True,
    )
    assert [(w.address, w.values[0]) for w in writes] == [
        (143, 24),
        (142, 0),
        (151, 1),
        (145, 0),
    ]


async def test_multi_unit_sensors(
    hass: HomeAssistant, init_multi_integration: MockConfigEntry
) -> None:
    """Per-unit and gateway sensors read their blocks."""
    assert hass.states.get("sensor.indoor_unit_0_error").state == "none"
    assert hass.states.get("binary_sensor.indoor_unit_0_filter_sign").state == STATE_OFF
    assert (
        hass.states.get("switch.indoor_unit_0_remote_controller_lock").state
        == STATE_OFF
    )
    hw = hass.states.get("binary_sensor.inmbsmhi048o000_hardware_communication")
    assert hw is not None
    assert hw.state == STATE_ON


async def test_remove_stale_unit_device(
    hass: HomeAssistant,
    init_multi_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """A unit the gateway no longer lists can be removed; a present one cannot."""
    assert await async_setup_component(hass, "config", {})
    stale = device_registry.async_get_or_create(
        config_entry_id=ENTRY_ID,
        identifiers={("other_domain", "ignored"), (DOMAIN, f"{ENTRY_ID}_unit_9")},
    )
    present = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{ENTRY_ID}_unit_7"), config_entry_id=ENTRY_ID
    )
    gateway = device_registry.async_get_device_by_identifier(
        (DOMAIN, ENTRY_ID), config_entry_id=ENTRY_ID
    )
    assert present is not None
    assert gateway is not None
    client = await hass_ws_client(hass)
    assert (await client.remove_device(stale.id))["success"]
    assert device_registry.async_get(stale.id) is None
    assert not (await client.remove_device(present.id))["success"]
    assert not (await client.remove_device(gateway.id))["success"]
