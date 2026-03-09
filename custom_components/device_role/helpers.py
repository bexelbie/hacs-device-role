# ABOUTME: Shared helpers for the device_role integration.
# ABOUTME: Resolves entity IDs from stored unique IDs to handle entity renames.

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_SOURCE_ENTITY_ID, CONF_SOURCE_UNIQUE_ID


def resolve_source_entity_id(
    hass: HomeAssistant, mapping: dict
) -> str:
    """Look up the current entity_id for a mapping's source_unique_id.

    Handles entity renames by searching the registry when the stored
    entity_id no longer matches the unique_id. Falls back to the stored
    entity_id if the unique_id is not found (e.g. entity was removed).
    """
    entity_reg = er.async_get(hass)
    source_uid = mapping.get(CONF_SOURCE_UNIQUE_ID)
    stored_entity_id = mapping[CONF_SOURCE_ENTITY_ID]

    if source_uid:
        # Fast path: check if stored entity_id still matches
        existing = entity_reg.async_get(stored_entity_id)
        if existing and existing.unique_id == source_uid:
            return stored_entity_id

        # Entity was renamed — search registry by unique_id
        for entry in entity_reg.entities.values():
            if entry.unique_id == source_uid:
                return entry.entity_id

    return stored_entity_id
