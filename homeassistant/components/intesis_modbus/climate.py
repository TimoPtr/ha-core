"""Climate entity for the air conditioner(s) behind an Intesis gateway."""

from dataclasses import dataclass
from typing import Any, Final, override

from intesis_gw_modbus import (
    AirConditioner,
    FanSpeed,
    GatewayFamily,
    IndoorUnitView,
    IntesisSingleUnitGateway,
    Mode,
    VanePosition,
)

from homeassistant.components.climate import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IntesisConfigEntry, IntesisCoordinator
from .entity import IntesisEntity, IntesisEntityDescription

PARALLEL_UPDATES = 1

MODE_TO_HVAC: Final = {
    Mode.AUTO: HVACMode.AUTO,
    Mode.HEAT: HVACMode.HEAT,
    Mode.DRY: HVACMode.DRY,
    Mode.FAN: HVACMode.FAN_ONLY,
    Mode.COOL: HVACMode.COOL,
}
HVAC_TO_MODE: Final = {hvac: mode for mode, hvac in MODE_TO_HVAC.items()}

FAN_TO_HA: Final = {
    FanSpeed.AUTO: FAN_AUTO,
    FanSpeed.LOW: FAN_LOW,
    FanSpeed.MEDIUM: FAN_MEDIUM,
    FanSpeed.HIGH: FAN_HIGH,
    FanSpeed.POWERFUL: "powerful",
}
HA_TO_FAN: Final = {name: speed for speed, name in FAN_TO_HA.items()}

VANE_TO_HA: Final = {position: position.value for position in VanePosition}
HA_TO_VANE: Final = {name: position for position, name in VANE_TO_HA.items()}

MODE_TO_ACTION: Final = {
    Mode.HEAT: HVACAction.HEATING,
    Mode.COOL: HVACAction.COOLING,
    Mode.DRY: HVACAction.DRYING,
    Mode.AUTO: HVACAction.IDLE,
}


@dataclass(frozen=True, kw_only=True)
class IntesisClimateEntityDescription(
    ClimateEntityDescription, IntesisEntityDescription
):
    """Describe an Intesis climate entity."""


CLIMATE_DESCRIPTION: Final = IntesisClimateEntityDescription(
    key="air_conditioner",
    translation_key="air_conditioner",
    name=None,
    report_name="control",
)
INDOOR_UNIT_CLIMATE_DESCRIPTION: Final = IntesisClimateEntityDescription(
    key="air_conditioner",
    translation_key="air_conditioner",
    name=None,
    report_name="units",
    families=frozenset({GatewayFamily.MULTI_UNIT}),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntesisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one climate entity per air conditioner the gateway controls."""
    runtime_data = entry.runtime_data
    coordinator = runtime_data.coordinator
    device = runtime_data.device
    if isinstance(device, IntesisSingleUnitGateway):
        async_add_entities([IntesisClimate(coordinator, device, CLIMATE_DESCRIPTION)])
        return
    async_add_entities(
        IntesisClimate(
            coordinator, unit, INDOOR_UNIT_CLIMATE_DESCRIPTION, indoor_unit=unit
        )
        for _, unit in sorted(device.indoor_units.items())
    )


class IntesisClimate(IntesisEntity, ClimateEntity):
    """One air conditioner behind an Intesis gateway."""

    entity_description: IntesisClimateEntityDescription
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: IntesisCoordinator,
        ac: AirConditioner,
        description: IntesisClimateEntityDescription,
        *,
        indoor_unit: IndoorUnitView | None = None,
    ) -> None:
        """Bind to the air conditioner the entity controls."""
        super().__init__(coordinator, description, indoor_unit=indoor_unit)
        self._ac = ac

    @property
    @override
    def hvac_modes(self) -> list[HVACMode]:
        return [HVACMode.OFF, *(MODE_TO_HVAC[m] for m in self._ac.available_modes)]

    @property
    @override
    def hvac_mode(self) -> HVACMode | None:
        if (power := self._ac.power) is None:
            return None
        if not power:
            return HVACMode.OFF
        if (mode := self._ac.mode) is None:
            return None
        return MODE_TO_HVAC[mode]

    @property
    @override
    def hvac_action(self) -> HVACAction | None:
        if not isinstance(self._ac, IndoorUnitView):
            return None
        if (power := self._ac.power) is None or (mode := self._ac.mode) is None:
            return None
        if not power:
            return HVACAction.OFF
        if mode is Mode.FAN:
            return HVACAction.FAN
        running = self._ac.compressor_on or self._ac.thermo_on
        return MODE_TO_ACTION[mode] if running else HVACAction.IDLE

    @property
    @override
    def fan_modes(self) -> list[str]:
        return [FAN_TO_HA[s] for s in self._ac.available_fan_speeds]

    @property
    @override
    def fan_mode(self) -> str | None:
        speed = self._ac.fan_speed
        return None if speed is None else FAN_TO_HA[speed]

    @property
    @override
    def swing_modes(self) -> list[str]:
        return [VANE_TO_HA[p] for p in self._ac.available_vane_positions]

    @property
    @override
    def swing_mode(self) -> str | None:
        vane = self._ac.vane
        return None if vane is None else VANE_TO_HA[vane]

    @property
    @override
    def native_target_temperature(self) -> float | None:
        return self._ac.setpoint

    @property
    @override
    def native_current_temperature(self) -> float | None:
        return self._ac.current_temperature

    @property
    @override
    def min_temp(self) -> float:
        return self._ac.setpoint_min

    @property
    @override
    def max_temp(self) -> float:
        return self._ac.setpoint_max

    @property
    @override
    def target_temperature_step(self) -> float:
        return self._ac.setpoint_step

    @override
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode is HVACMode.OFF:
            await self._async_write(lambda: self._ac.async_set_power(False))
            return

        async def _set_mode_and_power_on() -> None:
            await self._ac.async_set_mode(HVAC_TO_MODE[hvac_mode])
            if self._ac.power is not True:
                await self._ac.async_set_power(True)

        await self._async_write(_set_mode_and_power_on)

    @override
    async def async_turn_on(self) -> None:
        await self._async_write(lambda: self._ac.async_set_power(True))

    @override
    async def async_turn_off(self) -> None:
        await self._async_write(lambda: self._ac.async_set_power(False))

    @override
    async def async_set_fan_mode(self, fan_mode: str) -> None:
        speed = HA_TO_FAN[fan_mode]
        await self._async_write(lambda: self._ac.async_set_fan_speed(speed))

    @override
    async def async_set_swing_mode(self, swing_mode: str) -> None:
        position = HA_TO_VANE[swing_mode]
        await self._async_write(lambda: self._ac.async_set_vane(position))

    @override
    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature: float = kwargs[ATTR_TEMPERATURE]
        await self._async_write(lambda: self._ac.async_set_setpoint(temperature))
