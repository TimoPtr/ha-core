"""Constants for the Intesis Modbus integration."""

from typing import Final

DOMAIN: Final = "intesis_modbus"
MANUFACTURER: Final = "Intesis (HMS Networks)"

CONF_UNIT_ID: Final = "unit_id"
CONF_BAUDRATE: Final = "baudrate"
CONF_MODEL: Final = "model"
CONF_TEMPERATURE_FORMAT: Final = "temperature_format"
CONF_FRAMING: Final = "framing"

TYPE_SERIAL: Final = "serial"
TYPE_TCP: Final = "tcp"

FRAMING_TCP: Final = "tcp"
FRAMING_RTU_OVER_TCP: Final = "rtu_over_tcp"

DEFAULT_BAUDRATE: Final = 9600
DEFAULT_PORT: Final = 502
DEFAULT_UNIT_ID: Final = 1
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 300

BAUDRATES: Final = (2400, 4800, 9600, 19200, 38400, 57600, 76800, 115200)
