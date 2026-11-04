"""Tests for the Intesis Modbus integration."""

from collections.abc import Iterable

from modbus_connection.mock import MockModbusUnit

from homeassistant.components.intesis_modbus.const import (
    CONF_BAUDRATE,
    CONF_FRAMING,
    CONF_MODEL,
    CONF_TEMPERATURE_FORMAT,
    CONF_UNIT_ID,
    FRAMING_TCP,
    TYPE_SERIAL,
    TYPE_TCP,
)
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, CONF_TYPE

INIT_VALUE = 0x8000

MOCK_SERIAL_INPUT = {CONF_DEVICE: "/dev/ttyUSB0", CONF_BAUDRATE: 9600, CONF_UNIT_ID: 1}
MOCK_SERIAL_ENTRY_DATA = {
    CONF_TYPE: TYPE_SERIAL,
    **MOCK_SERIAL_INPUT,
    CONF_MODEL: "INMBSMHI001R000",
    CONF_TEMPERATURE_FORMAT: "decicelsius",
}
MOCK_TCP_INPUT = {
    CONF_HOST: "192.168.1.50",
    CONF_PORT: 502,
    CONF_UNIT_ID: 1,
    CONF_FRAMING: FRAMING_TCP,
}
MOCK_MULTI_ENTRY_DATA = {
    CONF_TYPE: TYPE_TCP,
    **MOCK_TCP_INPUT,
    CONF_MODEL: "INMBSMHI048O000",
}

# A healthy MHI single-unit gateway, DIP switches on x10 °C.
SINGLE_UNIT_REGISTERS: dict[int, int] = {
    0: 1,  # on
    1: 1,  # heat
    2: 2,  # medium
    3: 10,  # swing
    4: 215,  # setpoint 21.5 °C
    5: 203,  # ambient 20.3 °C
    6: 0,  # window contact closed
    7: 0,  # gateway enabled
    8: 0,  # remote control enabled
    9: 1234,  # operation hours
    10: 0,  # no alarm
    11: 0,  # no error
    13: 30,  # window timeout
    14: 2,  # baud rate code
    15: 1,  # slave address
    21: 4,  # four fan speeds
    22: INIT_VALUE,  # no external temperature
    23: 215,  # real setpoint
    24: 300,  # max setpoint
    25: 160,  # min setpoint
    31: 0,  # window closed
    46: 0,  # remote unlock
    48: 0x0012,  # switch value
    49: 0x0F00,  # MHI device id
    50: 0x0014,  # software version 20
    55: 3,  # undervoltage hours
    60: 125,  # outdoor intake 12.5 °C
    65: INIT_VALUE,  # no input reference
    66: 240,  # return path 24.0 °C
    81: 0,  # error address
    97: 0,  # periodic sendings not blocked
    98: 0,  # slave
}

_IDENTITY = {48, 49, 50}


def seed_single_unit(unit: MockModbusUnit) -> None:
    """Seed a healthy single-unit gateway."""
    for address, value in SINGLE_UNIT_REGISTERS.items():
        unit.holding[address] = value


def seed_initialising_single_unit(unit: MockModbusUnit) -> None:
    """Seed a single-unit gateway that is still initialising."""
    for address, value in SINGLE_UNIT_REGISTERS.items():
        unit.holding[address] = value if address in _IDENTITY else INIT_VALUE
    unit.holding[11] = 65532


UNIT_STRIDE = 20

# One healthy indoor unit of a multi-unit gateway, by block offset.
INDOOR_UNIT_BLOCK: dict[int, int] = {
    0: 0,  # communication OK
    1: 1,  # on
    2: 1,  # heat
    3: 22,  # setpoint 22 °C
    4: 1,  # medium
    5: 1,  # remote controller unlocked
    6: 0,  # swing
    7: 21,  # room 21 °C
    8: 0,  # filter sign off
    9: 0,  # no error
    10: 1,  # compressor on
    11: 0,
    12: 0,
    13: 1,  # thermo on
}


def seed_multi_unit(unit: MockModbusUnit, present: Iterable[int]) -> None:
    """Seed a multi-unit gateway with the given indoor units present."""
    present = set(present)
    for number in range(128):
        base = number * UNIT_STRIDE
        for offset in range(14):
            unit.holding[base + offset] = 0
        if number in present:
            for offset, value in INDOOR_UNIT_BLOCK.items():
                unit.holding[base + offset] = value
        else:
            unit.holding[base] = 1  # communication error
    unit.holding[2994] = 0
