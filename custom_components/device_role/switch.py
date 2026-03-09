# ABOUTME: Switch platform for the device_role integration.
# ABOUTME: Creates role switch entities that mirror state and forward commands.

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_ACTIVE,
    CONF_DOMAIN,
    CONF_ENTITY_MAPPINGS,
    CONF_ROLE_NAME,
    CONF_SLOT,
    CONF_SOURCE_ENTITY_ID,
    DOMAIN,
)
from .helpers import resolve_source_entity_id

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device role switch entities from a config entry."""
    role_name = entry.data[CONF_ROLE_NAME]
    active = entry.data.get(CONF_ACTIVE, True)

    entities = []
    for mapping in entry.data.get(CONF_ENTITY_MAPPINGS, []):
        if mapping[CONF_DOMAIN] != "switch":
            continue

        source_entity_id = resolve_source_entity_id(hass, mapping)

        entities.append(
            RoleSwitch(
                entry=entry,
                role_name=role_name,
                slot=mapping[CONF_SLOT],
                source_entity_id=source_entity_id,
                active=active,
            )
        )

    async_add_entities(entities)


class RoleSwitch(SwitchEntity):
    """A role switch that mirrors state and forwards commands."""

    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(
        self,
        entry: ConfigEntry,
        role_name: str,
        slot: str,
        source_entity_id: str,
        active: bool,
    ) -> None:
        """Initialize the role switch."""
        self._entry = entry
        self._role_name = role_name
        self._slot = slot
        self._source_entity_id = source_entity_id
        self._active = active
        self._unsub_listener = None

        self._attr_unique_id = f"{entry.entry_id}_{slot}"
        self._attr_name = f"{role_name} {slot}".replace("_", " ").title()

    @property
    def device_info(self):
        """Return device info to group role entities under a role device."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._role_name,
            "manufacturer": "Device Role",
        }

    @property
    def available(self) -> bool:
        """Return True if the role is active."""
        return self._active

    async def async_added_to_hass(self) -> None:
        """Subscribe to source entity state changes."""
        if not self._active:
            return

        self._update_from_source()

        self._unsub_listener = async_track_state_change_event(
            self.hass, [self._source_entity_id], self._handle_source_change
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up the state change listener."""
        if self._unsub_listener:
            self._unsub_listener()
            self._unsub_listener = None

    @callback
    def _handle_source_change(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle source entity state changes."""
        self._update_from_source()
        self.async_write_ha_state()

    @callback
    def _update_from_source(self) -> None:
        """Update role switch from the source entity's current state."""
        source_state = self.hass.states.get(self._source_entity_id)
        if source_state is None or source_state.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            self._attr_is_on = None
            return

        self._attr_is_on = source_state.state == STATE_ON

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Forward turn_on to the physical switch."""
        if not self._active:
            return
        await self.hass.services.async_call(
            "switch",
            SERVICE_TURN_ON,
            {"entity_id": self._source_entity_id},
            blocking=True,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Forward turn_off to the physical switch."""
        if not self._active:
            return
        await self.hass.services.async_call(
            "switch",
            SERVICE_TURN_OFF,
            {"entity_id": self._source_entity_id},
            blocking=True,
        )
