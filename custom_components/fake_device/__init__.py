# ABOUTME: Integration setup for fake_device.
# ABOUTME: Registers platforms and the set_value service for deterministic control.

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PLATFORMS, SERVICE_SET_VALUE

_LOGGER = logging.getLogger(__name__)


def device_info_for_entry(entry: ConfigEntry) -> dict:
    """Build device_info shared by all entities of a fake device."""
    return {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "name": entry.data["name"],
        "manufacturer": "Fake Device Co",
        "model": "Multi-Sensor Plug",
    }


def register_entity(hass: HomeAssistant, entry: ConfigEntry, entity) -> None:
    """Register an entity so the set_value service can find it."""
    hass.data[DOMAIN][entry.entry_id]["entities"][entity.entity_id] = entity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a fake device from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"entities": {}}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.services.has_service(DOMAIN, SERVICE_SET_VALUE):
        async def handle_set_value(call: ServiceCall) -> None:
            """Set an entity to an exact value, or to unavailable/unknown."""
            entity_id = call.data["entity_id"]
            value = call.data["value"]

            for entry_data in hass.data[DOMAIN].values():
                if not isinstance(entry_data, dict):
                    continue
                entities = entry_data.get("entities", {})
                if entity_id in entities:
                    entities[entity_id].set_value(value)
                    return

            _LOGGER.warning(
                "fake_device.set_value: entity %s not found", entity_id
            )

        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_VALUE,
            handle_set_value,
            schema=vol.Schema(
                {
                    vol.Required("entity_id"): cv.string,
                    vol.Required("value"): vol.Any(
                        float, int, bool, str, None
                    ),
                }
            ),
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a fake device config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
