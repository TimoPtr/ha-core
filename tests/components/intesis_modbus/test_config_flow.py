"""Tests for the Intesis Modbus config flow."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, _patch, patch

from modbus_connection import (
    IllegalDataAddressError,
    ModbusSerialParams,
    ModbusTcpParams,
    ModbusTimeoutError,
)
from modbus_connection.mock import MockModbusConnection, MockModbusUnit
from pytest_homeassistant.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.components.intesis_modbus.const import (
    CONF_BAUDRATE,
    CONF_FRAMING,
    CONF_MODEL,
    CONF_TEMPERATURE_FORMAT,
    DOMAIN,
    FRAMING_RTU_OVER_TCP,
    TYPE_SERIAL,
    TYPE_TCP,
)
from homeassistant.components.intesis_modbus.helpers import create_modbus_params
from homeassistant.const import CONF_DEVICE, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError

from . import (
    MOCK_MULTI_ENTRY_DATA,
    MOCK_SERIAL_ENTRY_DATA,
    MOCK_SERIAL_INPUT,
    MOCK_TCP_INPUT,
    seed_initialising_single_unit,
    seed_multi_unit,
    seed_single_unit,
)

TARGET = "homeassistant.components.intesis_modbus.config_flow.async_get_temporary_unit"


def _patch_temporary_unit(connection: MockModbusConnection) -> _patch:
    """Stand in for async_get_temporary_unit, handing out a unit on connection."""

    @asynccontextmanager
    async def _get_temporary_unit(
        hass: HomeAssistant,
        params: ModbusSerialParams | ModbusTcpParams,
        unit_id: int,
    ) -> AsyncIterator[MockModbusUnit]:
        yield connection.for_unit(unit_id)

    return patch(TARGET, side_effect=_get_temporary_unit)


class _RaisingTemporaryUnit:
    """Stand in for a temporary-unit context whose __aenter__ raises."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def __aenter__(self) -> None:
        raise self._error

    async def __aexit__(self, *args: object) -> None:
        return None


def _seeded(seed: Any = seed_single_unit, **kwargs: Any) -> MockModbusConnection:
    connection = MockModbusConnection()
    seed(connection.for_unit(1), **kwargs)
    return connection


async def _start_serial(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": TYPE_SERIAL}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == TYPE_SERIAL
    return result["flow_id"]


async def _start_tcp(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": TYPE_TCP}
    )
    assert result["step_id"] == TYPE_TCP
    return result["flow_id"]


async def test_serial_auto_detects_mhi(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """A serial gateway whose device id is known needs no model step."""
    with _patch_temporary_unit(_seeded()):
        flow_id = await _start_serial(hass)
        result = await hass.config_entries.flow.async_configure(
            flow_id, MOCK_SERIAL_INPUT
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "INMBSMHI001R000"
    assert result["data"] == MOCK_SERIAL_ENTRY_DATA
    assert result["result"].unique_id == "/dev/ttyUSB0:1"
    assert mock_setup_entry.call_count == 1


async def test_serial_unknown_device_id_asks_model(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """An unknown device id leads to the model step, which checks the pick."""
    connection = _seeded()
    connection.for_unit(1).holding[49] = 0x0801
    with _patch_temporary_unit(connection):
        flow_id = await _start_serial(hass)
        result = await hass.config_entries.flow.async_configure(
            flow_id, MOCK_SERIAL_INPUT
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "model"
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_MODEL: "INMBSMHI001R000"}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "wrong_model"}
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_MODEL: "INMBSMHI048O000"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "INMBSMHI048O000"
    assert result["result"].unique_id == "/dev/ttyUSB0:1"
    assert CONF_TEMPERATURE_FORMAT not in result["data"]
    assert result["data"][CONF_MODEL] == "INMBSMHI048O000"


async def test_illegal_address_on_49_asks_model(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """A gateway that refuses register 49 goes through the model step."""
    connection = _seeded(seed_multi_unit, present=(0,))
    connection.for_unit(1).fail_read(49, IllegalDataAddressError())
    with _patch_temporary_unit(connection):
        flow_id = await _start_serial(hass)
        result = await hass.config_entries.flow.async_configure(
            flow_id, MOCK_SERIAL_INPUT
        )
        assert result["step_id"] == "model"
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_MODEL: "INMBSMHI048O000"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "/dev/ttyUSB0:1"


async def test_initialising_gateway_asks_temperature_format(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """With every register at the init value the format cannot be detected."""
    with _patch_temporary_unit(_seeded(seed_initialising_single_unit)):
        flow_id = await _start_serial(hass)
        result = await hass.config_entries.flow.async_configure(
            flow_id, MOCK_SERIAL_INPUT
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "temperature_format"
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_TEMPERATURE_FORMAT: "celsius"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "/dev/ttyUSB0:1"
    assert result["data"][CONF_TEMPERATURE_FORMAT] == "celsius"


async def test_cannot_connect(hass: HomeAssistant, mock_setup_entry: AsyncMock) -> None:
    """A silent gateway shows cannot_connect and the flow can be retried."""
    connection = _seeded()
    connection.for_unit(1).fail_requests(ModbusTimeoutError())
    with _patch_temporary_unit(connection):
        flow_id = await _start_serial(hass)
        result = await hass.config_entries.flow.async_configure(
            flow_id, MOCK_SERIAL_INPUT
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}
        connection.for_unit(1).fail_requests(None)
        result = await hass.config_entries.flow.async_configure(
            flow_id, MOCK_SERIAL_INPUT
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_serial_port_in_use_with_other_settings(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """A port held by another entry with other link settings cannot be probed."""
    with patch(
        TARGET, return_value=_RaisingTemporaryUnit(HomeAssistantError("in use"))
    ):
        flow_id = await _start_serial(hass)
        result = await hass.config_entries.flow.async_configure(
            flow_id, MOCK_SERIAL_INPUT
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    with _patch_temporary_unit(_seeded()):
        result = await hass.config_entries.flow.async_configure(
            flow_id, MOCK_SERIAL_INPUT
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "/dev/ttyUSB0:1"


async def test_tcp_rtu_over_tcp(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """A single-unit gateway behind a serial server is reached over a socket."""
    user_input = {
        **MOCK_TCP_INPUT,
        CONF_FRAMING: FRAMING_RTU_OVER_TCP,
        CONF_BAUDRATE: 9600,
    }
    with _patch_temporary_unit(_seeded()):
        flow_id = await _start_tcp(hass)
        result = await hass.config_entries.flow.async_configure(flow_id, user_input)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "192.168.1.50:502:1"
    assert result["data"][CONF_MODEL] == "INMBSMHI001R000"
    assert create_modbus_params(result["data"]) == ModbusSerialParams(
        device="socket://192.168.1.50:502",
        baudrate=9600,
        bytesize=8,
        parity="N",
        stopbits=2,
    )


async def test_tcp_multi_unit(hass: HomeAssistant, mock_setup_entry: AsyncMock) -> None:
    """A multi-unit gateway over Modbus TCP is picked from the model list."""
    with _patch_temporary_unit(_seeded(seed_multi_unit, present=(0,))):
        flow_id = await _start_tcp(hass)
        result = await hass.config_entries.flow.async_configure(
            flow_id, {**MOCK_TCP_INPUT, CONF_BAUDRATE: 9600}
        )
        assert result["step_id"] == "model"
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_MODEL: "INMBSMHI048O000"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "192.168.1.50:502:1"
    assert create_modbus_params(result["data"]) == ModbusTcpParams(
        host="192.168.1.50", port=502
    )


async def test_duplicate_aborts(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_setup_entry: AsyncMock
) -> None:
    """The same port and unit id cannot be set up twice."""
    mock_config_entry.add_to_hass(hass)
    with _patch_temporary_unit(_seeded()):
        flow_id = await _start_serial(hass)
        result = await hass.config_entries.flow.async_configure(
            flow_id, MOCK_SERIAL_INPUT
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_changes_port(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_setup_entry: AsyncMock
) -> None:
    """Reconfiguring onto another port updates the entry and its unique id."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    with _patch_temporary_unit(_seeded()):
        result = await mock_config_entry.start_reconfigure_flow(hass)
        assert result["type"] is FlowResultType.MENU
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "reconfigure_serial"}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**MOCK_SERIAL_INPUT, CONF_DEVICE: "/dev/ttyUSB1"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.unique_id == "/dev/ttyUSB1:1"
    assert mock_config_entry.data[CONF_DEVICE] == "/dev/ttyUSB1"
    assert mock_config_entry.data[CONF_MODEL] == "INMBSMHI001R000"


async def test_reconfigure_to_other_entry_port_aborts(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_setup_entry: AsyncMock
) -> None:
    """Two entries cannot end up on the same port and unit id."""
    mock_config_entry.add_to_hass(hass)
    other = MockConfigEntry(
        domain=DOMAIN,
        unique_id="/dev/ttyUSB1:1",
        data={**MOCK_SERIAL_ENTRY_DATA, CONF_DEVICE: "/dev/ttyUSB1"},
        title="INMBSMHI001R000",
    )
    other.add_to_hass(hass)
    with _patch_temporary_unit(_seeded()):
        result = await mock_config_entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "reconfigure_serial"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**MOCK_SERIAL_INPUT, CONF_DEVICE: "/dev/ttyUSB1"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_tcp_recovers_from_cannot_connect(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_setup_entry: AsyncMock
) -> None:
    """A failed probe during reconfigure shows the error, then the flow finishes."""
    mock_config_entry.add_to_hass(hass)
    connection = _seeded()
    connection.for_unit(1).fail_requests(ModbusTimeoutError())
    with _patch_temporary_unit(connection):
        result = await mock_config_entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "reconfigure_tcp"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**MOCK_TCP_INPUT, CONF_BAUDRATE: 9600}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}
        connection.for_unit(1).fail_requests(None)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**MOCK_TCP_INPUT, CONF_BAUDRATE: 9600}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.unique_id == "192.168.1.50:502:1"
    assert mock_config_entry.data[CONF_TYPE] == TYPE_TCP


def test_create_modbus_params_serial() -> None:
    """Serial entries map to 8N2 RTU parameters."""
    assert create_modbus_params(MOCK_SERIAL_ENTRY_DATA) == ModbusSerialParams(
        device="/dev/ttyUSB0", baudrate=9600, bytesize=8, parity="N", stopbits=2
    )


def test_create_modbus_params_multi() -> None:
    """Multi-unit TCP entries map to native Modbus TCP parameters."""
    assert create_modbus_params(MOCK_MULTI_ENTRY_DATA) == ModbusTcpParams(
        host="192.168.1.50", port=502
    )


async def test_reconfigure_onto_other_family_aborts(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_setup_entry: AsyncMock
) -> None:
    """A single-unit entry cannot be pointed at a multi-unit gateway."""
    mock_config_entry.add_to_hass(hass)
    with _patch_temporary_unit(_seeded(seed_multi_unit, present=(0,))):
        result = await mock_config_entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "reconfigure_tcp"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**MOCK_TCP_INPUT, CONF_BAUDRATE: 9600}
        )
        assert result["step_id"] == "model"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_MODEL: "INMBSMHI048O000"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert mock_config_entry.data[CONF_MODEL] == "INMBSMHI001R000"
