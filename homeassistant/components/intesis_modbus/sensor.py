"""Sensors for the registers an Intesis gateway reports."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final, override

from intesis_gw_modbus import (
    ControlLock,
    ErrorInfo,
    ErrorState,
    IndoorUnitView,
    IntesisSingleUnitGateway,
)

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import IntesisConfigEntry, IntesisCoordinator
from .entity import MULTI_UNIT_ONLY, IntesisEntity, IntesisEntityDescription

PARALLEL_UPDATES = 1

ERROR_STATES: Final = [state.value for state in ErrorState]
CONTROL_LOCK_STATES: Final = [lock.value for lock in ControlLock]


def _error_state(error: ErrorInfo | None) -> StateType:
    return None if error is None else error.state.value


def _error_attributes(error: ErrorInfo | None) -> dict[str, Any]:
    return {
        "code": None if error is None else error.code,
        "remote_controller_code": None if error is None else error.remote_code,
        "description": None if error is None else error.description,
    }


@dataclass(frozen=True, kw_only=True)
class IntesisSensorDescription[TargetT](
    SensorEntityDescription, IntesisEntityDescription
):
    """Describe a sensor read off the gateway, or off one of its indoor units."""

    value_fn: Callable[[TargetT], StateType]
    attributes_fn: Callable[[TargetT], Mapping[str, Any]] | None = None


def _temperature(
    key: str,
    report_name: str,
    value_fn: Callable[[IntesisSingleUnitGateway], float | None],
    *,
    diagnostic: bool = False,
    enabled: bool = True,
    state_class: SensorStateClass | None = None,
) -> IntesisSensorDescription[IntesisSingleUnitGateway]:
    return IntesisSensorDescription(
        key=key,
        translation_key=key,
        report_name=report_name,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=state_class,
        entity_category=EntityCategory.DIAGNOSTIC if diagnostic else None,
        entity_registry_enabled_default=enabled,
        value_fn=value_fn,
    )


SENSORS: Final[tuple[IntesisSensorDescription[IntesisSingleUnitGateway], ...]] = (
    _temperature(
        "ambient_temperature",
        "control",
        lambda d: d.current_temperature,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    _temperature("real_setpoint", "limits", lambda d: d.real_setpoint),
    _temperature(
        "outdoor_intake_temperature",
        "temperatures",
        lambda d: d.outdoor_intake_temperature,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    _temperature(
        "input_reference_temperature",
        "temperatures",
        lambda d: d.input_reference_temperature,
        diagnostic=True,
        enabled=False,
    ),
    _temperature(
        "return_path_temperature",
        "temperatures",
        lambda d: d.return_path_temperature,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    _temperature(
        "setpoint_min",
        "limits",
        lambda d: d.setpoint_min,
        diagnostic=True,
        enabled=False,
    ),
    _temperature(
        "setpoint_max",
        "limits",
        lambda d: d.setpoint_max,
        diagnostic=True,
        enabled=False,
    ),
    IntesisSensorDescription(
        key="error",
        translation_key="error",
        report_name="control",
        device_class=SensorDeviceClass.ENUM,
        options=ERROR_STATES,
        value_fn=lambda d: _error_state(d.error),
        attributes_fn=lambda d: {
            **_error_attributes(d.error),
            "error_address": d.error_address,
        },
    ),
    IntesisSensorDescription(
        key="operation_hours",
        translation_key="operation_hours",
        report_name="control",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.operation_hours,
    ),
    IntesisSensorDescription(
        key="undervoltage_hours",
        translation_key="undervoltage_hours",
        report_name="diagnostics",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.undervoltage_hours,
    ),
    IntesisSensorDescription(
        key="control_lock",
        translation_key="control_lock",
        report_name="lock",
        device_class=SensorDeviceClass.ENUM,
        options=CONTROL_LOCK_STATES,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: None if d.control_lock is None else d.control_lock.value,
    ),
    IntesisSensorDescription(
        key="fan_speed_count",
        translation_key="fan_speed_count",
        report_name="limits",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.max_fan_speeds,
    ),
)

INDOOR_UNIT_SENSORS: Final[tuple[IntesisSensorDescription[IndoorUnitView], ...]] = (
    IntesisSensorDescription(
        key="error",
        translation_key="error",
        report_name="units",
        families=MULTI_UNIT_ONLY,
        device_class=SensorDeviceClass.ENUM,
        options=ERROR_STATES,
        value_fn=lambda u: _error_state(u.error),
        attributes_fn=lambda u: _error_attributes(u.error),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntesisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors the gateway family offers."""
    runtime_data = entry.runtime_data
    coordinator = runtime_data.coordinator
    device = runtime_data.device
    if isinstance(device, IntesisSingleUnitGateway):
        async_add_entities(
            (
                IntesisTotalSensor
                if description.state_class is SensorStateClass.TOTAL_INCREASING
                else IntesisSensor
            )(coordinator, device, description)
            for description in SENSORS
        )
        return
    async_add_entities(
        IntesisSensor(coordinator, unit, description, indoor_unit=unit)
        for number, unit in sorted(device.indoor_units.items())
        for description in INDOOR_UNIT_SENSORS
    )


class IntesisSensor[TargetT](IntesisEntity, SensorEntity):
    """A value read off the gateway or one of its indoor units."""

    entity_description: IntesisSensorDescription[TargetT]

    def __init__(
        self,
        coordinator: IntesisCoordinator,
        target: TargetT,
        description: IntesisSensorDescription[TargetT],
        *,
        indoor_unit: IndoorUnitView | None = None,
    ) -> None:
        """Bind to the object the description reads."""
        super().__init__(coordinator, description, indoor_unit=indoor_unit)
        self._target: TargetT = target

    @property
    @override
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self._target)

    @property
    @override
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        if (attributes_fn := self.entity_description.attributes_fn) is None:
            return None
        return attributes_fn(self._target)


class IntesisTotalSensor(IntesisEntity, RestoreSensor):
    """A long-term counter: restores its last value across restarts."""

    entity_description: IntesisSensorDescription[IntesisSingleUnitGateway]

    def __init__(
        self,
        coordinator: IntesisCoordinator,
        device: IntesisSingleUnitGateway,
        description: IntesisSensorDescription[IntesisSingleUnitGateway],
    ) -> None:
        """Bind to the gateway the description reads."""
        super().__init__(coordinator, description)
        self._device = device

    @override
    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last.native_value
        self._process_data()

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        self._process_data()
        super()._handle_coordinator_update()

    def _process_data(self) -> None:
        """Take the gateway's value when its block answered."""
        if self.entity_description.report_name not in self.coordinator.data.updated:
            return
        if (value := self.entity_description.value_fn(self._device)) is not None:
            self._attr_native_value = value
