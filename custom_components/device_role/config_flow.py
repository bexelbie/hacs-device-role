# ABOUTME: Config flow for the device_role integration.
# ABOUTME: Guides role creation and updates using shared role-management helpers.

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.selector import DeviceSelector, DeviceSelectorConfig

from .const import (
    CONF_ACTIVE,
    CONF_DEVICE_ID,
    CONF_ENTITY_MAPPINGS,
    CONF_ROLE_NAME,
    DOMAIN,
)
from .role_manager import (
    RoleManagerError,
    SUPPORTED_DOMAINS,
    async_update_role_entry,
    build_configured_mappings,
    build_reassignment_mappings,
    build_reassignment_plan,
    commit_entry_accumulators,
    get_device_entity_options,
    validate_reassignment_units,
    validate_role_name,
)


class DeviceRoleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for creating a device role."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return DeviceRoleOptionsFlow(config_entry)

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._role_name: str | None = None
        self._device_id: str | None = None

    async def async_step_user(self, user_input=None):
        """Step 1: Enter the role name."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_ROLE_NAME].strip()
            try:
                validate_role_name(self.hass, name)
            except RoleManagerError as err:
                errors["base"] = err.code
            else:
                self._role_name = name
                return await self.async_step_select_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ROLE_NAME): str}),
            errors=errors,
        )

    async def async_step_select_device(self, user_input=None):
        """Step 2: Select the physical device."""
        if user_input is not None:
            self._device_id = user_input[CONF_DEVICE_ID]
            return await self.async_step_select_entities()

        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): DeviceSelector(
                        DeviceSelectorConfig(
                            entity=[{"domain": list(SUPPORTED_DOMAINS)}],
                        )
                    )
                }
            ),
        )

    async def async_step_select_entities(self, user_input=None):
        """Step 3: Select which entities to mirror."""
        eligible = get_device_entity_options(self.hass, self._device_id)
        if not eligible:
            return self.async_abort(reason="no_entities")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                mappings = build_configured_mappings(
                    self.hass,
                    self._device_id,
                    user_input.get("entities", []),
                    require_non_empty=True,
                )
            except RoleManagerError as err:
                errors["base"] = err.code
            else:
                return self.async_create_entry(
                    title=self._role_name,
                    data={
                        CONF_ROLE_NAME: self._role_name,
                        CONF_DEVICE_ID: self._device_id,
                        CONF_ACTIVE: True,
                        CONF_ENTITY_MAPPINGS: mappings,
                    },
                )

        return self.async_show_form(
            step_id="select_entities",
            data_schema=vol.Schema(
                {vol.Required("entities"): cv.multi_select(eligible)}
            ),
            errors=errors,
        )


class DeviceRoleOptionsFlow(config_entries.OptionsFlow):
    """Options flow for modifying a device role."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry
        self._new_device_id: str | None = None
        self._reassignment_options: dict[str, dict[str, str]] = {}
        self._reassignment_defaults: dict[str, str] = {}

    async def async_step_init(self, user_input=None):
        """Show the options form with active toggle, entity selection, and device change."""
        errors: dict[str, str] = {}
        device_id = self._config_entry.data.get(CONF_DEVICE_ID)

        device_reg = dr.async_get(self.hass)
        device = device_reg.async_get(device_id) if device_id else None
        device_name = (
            (device.name_by_user or device.name) if device else "Unknown device"
        )

        eligible = get_device_entity_options(self.hass, device_id)
        current_mappings = self._config_entry.data.get(CONF_ENTITY_MAPPINGS, [])
        current_entity_ids = [m["source_entity_id"] for m in current_mappings]

        if user_input is not None:
            if user_input.get("change_device", False):
                return await self.async_step_select_device()

            new_active = user_input.get(CONF_ACTIVE, True)
            new_mappings = current_mappings

            if eligible and "entities" in user_input:
                try:
                    new_mappings = build_configured_mappings(
                        self.hass,
                        device_id,
                        user_input["entities"],
                        existing_mappings=current_mappings,
                        exclude_entry_id=self._config_entry.entry_id,
                        require_non_empty=False,
                    )
                except RoleManagerError as err:
                    errors["base"] = err.code

            if not errors:
                new_data = dict(self._config_entry.data)
                new_data[CONF_ACTIVE] = new_active
                new_data[CONF_ENTITY_MAPPINGS] = new_mappings
                self._config_entry = await async_update_role_entry(
                    self.hass, self._config_entry, new_data
                )
                return self.async_create_entry(title="", data={})

        current_active = self._config_entry.data.get(CONF_ACTIVE, True)
        schema_fields = {
            vol.Required(CONF_ACTIVE, default=current_active): bool,
        }
        if eligible:
            schema_fields[
                vol.Required("entities", default=current_entity_ids)
            ] = cv.multi_select(eligible)
        schema_fields[vol.Optional("change_device", default=False)] = bool

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_fields),
            description_placeholders={"device_name": device_name},
            errors=errors,
        )

    async def async_step_select_device(self, user_input=None):
        """Select a new physical device for the role."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._new_device_id = user_input[CONF_DEVICE_ID]
            try:
                (
                    self._reassignment_options,
                    self._reassignment_defaults,
                    requires_mapping,
                ) = build_reassignment_plan(
                    self.hass,
                    self._config_entry,
                    self._new_device_id,
                )
            except RoleManagerError as err:
                errors["base"] = err.code
            else:
                if not self._reassignment_options:
                    new_data = dict(self._config_entry.data)
                    new_data[CONF_DEVICE_ID] = self._new_device_id
                    self._config_entry = await async_update_role_entry(
                        self.hass, self._config_entry, new_data
                    )
                    return self.async_create_entry(title="", data={})

                if requires_mapping:
                    return await self.async_step_map_entities()

                assignments = [
                    {
                        "role_entity_id": role_entity_id,
                        "entity_id": entity_id,
                    }
                    for role_entity_id, entity_id in self._reassignment_defaults.items()
                    if entity_id
                ]
                try:
                    return await self._async_finish_reassignment(assignments)
                except RoleManagerError as err:
                    errors["base"] = err.code
                    return self._show_map_entities_form(errors)

        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): DeviceSelector(
                        DeviceSelectorConfig(
                            entity=[{"domain": list(SUPPORTED_DOMAINS)}],
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_map_entities(self, user_input=None):
        """Map logical role entities to source entities on the new device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            assignments = [
                {
                    "role_entity_id": role_entity_id,
                    "entity_id": entity_id,
                }
                for role_entity_id, entity_id in user_input.items()
                if entity_id
            ]
            try:
                return await self._async_finish_reassignment(assignments)
            except RoleManagerError as err:
                errors["base"] = err.code

        return self._show_map_entities_form(errors)

    async def _async_finish_reassignment(self, assignments: list[dict]):
        """Validate and apply a role reassignment."""
        new_mappings = build_reassignment_mappings(
            self.hass,
            self._config_entry,
            self._new_device_id,
            assignments,
        )
        validate_reassignment_units(self.hass, self._config_entry, new_mappings)
        commit_entry_accumulators(self.hass, self._config_entry)

        new_data = dict(self._config_entry.data)
        new_data[CONF_DEVICE_ID] = self._new_device_id
        new_data[CONF_ENTITY_MAPPINGS] = new_mappings
        self._config_entry = await async_update_role_entry(
            self.hass, self._config_entry, new_data
        )
        return self.async_create_entry(title="", data={})

    def _show_map_entities_form(self, errors: dict[str, str]):
        """Show the logical reassignment form."""
        return self.async_show_form(
            step_id="map_entities",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        role_entity_id,
                        default=self._reassignment_defaults.get(role_entity_id, ""),
                    ): vol.In(options)
                    for role_entity_id, options in self._reassignment_options.items()
                }
            ),
            errors=errors,
        )
