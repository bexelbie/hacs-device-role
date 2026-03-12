# ABOUTME: Shared role-management helpers for services and config flows.
# ABOUTME: Validates mappings, serializes roles, preserves logical identity, and builds compatible config entries.

from __future__ import annotations

import inspect

from collections.abc import Mapping, Sequence
from types import MappingProxyType

from homeassistant.config_entries import ConfigEntry, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_ACTIVE,
    CONF_DEVICE_CLASS,
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_MAPPINGS,
    CONF_ROLE_NAME,
    CONF_SLOT,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_UNIQUE_ID,
    CONF_STATE_CLASS,
    DOMAIN,
    PLATFORMS,
)

SUPPORTED_DOMAINS = set(PLATFORMS)
_CONFIG_ENTRY_SUPPORTS_SUBENTRIES = (
    "subentries_data" in inspect.signature(ConfigEntry).parameters
)


class RoleManagerError(Exception):
    """Error raised when role management validation fails."""

    def __init__(self, code: str, message: str) -> None:
        """Initialize the error."""
        super().__init__(message)
        self.code = code
        self.message = message


def describe_registry_entry(entry: er.RegistryEntry) -> str:
    """Build a human-readable description for an entity registry entry."""
    return (
        f"{entry.original_name or entry.entity_id}"
        f" ({entry.domain}"
        f"{', ' + entry.original_device_class if entry.original_device_class else ''})"
    )


def get_device_role_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    """Return all device_role config entries."""
    return hass.config_entries.async_entries(DOMAIN)


def get_device_role_entry(
    hass: HomeAssistant, config_entry_id: str
) -> ConfigEntry:
    """Return a device_role config entry or raise."""
    entry = hass.config_entries.async_get_entry(config_entry_id)
    if entry is None:
        raise RoleManagerError(
            "config_entry_not_found",
            f"Role config entry '{config_entry_id}' was not found.",
        )
    if entry.domain != DOMAIN:
        raise RoleManagerError(
            "wrong_domain",
            f"Config entry '{config_entry_id}' does not belong to {DOMAIN}.",
        )
    return entry


def create_device_role_entry(
    role_name: str,
    device_id: str,
    mappings: list[dict],
    *,
    active: bool = True,
) -> ConfigEntry:
    """Build a device_role config entry using the available HA constructor fields."""
    entry_kwargs: dict[str, object] = {
        "version": 1,
        "minor_version": 1,
        "domain": DOMAIN,
        "title": role_name,
        "data": {
            CONF_ROLE_NAME: role_name,
            CONF_DEVICE_ID: device_id,
            CONF_ACTIVE: active,
            CONF_ENTITY_MAPPINGS: mappings,
        },
        "options": {},
        "pref_disable_new_entities": False,
        "pref_disable_polling": False,
        "source": SOURCE_USER,
        "unique_id": None,
        "discovery_keys": MappingProxyType({}),
    }
    if _CONFIG_ENTRY_SUPPORTS_SUBENTRIES:
        entry_kwargs["subentries_data"] = ()
    return ConfigEntry(**entry_kwargs)


def validate_role_name(
    hass: HomeAssistant,
    role_name: str,
    *,
    exclude_entry_id: str | None = None,
) -> None:
    """Reject duplicate role names."""
    existing_names = {
        entry.data.get(CONF_ROLE_NAME, entry.title)
        for entry in get_device_role_entries(hass)
        if entry.entry_id != exclude_entry_id
    }
    if role_name in existing_names:
        raise RoleManagerError(
            "name_exists",
            f"A role named '{role_name}' already exists.",
        )


def get_device_entity_options(
    hass: HomeAssistant, device_id: str
) -> dict[str, str]:
    """Return selectable entity options for a physical device."""
    return {
        entry.entity_id: describe_registry_entry(entry)
        for entry in get_eligible_device_entities(hass, device_id)
    }


def get_eligible_device_entities(
    hass: HomeAssistant, device_id: str
) -> list[er.RegistryEntry]:
    """Return supported entities for a device."""
    device_reg = dr.async_get(hass)
    if device_reg.async_get(device_id) is None:
        raise RoleManagerError(
            "device_not_found",
            f"Physical device '{device_id}' was not found.",
        )

    entity_reg = er.async_get(hass)
    return [
        entry
        for entry in er.async_entries_for_device(
            entity_reg, device_id, include_disabled_entities=False
        )
        if entry.domain in SUPPORTED_DOMAINS
    ]


def _get_state_class(
    hass: HomeAssistant, reg_entry: er.RegistryEntry
) -> str | None:
    """Extract state_class from the registry or current entity state."""
    if reg_entry.capabilities:
        state_class = reg_entry.capabilities.get("state_class")
        if state_class is not None:
            return state_class

    source_state = hass.states.get(reg_entry.entity_id)
    if source_state is not None:
        return source_state.attributes.get("state_class")
    return None


def _build_slot_name(domain: str, device_class: str | None) -> str:
    """Build a slot name from domain and device class."""
    if device_class:
        return f"{domain}_{device_class}"
    return domain


def _allocate_slot_name(base_slot: str, used_slots: set[str]) -> str:
    """Allocate a unique slot name while preserving existing slot names."""
    if base_slot not in used_slots:
        return base_slot

    ordinal = 2
    while True:
        candidate = f"{base_slot}_{ordinal}"
        if candidate not in used_slots:
            return candidate
        ordinal += 1


def get_claimed_source_unique_ids(
    hass: HomeAssistant,
    *,
    exclude_entry_id: str | None = None,
) -> set[str]:
    """Return all source unique IDs claimed by active roles."""
    claimed: set[str] = set()
    for entry in get_device_role_entries(hass):
        if entry.entry_id == exclude_entry_id:
            continue
        if not entry.data.get(CONF_ACTIVE, False):
            continue
        for mapping in entry.data.get(CONF_ENTITY_MAPPINGS, []):
            claimed.add(mapping[CONF_SOURCE_UNIQUE_ID])
    return claimed


def _validate_requested_entity_ids(
    entity_ids: Sequence[str], *, require_non_empty: bool
) -> None:
    """Validate requested entity_id collections."""
    if require_non_empty and not entity_ids:
        raise RoleManagerError(
            "no_entities",
            "At least one source entity must be selected.",
        )
    if len(set(entity_ids)) != len(entity_ids):
        raise RoleManagerError(
            "duplicate_entities",
            "Each source entity may only be selected once.",
        )


def resolve_selected_source_entities(
    hass: HomeAssistant,
    device_id: str,
    entity_ids: Sequence[str],
    *,
    require_non_empty: bool,
) -> list[er.RegistryEntry]:
    """Resolve and validate selected entities for a device."""
    _validate_requested_entity_ids(entity_ids, require_non_empty=require_non_empty)

    entity_reg = er.async_get(hass)
    eligible_entries = get_eligible_device_entities(hass, device_id)
    eligible_by_id = {entry.entity_id: entry for entry in eligible_entries}

    selected_entries: list[er.RegistryEntry] = []
    for entity_id in entity_ids:
        reg_entry = entity_reg.async_get(entity_id)
        if reg_entry is None:
            raise RoleManagerError(
                "entity_not_found",
                f"Entity '{entity_id}' was not found.",
            )
        if reg_entry.device_id != device_id:
            raise RoleManagerError(
                "entity_wrong_device",
                f"Entity '{entity_id}' does not belong to device '{device_id}'.",
            )
        if reg_entry.domain not in SUPPORTED_DOMAINS:
            raise RoleManagerError(
                "unsupported_domain",
                f"Entity '{entity_id}' uses unsupported domain '{reg_entry.domain}'.",
            )
        if entity_id not in eligible_by_id:
            raise RoleManagerError(
                "entity_not_available",
                f"Entity '{entity_id}' is not available for selection.",
            )
        selected_entries.append(eligible_by_id[entity_id])

    return selected_entries


def validate_unclaimed_entities(
    hass: HomeAssistant,
    selected_entries: Sequence[er.RegistryEntry],
    *,
    exclude_entry_id: str | None = None,
) -> None:
    """Reject entities already claimed by another active role."""
    claimed = get_claimed_source_unique_ids(hass, exclude_entry_id=exclude_entry_id)
    if any(entry.unique_id in claimed for entry in selected_entries):
        raise RoleManagerError(
            "entity_claimed",
            "One or more selected entities are already claimed by another active role.",
        )


def build_entity_mappings(
    hass: HomeAssistant,
    selected_entries: Sequence[er.RegistryEntry],
    *,
    existing_mappings: Sequence[Mapping[str, object]] | None = None,
) -> list[dict]:
    """Build entity mappings, preserving existing slot names when possible."""
    existing_by_uid = {
        mapping[CONF_SOURCE_UNIQUE_ID]: dict(mapping)
        for mapping in existing_mappings or []
    }
    used_slots: set[str] = set()
    mappings: list[dict] = []

    for entry in selected_entries:
        existing = existing_by_uid.get(entry.unique_id)
        if existing is not None:
            mapping = existing
        else:
            mapping = {
                CONF_SLOT: _allocate_slot_name(
                    _build_slot_name(entry.domain, entry.original_device_class),
                    used_slots,
                )
            }

        mapping[CONF_SOURCE_UNIQUE_ID] = entry.unique_id
        mapping[CONF_SOURCE_ENTITY_ID] = entry.entity_id
        mapping[CONF_DOMAIN] = entry.domain
        mapping[CONF_DEVICE_CLASS] = entry.original_device_class
        mapping[CONF_STATE_CLASS] = _get_state_class(hass, entry)
        used_slots.add(mapping[CONF_SLOT])
        mappings.append(mapping)

    return mappings


def build_configured_mappings(
    hass: HomeAssistant,
    device_id: str,
    entity_ids: Sequence[str],
    *,
    existing_mappings: Sequence[Mapping[str, object]] | None = None,
    exclude_entry_id: str | None = None,
    require_non_empty: bool,
) -> list[dict]:
    """Validate a same-device source selection and build mappings."""
    selected_entries = resolve_selected_source_entities(
        hass,
        device_id,
        entity_ids,
        require_non_empty=require_non_empty,
    )
    validate_unclaimed_entities(
        hass, selected_entries, exclude_entry_id=exclude_entry_id
    )
    return build_entity_mappings(
        hass, selected_entries, existing_mappings=existing_mappings
    )


def get_role_entity_id(
    hass: HomeAssistant,
    entry: ConfigEntry,
    mapping: Mapping[str, object],
) -> str | None:
    """Resolve a role entity_id from its stable unique ID."""
    entity_reg = er.async_get(hass)
    return entity_reg.async_get_entity_id(
        mapping[CONF_DOMAIN],
        DOMAIN,
        f"{entry.entry_id}_{mapping[CONF_SLOT]}",
    )


def serialize_role(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, object]:
    """Serialize a config entry into the canonical role object."""
    mappings: list[dict[str, object]] = []
    for mapping in entry.data.get(CONF_ENTITY_MAPPINGS, []):
        mappings.append(
            {
                "slot": mapping[CONF_SLOT],
                "role_entity_id": get_role_entity_id(hass, entry, mapping),
                "source_entity_id": mapping[CONF_SOURCE_ENTITY_ID],
                "source_unique_id": mapping[CONF_SOURCE_UNIQUE_ID],
                "domain": mapping[CONF_DOMAIN],
                "device_class": mapping.get(CONF_DEVICE_CLASS),
            }
        )

    return {
        "config_entry_id": entry.entry_id,
        "name": entry.data.get(CONF_ROLE_NAME, entry.title),
        "active": entry.data.get(CONF_ACTIVE, True),
        "device_id": entry.data.get(CONF_DEVICE_ID),
        "mappings": mappings,
    }


def build_reassignment_plan(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_id: str,
) -> tuple[dict[str, dict[str, str]], dict[str, str], bool]:
    """Build per-role-entity reassignment options for a new device."""
    eligible_entries = get_eligible_device_entities(hass, device_id)
    candidate_options: dict[str, dict[str, str]] = {}
    defaults: dict[str, str] = {}
    used_defaults: set[str] = set()
    requires_explicit_mapping = False

    for current_mapping in entry.data.get(CONF_ENTITY_MAPPINGS, []):
        role_entity_id = get_role_entity_id(hass, entry, current_mapping)
        if role_entity_id is None:
            role_entity_id = f"{current_mapping[CONF_DOMAIN]}.{entry.title.lower()}"

        compatible = [
            candidate
            for candidate in eligible_entries
            if candidate.domain == current_mapping[CONF_DOMAIN]
            and candidate.original_device_class == current_mapping.get(CONF_DEVICE_CLASS)
        ]

        options = {"": "Remove from role"}
        options.update(
            {
                candidate.entity_id: describe_registry_entry(candidate)
                for candidate in compatible
            }
        )
        candidate_options[role_entity_id] = options

        default = ""
        if len(compatible) == 1 and compatible[0].entity_id not in used_defaults:
            default = compatible[0].entity_id
            used_defaults.add(default)
        else:
            requires_explicit_mapping = True

        if not compatible:
            requires_explicit_mapping = True

        defaults[role_entity_id] = default

    return candidate_options, defaults, requires_explicit_mapping


def build_reassignment_mappings(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_id: str,
    assignments: Sequence[Mapping[str, str]],
) -> list[dict]:
    """Build new mappings for a reassigned role."""
    assignment_by_role_entity_id: dict[str, str] = {}
    assigned_entity_ids: set[str] = set()

    for assignment in assignments:
        role_entity_id = assignment["role_entity_id"]
        entity_id = assignment["entity_id"]

        if role_entity_id in assignment_by_role_entity_id:
            raise RoleManagerError(
                "duplicate_role_assignment",
                f"Role entity '{role_entity_id}' was assigned more than once.",
            )
        if entity_id in assigned_entity_ids:
            raise RoleManagerError(
                "duplicate_entities",
                f"Source entity '{entity_id}' was assigned more than once.",
            )

        assignment_by_role_entity_id[role_entity_id] = entity_id
        assigned_entity_ids.add(entity_id)

    selected_entries = resolve_selected_source_entities(
        hass,
        device_id,
        list(assigned_entity_ids),
        require_non_empty=False,
    )
    selected_by_entity_id = {entry.entity_id: entry for entry in selected_entries}
    validate_unclaimed_entities(
        hass, selected_entries, exclude_entry_id=entry.entry_id
    )

    new_mappings: list[dict] = []
    for current_mapping in entry.data.get(CONF_ENTITY_MAPPINGS, []):
        role_entity_id = get_role_entity_id(hass, entry, current_mapping)
        assigned_entity_id = assignment_by_role_entity_id.get(role_entity_id or "")
        if assigned_entity_id is None:
            continue

        selected_entry = selected_by_entity_id[assigned_entity_id]
        if selected_entry.domain != current_mapping[CONF_DOMAIN]:
            raise RoleManagerError(
                "incompatible_domain",
                f"Role entity '{role_entity_id}' can only be reassigned to a"
                f" '{current_mapping[CONF_DOMAIN]}' source entity.",
            )
        if selected_entry.original_device_class != current_mapping.get(CONF_DEVICE_CLASS):
            raise RoleManagerError(
                "incompatible_device_class",
                f"Role entity '{role_entity_id}' requires a"
                f" '{current_mapping.get(CONF_DEVICE_CLASS)}' source entity.",
            )

        new_mappings.append(
            {
                CONF_SLOT: current_mapping[CONF_SLOT],
                CONF_SOURCE_UNIQUE_ID: selected_entry.unique_id,
                CONF_SOURCE_ENTITY_ID: selected_entry.entity_id,
                CONF_DOMAIN: selected_entry.domain,
                CONF_DEVICE_CLASS: selected_entry.original_device_class,
                CONF_STATE_CLASS: _get_state_class(hass, selected_entry),
            }
        )

    known_role_entity_ids = {
        get_role_entity_id(hass, entry, mapping)
        for mapping in entry.data.get(CONF_ENTITY_MAPPINGS, [])
    }
    for role_entity_id in assignment_by_role_entity_id:
        if role_entity_id not in known_role_entity_ids:
            raise RoleManagerError(
                "role_entity_not_found",
                f"Role entity '{role_entity_id}' does not belong to role"
                f" '{entry.entry_id}'.",
            )

    return new_mappings


def validate_reassignment_units(
    hass: HomeAssistant,
    entry: ConfigEntry,
    new_mappings: Sequence[Mapping[str, object]],
) -> None:
    """Reject reassignment when an accumulator unit would change."""
    store_manager = hass.data.get(DOMAIN, {}).get("store_manager")
    if store_manager is None:
        return

    new_by_slot = {mapping[CONF_SLOT]: mapping for mapping in new_mappings}
    for current_mapping in entry.data.get(CONF_ENTITY_MAPPINGS, []):
        accumulator = store_manager.get_by_entry_slot(
            entry.entry_id, current_mapping[CONF_SLOT]
        )
        if accumulator is None or accumulator.unit is None:
            continue

        replacement = new_by_slot.get(current_mapping[CONF_SLOT])
        if replacement is None:
            continue

        source_state = hass.states.get(replacement[CONF_SOURCE_ENTITY_ID])
        new_unit = (
            source_state.attributes.get("unit_of_measurement", "")
            if source_state is not None
            else ""
        )
        if new_unit and new_unit != accumulator.unit:
            raise RoleManagerError(
                "unit_mismatch",
                "New device has a different unit for an accumulating sensor."
                " Delete and recreate the role to change units.",
            )


def commit_entry_accumulators(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Commit all current accumulator sessions for an entry."""
    store_manager = hass.data.get(DOMAIN, {}).get("store_manager")
    if store_manager is None:
        return

    store_manager.commit_entry_slots(
        entry.entry_id,
        [
            mapping[CONF_SLOT]
            for mapping in entry.data.get(CONF_ENTITY_MAPPINGS, [])
        ],
    )


async def async_update_role_entry(
    hass: HomeAssistant, entry: ConfigEntry, new_data: Mapping[str, object]
) -> ConfigEntry:
    """Persist new config-entry data and reload the entry."""
    hass.config_entries.async_update_entry(entry, data=dict(new_data))
    await hass.config_entries.async_reload(entry.entry_id)
    return get_device_role_entry(hass, entry.entry_id)
