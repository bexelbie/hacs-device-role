# ABOUTME: Service registration and handlers for the device_role integration.
# ABOUTME: Exposes role discovery and lifecycle management through Home Assistant services.

from __future__ import annotations

from types import MappingProxyType

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, SOURCE_USER
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service

from .const import CONF_ACTIVE, CONF_DEVICE_ID, CONF_ENTITY_MAPPINGS, CONF_ROLE_NAME, DOMAIN
from .role_manager import (
    RoleManagerError,
    async_update_role_entry,
    build_configured_mappings,
    build_reassignment_mappings,
    commit_entry_accumulators,
    get_device_role_entry,
    get_device_role_entries,
    serialize_role,
    validate_reassignment_units,
    validate_role_name,
)

SERVICE_LIST_ROLES = "list_roles"
SERVICE_CREATE_ROLE = "create_role"
SERVICE_SET_ACTIVE = "set_active"
SERVICE_CONFIGURE_ENTITIES = "configure_entities"
SERVICE_REASSIGN = "reassign"
SERVICE_DELETE_ROLE = "delete_role"

ROLE_ASSIGNMENT_SCHEMA = vol.Schema(
    {
        vol.Required("role_entity_id"): cv.entity_id,
        vol.Required("entity_id"): cv.entity_id,
    }
)


def _raise_service_error(err: RoleManagerError) -> None:
    """Translate a role-manager error into a service validation error."""
    raise ServiceValidationError(
        err.message,
        translation_domain=DOMAIN,
        translation_key=err.code,
    )


async def _async_handle_list_roles(call: ServiceCall) -> dict[str, object]:
    """Return all roles."""
    return {
        "roles": [
            serialize_role(call.hass, entry)
            for entry in get_device_role_entries(call.hass)
        ]
    }


async def _async_handle_create_role(call: ServiceCall) -> dict[str, object]:
    """Create a new role-backed config entry."""
    role_name = call.data["name"].strip()
    device_id = call.data[CONF_DEVICE_ID]
    entity_ids = call.data["entity_ids"]

    try:
        validate_role_name(call.hass, role_name)
        mappings = build_configured_mappings(
            call.hass,
            device_id,
            entity_ids,
            require_non_empty=True,
        )
    except RoleManagerError as err:
        _raise_service_error(err)

    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title=role_name,
        data={
            CONF_ROLE_NAME: role_name,
            CONF_DEVICE_ID: device_id,
            CONF_ACTIVE: True,
            CONF_ENTITY_MAPPINGS: mappings,
        },
        options={},
        pref_disable_new_entities=False,
        pref_disable_polling=False,
        source=SOURCE_USER,
        unique_id=None,
        discovery_keys=MappingProxyType({}),
        subentries_data=(),
    )
    await call.hass.config_entries.async_add(entry)
    return {"role": serialize_role(call.hass, entry)}


async def _async_handle_set_active(call: ServiceCall) -> dict[str, object]:
    """Set a role active or inactive."""
    entry = get_device_role_entry(call.hass, call.data["config_entry_id"])
    new_data = dict(entry.data)
    new_data[CONF_ACTIVE] = call.data[CONF_ACTIVE]
    entry = await async_update_role_entry(call.hass, entry, new_data)
    return {"role": serialize_role(call.hass, entry)}


async def _async_handle_configure_entities(call: ServiceCall) -> dict[str, object]:
    """Update the entity set for an existing role."""
    entry = get_device_role_entry(call.hass, call.data["config_entry_id"])
    try:
        mappings = build_configured_mappings(
            call.hass,
            entry.data[CONF_DEVICE_ID],
            call.data["entity_ids"],
            existing_mappings=entry.data.get(CONF_ENTITY_MAPPINGS, []),
            exclude_entry_id=entry.entry_id,
            require_non_empty=False,
        )
    except RoleManagerError as err:
        _raise_service_error(err)

    new_data = dict(entry.data)
    new_data[CONF_ENTITY_MAPPINGS] = mappings
    entry = await async_update_role_entry(call.hass, entry, new_data)
    return {"role": serialize_role(call.hass, entry)}


async def _async_handle_reassign(call: ServiceCall) -> dict[str, object]:
    """Reassign a role to a different physical device."""
    entry = get_device_role_entry(call.hass, call.data["config_entry_id"])
    device_id = call.data[CONF_DEVICE_ID]

    try:
        new_mappings = build_reassignment_mappings(
            call.hass,
            entry,
            device_id,
            call.data["assignments"],
        )
        validate_reassignment_units(call.hass, entry, new_mappings)
    except RoleManagerError as err:
        _raise_service_error(err)

    commit_entry_accumulators(call.hass, entry)
    new_data = dict(entry.data)
    new_data[CONF_DEVICE_ID] = device_id
    new_data[CONF_ENTITY_MAPPINGS] = new_mappings
    entry = await async_update_role_entry(call.hass, entry, new_data)
    return {"role": serialize_role(call.hass, entry)}


async def _async_handle_delete_role(call: ServiceCall) -> dict[str, object]:
    """Delete a role config entry."""
    entry = get_device_role_entry(call.hass, call.data["config_entry_id"])
    response = {
        "config_entry_id": entry.entry_id,
        "name": entry.data.get(CONF_ROLE_NAME, entry.title),
    }
    await call.hass.config_entries.async_remove(entry.entry_id)
    return response


def async_register_services(hass: HomeAssistant) -> None:
    """Register device_role services once."""
    if hass.services.has_service(DOMAIN, SERVICE_LIST_ROLES):
        return

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_LIST_ROLES,
        _async_handle_list_roles,
        supports_response=SupportsResponse.ONLY,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_CREATE_ROLE,
        _async_handle_create_role,
        schema=vol.Schema(
            {
                vol.Required("name"): str,
                vol.Required(CONF_DEVICE_ID): str,
                vol.Required("entity_ids"): vol.All(cv.ensure_list, [cv.entity_id]),
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_SET_ACTIVE,
        _async_handle_set_active,
        schema=vol.Schema(
            {
                vol.Required("config_entry_id"): str,
                vol.Required(CONF_ACTIVE): bool,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_CONFIGURE_ENTITIES,
        _async_handle_configure_entities,
        schema=vol.Schema(
            {
                vol.Required("config_entry_id"): str,
                vol.Required("entity_ids"): vol.All(cv.ensure_list, [cv.entity_id]),
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_REASSIGN,
        _async_handle_reassign,
        schema=vol.Schema(
            {
                vol.Required("config_entry_id"): str,
                vol.Required(CONF_DEVICE_ID): str,
                vol.Required("assignments"): vol.All(
                    cv.ensure_list,
                    [ROLE_ASSIGNMENT_SCHEMA],
                ),
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_DELETE_ROLE,
        _async_handle_delete_role,
        schema=vol.Schema({vol.Required("config_entry_id"): str}),
        supports_response=SupportsResponse.OPTIONAL,
    )
