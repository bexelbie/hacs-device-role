# ABOUTME: Sensor platform for the device_role integration.
# ABOUTME: Creates role sensor entities that mirror physical measurement and energy sensors.

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device role sensor entities from a config entry."""
