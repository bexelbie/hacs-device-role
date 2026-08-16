# ABOUTME: Shared helpers for the device_role integration.
# ABOUTME: Resolves entity IDs, builds device info, and links role devices to physical devices.

from collections.abc import Mapping

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.issue_registry import IssueSeverity

from .const import (
    CONF_DEVICE_ID,
    CONF_ENTITY_MAPPINGS,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_UNIQUE_ID,
    DEVICE_SPLIT_ISSUE,
    DOMAIN,
)


def resolve_via_device(hass: HomeAssistant, device_id: str) -> str | None:
    """Return a registered concrete device ID for via_device_id linking."""
    device_reg = dr.async_get(hass)
    if not device_id or device_reg.async_is_composite_device_id(device_id) is True:
        return None
    physical = device_reg.async_get(device_id)
    if not isinstance(physical, dr.DeviceEntry):
        return None
    return physical.id


def build_role_device_info(
    entry_id: str, role_name: str, via_device_id: str | None = None,
) -> dict:
    """Build device_info dict for a role entity."""
    info: dict = {
        "identifiers": {(DOMAIN, entry_id)},
        "name": role_name,
        "manufacturer": "Device Role",
    }
    if via_device_id is not None:
        info["via_device_id"] = via_device_id
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


def canonicalize_role_device(
    hass: HomeAssistant,
    entry_id: str,
    role_name: str,
    data: Mapping[str, object],
) -> str | None:
    """Replace a split composite source ID with one unambiguous concrete device ID."""
    stored_device_id = data.get(CONF_DEVICE_ID)
    if not isinstance(stored_device_id, str) or not stored_device_id:
        return None

    device_reg = dr.async_get(hass)
    if device_reg.async_is_composite_device_id(stored_device_id) is not True:
        ir.async_delete_issue(hass, DOMAIN, f"{DEVICE_SPLIT_ISSUE}_{entry_id}")
        return stored_device_id

    entity_reg = er.async_get(hass)
    source_device_ids: set[str] = set()
    for mapping in data.get(CONF_ENTITY_MAPPINGS, []):
        if not isinstance(mapping, Mapping):
            continue
        source_entity_id = resolve_source_entity_id(hass, mapping)
        source_entry = entity_reg.async_get(source_entity_id)
        source_device_id = source_entry.device_id if source_entry else None
        if (
            source_device_id
            and device_reg.async_get(source_device_id) is not None
            and device_reg.async_is_composite_device_id(source_device_id) is not True
        ):
            source_device_ids.add(source_device_id)

    issue_id = f"{DEVICE_SPLIT_ISSUE}_{entry_id}"
    if len(source_device_ids) == 1:
        concrete_device_id = next(iter(source_device_ids))
        new_data = dict(data)
        new_data[CONF_DEVICE_ID] = concrete_device_id
        hass.config_entries.async_update_entry(
            hass.config_entries.async_get_entry(entry_id),
            data=new_data,
        )
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return concrete_device_id

    role_device = device_reg.async_get_device_by_identifier(
        (DOMAIN, entry_id), entry_id
    )
    if role_device is not None and role_device.via_device_id is not None:
        device_reg.async_update_device(role_device.id, via_device_id=None)

    if len(source_device_ids) > 1:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            translation_key=DEVICE_SPLIT_ISSUE,
            translation_placeholders={"role_name": role_name},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    return stored_device_id
