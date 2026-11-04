"""Tests for the Intesis Modbus integration setup."""

from homeassistant.components.intesis_modbus.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration


async def test_manifest_loads(hass: HomeAssistant) -> None:
    """The integration manifest declares what the quality scale needs."""
    integration = await async_get_integration(hass, DOMAIN)
    assert integration.quality_scale == "platinum"
    assert "modbus" in integration.dependencies
