"""An entity class for mobile_app."""

from __future__ import annotations

from typing import Any

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ICON, CONF_NAME, CONF_UNIQUE_ID, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    ATTR_SENSOR_ATTRIBUTES,
    ATTR_SENSOR_DEVICE_CLASS,
    ATTR_SENSOR_DISABLED,
    ATTR_SENSOR_ENTITY_CATEGORY,
    ATTR_SENSOR_ICON,
    ATTR_SENSOR_STATE,
    ATTR_SENSOR_STATE_CLASS,
    DATA_PENDING_UPDATES,
    DOMAIN,
    SIGNAL_SENSOR_UPDATE,
)
from .helpers import device_info

from .coordinator import MobileAppCoordinator


_LOGGER = logging.getLogger(__name__)

class MobileAppEntity(CoordinatorEntity[MobileAppCoordinator], RestoreEntity):
    """Representation of a mobile app entity."""

    _attr_should_poll = False

    def __init__(self, coordinator: MobileAppCoordinator, config: dict, entry: ConfigEntry) -> None:
        """Initialize the mobile app entity.

        Args:
            coordinator: The coordinator managing sensor data updates from webhooks.
            config: Entity configuration containing sensor attributes, state, and metadata.
            entry: The config entry for this mobile app device.

        The entity subscribes to the coordinator for automatic updates when webhook
        data arrives. If coordinator data is already available for this entity's
        unique_id, it will be loaded immediately. Otherwise, the entity will wait
        for the first webhook update or restore from previous state.
        """
        super().__init__(coordinator=coordinator)

        unique_id = config[CONF_UNIQUE_ID]

        self._config = config
        self._entry = entry
        self._registration = entry.data
        self._attr_unique_id = unique_id
        self._attr_entity_registry_enabled_default = not config.get(
            ATTR_SENSOR_DISABLED
        )
        self._attr_name = config[CONF_NAME]

        _LOGGER.debug(
            "Initializing MobileAppEntity: %s for unique_id %s", self._attr_name, unique_id
        )

        _LOGGER.warning("Coordinator data on init: %s", coordinator.data)

        # entry.async_on_unload(
        #     coordinator.async_add_listener(self._handle_coordinator_update)
        # )

        if unique_id in coordinator.data:
            _LOGGER.debug(
                "Loading initial data for %s from coordinator", self._attr_name
            )
            self._config.update(coordinator.data[unique_id])

        self._async_update_attr_from_config()

    @callback
    def _async_update_attr_from_config(self) -> None:
        """Update the entity from the config."""
        config = self._config
        self._attr_device_class = config.get(ATTR_SENSOR_DEVICE_CLASS)
        self._attr_state_class = config.get(ATTR_SENSOR_STATE_CLASS)
        self._attr_extra_state_attributes = config[ATTR_SENSOR_ATTRIBUTES]
        self._attr_icon = config[ATTR_SENSOR_ICON]
        self._attr_entity_category = config.get(ATTR_SENSOR_ENTITY_CATEGORY)
        self._attr_available = config.get(ATTR_SENSOR_STATE) != STATE_UNAVAILABLE


    @callback
    def _handle_coordinator_update(self) -> None:
        """Call when the coordinator has an update."""

        _LOGGER.debug(
            "Handling coordinator update for %s", self._attr_name)

        if self._attr_unique_id not in self.coordinator.data:
            _LOGGER.debug(
                "No update data for %s in coordinator content: %s", self._attr_unique_id, self.coordinator.data
            )
            return
        data = self.coordinator.data[self._attr_unique_id]

        self._config.update(data)
        self._async_update_attr_from_config()


        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        await super().async_added_to_hass()
        _LOGGER.debug(
            "MobileAppEntity added to hass: %s and state %s", self._attr_name, self._attr_state)

        if (state := await self.async_get_last_state()) is None:
            return

        await self.async_restore_last_state(state)

    async def async_restore_last_state(self, last_state: State) -> None:
        """Restore previous state."""
        config = self._config

        _LOGGER.debug("Restoring last state: %s", last_state)

        if config[ATTR_SENSOR_STATE] is None or config[ATTR_SENSOR_STATE] == STATE_UNKNOWN:
            config[ATTR_SENSOR_STATE] = last_state.state
            config[ATTR_SENSOR_ATTRIBUTES] = {
                **last_state.attributes,
                **self._config[ATTR_SENSOR_ATTRIBUTES],
            }
            if ATTR_ICON in last_state.attributes:
                config[ATTR_SENSOR_ICON] = last_state.attributes[ATTR_ICON]

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this entity."""
        return device_info(self._registration)
