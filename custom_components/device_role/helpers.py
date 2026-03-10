# ABOUTME: Shared helpers for the device_role integration.
# ABOUTME: Resolves entity IDs, builds device info, and links role devices to physical devices.

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import CONF_SOURCE_ENTITY_ID, CONF_SOURCE_UNIQUE_ID, DOMAIN


def resolve_via_device(hass: HomeAssistant, device_id: str) -> tuple | None:
    """Look up a physical device's primary identifier for via_device linking."""
    device_reg = dr.async_get(hass)
    physical = device_reg.async_get(device_id)
    if physical and physical.identifiers:
        return next(iter(physical.identifiers))
    return None


def build_role_device_info(
    entry_id: str, role_name: str, via_device_id: tuple | None = None,
) -> dict:
    """Build device_info dict for a role entity."""
    info: dict = {
        "identifiers": {(DOMAIN, entry_id)},
        "name": role_name,
        "manufacturer": "Device Role",
    }
    if via_device_id is not None:
        info["via_device"] = via_device_id
    return info


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
