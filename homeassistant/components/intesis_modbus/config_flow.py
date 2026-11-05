"""Config flow for the Intesis Modbus integration."""

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any, override

from intesis_gw_modbus import (
    KNOWN_DEVICE_IDS,
    MODELS,
    GatewayFamily,
    GatewayModel,
    TemperatureFormat,
    detect_temperature_format,
    model_for_device_id,
)
from modbus_connection import ModbusError, ModbusExceptionError, ModbusUnit
import probatio

from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    SerialPortSelector,
    TextSelector,
)

from .const import (
    CONF_BAUDRATE,
    CONF_FRAMING,
    CONF_HAS_VANE,
    CONF_MODEL,
    CONF_TEMPERATURE_FORMAT,
    CONF_UNIT_ID,
    DEFAULT_BAUDRATE,
    DEFAULT_PORT,
    DEFAULT_UNIT_ID,
    DOMAIN,
    FRAMING_RTU_OVER_TCP,
    FRAMING_TCP,
    TYPE_SERIAL,
    TYPE_TCP,
)
from .helpers import create_modbus_params, unique_id_for

_LOGGER = logging.getLogger(__name__)

STEP_MODEL = "model"
STEP_TEMPERATURE_FORMAT = "temperature_format"
STEP_FEATURES = "features"
STEP_RECONFIGURE_SERIAL = "reconfigure_serial"
STEP_RECONFIGURE_TCP = "reconfigure_tcp"

DEVICE_ID_REGISTER = 49
SETPOINT_REGISTER = 4
VANE_REGISTER = 3

UNIT_ID_SELECTOR = probatio.All(
    NumberSelector(NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=247)),
    probatio.Coerce(int),
)
BAUDRATE_SELECTOR = probatio.All(
    NumberSelector(NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1)),
    probatio.Coerce(int),
)

STEP_SERIAL_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_DEVICE): SerialPortSelector(),
        probatio.Required(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): BAUDRATE_SELECTOR,
        probatio.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): UNIT_ID_SELECTOR,
    }
)

STEP_TCP_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_HOST): TextSelector(),
        probatio.Required(CONF_PORT, default=DEFAULT_PORT): probatio.All(
            NumberSelector(
                NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=65535)
            ),
            probatio.Coerce(int),
        ),
        probatio.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): UNIT_ID_SELECTOR,
        probatio.Required(CONF_FRAMING, default=FRAMING_TCP): SelectSelector(
            SelectSelectorConfig(
                options=[FRAMING_TCP, FRAMING_RTU_OVER_TCP],
                translation_key="framing",
                mode=SelectSelectorMode.LIST,
            )
        ),
        probatio.Required(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): BAUDRATE_SELECTOR,
    }
)

STEP_MODEL_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_MODEL): SelectSelector(
            SelectSelectorConfig(
                options=sorted(MODELS), mode=SelectSelectorMode.DROPDOWN
            )
        ),
    }
)

STEP_TEMPERATURE_FORMAT_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(
            CONF_TEMPERATURE_FORMAT, default=TemperatureFormat.DECICELSIUS.value
        ): SelectSelector(
            SelectSelectorConfig(
                options=[fmt.value for fmt in TemperatureFormat],
                translation_key="temperature_format",
                mode=SelectSelectorMode.LIST,
            )
        ),
    }
)


STEP_FEATURES_DATA_SCHEMA = probatio.Schema(
    {probatio.Required(CONF_HAS_VANE, default=True): BooleanSelector()}
)


@dataclass(frozen=True)
class ProbeResult:
    """What a gateway answered when asked who it is."""

    device_id: int | None
    raw_setpoint: int | None
    raw_vane: int | None


async def _async_read_or_none(unit: ModbusUnit, address: int) -> int | None:
    """Read one holding register, or None if the gateway refuses the address."""
    try:
        [value] = await unit.read_holding_registers(address, 1)
    except ModbusExceptionError:
        return None
    return value


async def _async_probe(hass: HomeAssistant, data: dict[str, Any]) -> ProbeResult:
    """Ask the gateway for its device id and raw setpoint, or raise."""
    params = create_modbus_params(data)
    async with async_get_temporary_unit(hass, params, data[CONF_UNIT_ID]) as unit:
        device_id = await _async_read_or_none(unit, DEVICE_ID_REGISTER)
        raw_setpoint = await _async_read_or_none(unit, SETPOINT_REGISTER)
        raw_vane = await _async_read_or_none(unit, VANE_REGISTER)
    return ProbeResult(device_id, raw_setpoint, raw_vane)


class IntesisModbusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle an Intesis Modbus config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._link: dict[str, Any] = {}
        self._probe = ProbeResult(None, None, None)
        self._pending: dict[str, Any] = {}
        self._model: GatewayModel | None = None

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick how the gateway is reached."""
        return self.async_show_menu(
            step_id="user", menu_options=[TYPE_SERIAL, TYPE_TCP]
        )

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a gateway reached over a serial port."""
        return await self._async_step_link(
            TYPE_SERIAL, TYPE_SERIAL, STEP_SERIAL_DATA_SCHEMA, user_input
        )

    async def async_step_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a gateway reached over the network."""
        return await self._async_step_link(
            TYPE_TCP, TYPE_TCP, STEP_TCP_DATA_SCHEMA, user_input
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick how the gateway is reached from now on."""
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=[STEP_RECONFIGURE_SERIAL, STEP_RECONFIGURE_TCP],
        )

    async def async_step_reconfigure_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reach this gateway over a serial port from now on."""
        return await self._async_step_link(
            STEP_RECONFIGURE_SERIAL, TYPE_SERIAL, STEP_SERIAL_DATA_SCHEMA, user_input
        )

    async def async_step_reconfigure_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reach this gateway over the network from now on."""
        return await self._async_step_link(
            STEP_RECONFIGURE_TCP, TYPE_TCP, STEP_TCP_DATA_SCHEMA, user_input
        )

    async def _async_step_link(
        self,
        step_id: str,
        connection_type: str,
        schema: probatio.Schema,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """Ask for the link settings, then probe the gateway behind them."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}
        if user_input is not None:
            self._link = {CONF_TYPE: connection_type, **user_input}
            if self.source != SOURCE_RECONFIGURE:
                await self.async_set_unique_id(unique_id_for(self._link))
                self._abort_if_unique_id_configured()
            try:
                self._probe = await _async_probe(self.hass, self._link)
            except (ModbusError, HomeAssistantError) as err:
                errors["base"] = "cannot_connect"
                description_placeholders["error"] = str(err)
            else:
                if (
                    brand := KNOWN_DEVICE_IDS.get(self._probe.device_id or -1)
                ) is not None:
                    return self.async_abort(
                        reason="unsupported_brand",
                        description_placeholders={"brand": brand},
                    )
                if (model := model_for_device_id(self._probe.device_id or -1)) is None:
                    return await self.async_step_model()
                return await self._async_finish(model)

        suggested = user_input
        if suggested is None and self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            if entry.data[CONF_TYPE] == connection_type:
                suggested = dict(entry.data)
            else:
                suggested = {CONF_UNIT_ID: entry.data[CONF_UNIT_ID]}
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_model(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which gateway this is when its registers do not say."""
        errors: dict[str, str] = {}
        if user_input is not None:
            model = MODELS[user_input[CONF_MODEL]]
            probed = self._probe.device_id
            if (
                model.family is GatewayFamily.SINGLE_UNIT
                and probed is not None
                and model.brand.device_id != probed
            ):
                errors["base"] = "wrong_model"
            else:
                return await self._async_finish(model)
        return self.async_show_form(
            step_id=STEP_MODEL, data_schema=STEP_MODEL_DATA_SCHEMA, errors=errors
        )

    async def async_step_temperature_format(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the DIP-switch temperature format when it cannot be detected."""
        if user_input is not None:
            self._pending[CONF_TEMPERATURE_FORMAT] = user_input[CONF_TEMPERATURE_FORMAT]
            return await self.async_step_features()
        return self.async_show_form(
            step_id=STEP_TEMPERATURE_FORMAT,
            data_schema=STEP_TEMPERATURE_FORMAT_DATA_SCHEMA,
        )

    async def async_step_features(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm what the unit behind the gateway can do.

        The gateway has no capability register for the vane, so the probe's
        reading of register 3 only pre-fills the answer.
        """
        if user_input is not None:
            return self._async_create_or_update(
                {**self._pending, CONF_HAS_VANE: user_input[CONF_HAS_VANE]}
            )
        if self.source == SOURCE_RECONFIGURE:
            has_vane = self._get_reconfigure_entry().data.get(CONF_HAS_VANE, True)
        else:
            if TYPE_CHECKING:
                assert self._model is not None
            has_vane = self._probe.raw_vane in self._model.brand.vane_positions
        return self.async_show_form(
            step_id=STEP_FEATURES,
            data_schema=self.add_suggested_values_to_schema(
                STEP_FEATURES_DATA_SCHEMA, {CONF_HAS_VANE: has_vane}
            ),
        )

    async def _async_finish(self, model: GatewayModel) -> ConfigFlowResult:
        """Settle format and features for a single-unit gateway, then finish."""
        data = {**self._link, CONF_MODEL: model.name}
        if model.family is not GatewayFamily.SINGLE_UNIT:
            return self._async_create_or_update(data)
        self._model = model
        self._pending = data
        fmt = detect_temperature_format(self._probe.raw_setpoint)
        if fmt is None:
            return await self.async_step_temperature_format()
        data[CONF_TEMPERATURE_FORMAT] = fmt.value
        return await self.async_step_features()

    def _async_create_or_update(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Create the entry, or update the one being reconfigured."""
        title = data[CONF_MODEL]
        if self.source != SOURCE_RECONFIGURE:
            return self.async_create_entry(title=title, data=data)
        entry = self._get_reconfigure_entry()
        if data[CONF_MODEL] != entry.data[CONF_MODEL]:
            return self.async_abort(reason="wrong_device")
        unique_id = unique_id_for(data)
        for other in self._async_current_entries():
            if other.entry_id != entry.entry_id and other.unique_id == unique_id:
                return self.async_abort(reason="already_configured")
        return self.async_update_reload_and_abort(
            entry, data=data, unique_id=unique_id, title=title
        )
