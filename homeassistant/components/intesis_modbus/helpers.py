"""Helpers shared by the config flow and the entry setup."""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from intesis_gw_modbus import (
    MODELS,
    GatewayFamily,
    IntesisMultiUnitGateway,
    IntesisSingleUnitGateway,
    TemperatureFormat,
)
from modbus_connection import ModbusSerialParams, ModbusTcpParams, ModbusUnit

from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, CONF_TYPE

from .const import (
    CONF_BAUDRATE,
    CONF_FRAMING,
    CONF_MODEL,
    CONF_TEMPERATURE_FORMAT,
    CONF_UNIT_ID,
    DEFAULT_BAUDRATE,
    FRAMING_RTU_OVER_TCP,
    TYPE_SERIAL,
)

type IntesisDevice = IntesisSingleUnitGateway | IntesisMultiUnitGateway


def create_modbus_params(
    data: Mapping[str, Any],
) -> ModbusSerialParams | ModbusTcpParams:
    """Build the Modbus link parameters from config entry data."""
    if data[CONF_TYPE] == TYPE_SERIAL:
        return ModbusSerialParams(
            device=data[CONF_DEVICE],
            baudrate=data[CONF_BAUDRATE],
            bytesize=8,
            parity="N",
            stopbits=2,
        )
    if data[CONF_FRAMING] == FRAMING_RTU_OVER_TCP:
        return ModbusSerialParams(
            device=f"socket://{data[CONF_HOST]}:{data[CONF_PORT]}",
            baudrate=data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
            bytesize=8,
            parity="N",
            stopbits=2,
        )
    return ModbusTcpParams(host=data[CONF_HOST], port=data[CONF_PORT])


def unique_id_for(data: Mapping[str, Any]) -> str:
    """Return the unique id of the gateway these link settings reach."""
    if data[CONF_TYPE] == TYPE_SERIAL:
        return f"{data[CONF_DEVICE]}:{data[CONF_UNIT_ID]}"
    return f"{data[CONF_HOST]}:{data[CONF_PORT]}:{data[CONF_UNIT_ID]}"


def create_device(unit: ModbusUnit, data: Mapping[str, Any]) -> IntesisDevice:
    """Build the library device the entry data describes."""
    model = MODELS[data[CONF_MODEL]]
    if model.family is GatewayFamily.SINGLE_UNIT:
        return IntesisSingleUnitGateway(
            unit,
            brand=model.brand,
            temperature_format=TemperatureFormat(data[CONF_TEMPERATURE_FORMAT]),
        )
    if TYPE_CHECKING:
        assert model.unit_count is not None
    return IntesisMultiUnitGateway(unit, brand=model.brand, unit_count=model.unit_count)
