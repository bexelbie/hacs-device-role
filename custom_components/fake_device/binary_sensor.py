# ABOUTME: Binary sensor platform for the fake_device integration.
# ABOUTME: Creates connectivity (and other) binary sensors with set_value support.

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import device_info_for_entry, register_entity
from .const import ENTITY_SPECS


class FakeBinarySensor(BinarySensorEntity):
    """A fake binary sensor with deterministic value control."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, spec: dict) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{spec['key']}"
        self._attr_name = spec["key"].replace("_", " ").title()
        self._attr_device_class = spec.get("device_class")
        self._attr_is_on = spec["initial"]
        self._force_unavailable = False

    @property
    def device_info(self):
        return device_info_for_entry(self._entry)

    @property
    def available(self) -> bool:
        return not self._force_unavailable

    async def async_added_to_hass(self) -> None:
        register_entity(self.hass, self._entry, self)

    @callback
    def set_value(self, value: Any) -> None:
        """Set the binary sensor to a bool value, or 'unavailable'."""
        if value == "unavailable":
            self._force_unavailable = True
        else:
            self._force_unavailable = False
            self._attr_is_on = bool(value)
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up fake binary sensor entities."""
    async_add_entities(
        FakeBinarySensor(entry, spec)
        for spec in ENTITY_SPECS
        if spec["domain"] == "binary_sensor"
    )
