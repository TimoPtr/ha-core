from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)

from .const import DOMAIN

from typing import Any

import logging
from dataclasses import dataclass
from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

@dataclass
class MobileAppData:
    """Data for Mobile App integration."""

    coordinator: MobileAppCoordinator

type MobileAppConfigEntry = ConfigEntry[MobileAppData]


class MobileAppCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for Mobile App integration."""

    def __init__(self, hass: HomeAssistant, config_entry: MobileAppConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            name=DOMAIN,
            logger=_LOGGER,
            # The app is pushing data, no polling needed
            update_interval=None,
            update_method=None,
            config_entry=config_entry,
        )
        self.data: dict[str, Any] = {}
