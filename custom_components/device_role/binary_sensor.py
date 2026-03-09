# ABOUTME: Binary sensor platform for the device_role integration.
# ABOUTME: Creates role binary sensor entities that mirror physical binary sensors.

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device role binary sensor entities from a config entry."""
