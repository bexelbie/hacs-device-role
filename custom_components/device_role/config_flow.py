# ABOUTME: Config flow for the device_role integration.
# ABOUTME: Guides user through role creation: name → device selection → entity selection.

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.selector import (
    DeviceSelector,
    DeviceSelectorConfig,
)

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
    DOMAIN,
    PLATFORMS,
)

SUPPORTED_DOMAINS = set(PLATFORMS)


def _build_slot_name(domain: str, device_class: str | None) -> str:
    """Build a slot name from domain and device class."""
    if device_class:
        return f"{domain}_{device_class}"
    return domain


def _deduplicate_slots(mappings: list[dict]) -> list[dict]:
    """Append ordinals to duplicate slot names."""
    seen: dict[str, int] = {}
    for mapping in mappings:
        base = mapping[CONF_SLOT]
        count = seen.get(base, 0)
        if count > 0:
            mapping[CONF_SLOT] = f"{base}_{count + 1}"
        seen[base] = count + 1
    return mappings


def _get_claimed_source_unique_ids(
    hass_entries: list[config_entries.ConfigEntry],
) -> set[str]:
    """Get all source unique IDs claimed by active roles."""
    claimed: set[str] = set()
    for entry in hass_entries:
        if entry.domain != DOMAIN:
            continue
        if not entry.data.get(CONF_ACTIVE, False):
            continue
        for mapping in entry.data.get(CONF_ENTITY_MAPPINGS, []):
            claimed.add(mapping[CONF_SOURCE_UNIQUE_ID])
    return claimed


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

            # Check for duplicate names
            existing_names = {
                entry.data.get(CONF_ROLE_NAME, entry.title)
                for entry in self.hass.config_entries.async_entries(DOMAIN)
            }
            if name in existing_names:
                errors["base"] = "name_exists"
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
                {vol.Required(CONF_DEVICE_ID): DeviceSelector(
                    DeviceSelectorConfig(
                        entity=[{"domain": list(SUPPORTED_DOMAINS)}],
                    )
                )}
            ),
        )

    async def async_step_select_entities(self, user_input=None):
        """Step 3: Select which entities to mirror."""
        entity_reg = er.async_get(self.hass)
        device_entities = er.async_entries_for_device(
            entity_reg, self._device_id, include_disabled_entities=False
        )

        # Filter to supported domains
        eligible = {
            entry.entity_id: (
                f"{entry.original_name or entry.entity_id}"
                f" ({entry.domain}"
                f"{', ' + entry.original_device_class if entry.original_device_class else ''})"
            )
            for entry in device_entities
            if entry.domain in SUPPORTED_DOMAINS
        }

        if not eligible:
            return self.async_abort(reason="no_entities")

        errors: dict[str, str] = {}

        if user_input is not None:
            selected_entity_ids = user_input.get("entities", [])

            # Validate no entity is claimed by another active role
            claimed = _get_claimed_source_unique_ids(
                self.hass.config_entries.async_entries(DOMAIN)
            )

            selected_entries = [
                entry
                for entry in device_entities
                if entry.entity_id in selected_entity_ids
            ]

            conflict = any(
                entry.unique_id in claimed for entry in selected_entries
            )

            if conflict:
                errors["base"] = "entity_claimed"
            else:
                # Build entity mappings
                mappings = []
                for entry in selected_entries:
                    mappings.append(
                        {
                            CONF_SLOT: _build_slot_name(
                                entry.domain, entry.original_device_class
                            ),
                            CONF_SOURCE_UNIQUE_ID: entry.unique_id,
                            CONF_SOURCE_ENTITY_ID: entry.entity_id,
                            CONF_DOMAIN: entry.domain,
                            CONF_DEVICE_CLASS: entry.original_device_class,
                        }
                    )
                mappings = _deduplicate_slots(mappings)

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

    async def async_step_init(self, user_input=None):
        """Show the options form with active toggle, entity selection, and device change."""
        errors: dict[str, str] = {}
        device_id = self._config_entry.data.get(CONF_DEVICE_ID)
        entity_reg = er.async_get(self.hass)

        # Look up device name for display, preferring user-assigned name
        device_reg = dr.async_get(self.hass)
        device = device_reg.async_get(device_id) if device_id else None
        device_name = (
            (device.name_by_user or device.name) if device else "Unknown device"
        )

        # Get eligible entities from the device
        device_entities = er.async_entries_for_device(
            entity_reg, device_id, include_disabled_entities=False
        )
        eligible = {
            entry.entity_id: (
                f"{entry.original_name or entry.entity_id}"
                f" ({entry.domain}"
                f"{', ' + entry.original_device_class if entry.original_device_class else ''})"
            )
            for entry in device_entities
            if entry.domain in SUPPORTED_DOMAINS
        }

        # Currently mapped entity IDs
        current_mappings = self._config_entry.data.get(CONF_ENTITY_MAPPINGS, [])
        current_entity_ids = [
            m[CONF_SOURCE_ENTITY_ID] for m in current_mappings
        ]

        if user_input is not None:
            # Route to device change flow if requested
            if user_input.get("change_device", False):
                return await self.async_step_select_device()

            new_active = user_input.get(CONF_ACTIVE, True)
            new_mappings = current_mappings

            # Only update mappings if the entities field was shown
            if eligible and "entities" in user_input:
                selected_entity_ids = user_input["entities"]

                # Check for conflicts with other active roles
                claimed = _get_claimed_source_unique_ids(
                    self.hass.config_entries.async_entries(DOMAIN)
                )
                # Exclude entities already owned by this role
                own_uids = {
                    m[CONF_SOURCE_UNIQUE_ID] for m in current_mappings
                }
                claimed -= own_uids

                selected_entries = [
                    e for e in device_entities
                    if e.entity_id in selected_entity_ids
                ]
                conflict = any(
                    e.unique_id in claimed for e in selected_entries
                )

                if conflict:
                    errors["base"] = "entity_claimed"
                else:
                    # Build new mappings preserving existing slot names
                    existing_by_uid = {
                        m[CONF_SOURCE_UNIQUE_ID]: m for m in current_mappings
                    }

                    new_mappings = []
                    for entry in device_entities:
                        if entry.entity_id not in selected_entity_ids:
                            continue
                        if entry.domain not in SUPPORTED_DOMAINS:
                            continue

                        if entry.unique_id in existing_by_uid:
                            new_mappings.append(existing_by_uid[entry.unique_id])
                        else:
                            new_mappings.append(
                            {
                                CONF_SLOT: _build_slot_name(
                                    entry.domain, entry.original_device_class
                                ),
                                CONF_SOURCE_UNIQUE_ID: entry.unique_id,
                                CONF_SOURCE_ENTITY_ID: entry.entity_id,
                                CONF_DOMAIN: entry.domain,
                                CONF_DEVICE_CLASS: entry.original_device_class,
                            }
                        )

                    new_mappings = _deduplicate_slots(new_mappings)

            if errors:
                # Fall through to re-show the form with errors
                pass
            else:
                new_data = dict(self._config_entry.data)
                new_data[CONF_ACTIVE] = new_active
                new_data[CONF_ENTITY_MAPPINGS] = new_mappings

                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data
                )

                return self.async_create_entry(title="", data={})

        current_active = self._config_entry.data.get(CONF_ACTIVE, True)

        schema_fields = {
            vol.Required(CONF_ACTIVE, default=current_active): bool,
        }

        if eligible:
            schema_fields[vol.Required(
                "entities", default=current_entity_ids
            )] = cv.multi_select(eligible)

        schema_fields[vol.Optional("change_device", default=False)] = bool

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_fields),
            description_placeholders={"device_name": device_name},
            errors=errors,
        )

    async def async_step_select_device(self, user_input=None):
        """Select a new physical device for the role."""
        if user_input is not None:
            self._new_device_id = user_input[CONF_DEVICE_ID]
            return await self.async_step_select_entities()

        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICE_ID): DeviceSelector(
                    DeviceSelectorConfig(
                        entity=[{"domain": list(SUPPORTED_DOMAINS)}],
                    )
                )}
            ),
        )

    async def async_step_select_entities(self, user_input=None):
        """Select entities from the new device to mirror."""
        entity_reg = er.async_get(self.hass)
        device_entities = er.async_entries_for_device(
            entity_reg, self._new_device_id, include_disabled_entities=False
        )
        eligible = {
            entry.entity_id: (
                f"{entry.original_name or entry.entity_id}"
                f" ({entry.domain}"
                f"{', ' + entry.original_device_class if entry.original_device_class else ''})"
            )
            for entry in device_entities
            if entry.domain in SUPPORTED_DOMAINS
        }

        errors: dict[str, str] = {}

        if user_input is not None:
            selected_entity_ids = user_input.get("entities", [])

            # Check for conflicts with other active roles
            claimed = _get_claimed_source_unique_ids(
                self.hass.config_entries.async_entries(DOMAIN)
            )
            current_mappings = self._config_entry.data.get(
                CONF_ENTITY_MAPPINGS, []
            )
            own_uids = {
                m[CONF_SOURCE_UNIQUE_ID] for m in current_mappings
            }
            claimed -= own_uids

            selected_entries = [
                entry for entry in device_entities
                if entry.entity_id in selected_entity_ids
            ]
            conflict = any(
                entry.unique_id in claimed for entry in selected_entries
            )

            if conflict:
                errors["base"] = "entity_claimed"
            else:
                # Build new mappings first so slot names are deduplicated
                new_mappings = []
                for entry in selected_entries:
                    new_mappings.append(
                        {
                            CONF_SLOT: _build_slot_name(
                                entry.domain, entry.original_device_class
                            ),
                            CONF_SOURCE_UNIQUE_ID: entry.unique_id,
                            CONF_SOURCE_ENTITY_ID: entry.entity_id,
                            CONF_DOMAIN: entry.domain,
                            CONF_DEVICE_CLASS: entry.original_device_class,
                        }
                    )
                new_mappings = _deduplicate_slots(new_mappings)

                # Check for unit mismatches between existing accumulators
                # and new source entities before allowing reassignment.
                store_manager = self.hass.data.get(DOMAIN, {}).get(
                    "store_manager"
                )
                new_by_slot = {m[CONF_SLOT]: m for m in new_mappings}
                if store_manager:
                    for mapping in current_mappings:
                        acc_key = (
                            f"{self._config_entry.entry_id}"
                            f"_{mapping[CONF_SLOT]}"
                        )
                        acc = store_manager._accumulators.get(acc_key)
                        if acc is None or acc.unit is None:
                            continue
                        new_mapping = new_by_slot.get(mapping[CONF_SLOT])
                        if new_mapping is None:
                            continue
                        new_state = self.hass.states.get(
                            new_mapping[CONF_SOURCE_ENTITY_ID]
                        )
                        new_unit = (
                            new_state.attributes.get(
                                "unit_of_measurement", ""
                            )
                            if new_state
                            else ""
                        )
                        if new_unit and new_unit != acc.unit:
                            errors["base"] = "unit_mismatch"
                            break

            if not errors:
                # Commit all active accumulator sessions before reassignment
                # so the old device's deltas are preserved in historical_sum.
                if store_manager:
                    for mapping in current_mappings:
                        acc_key = (
                            f"{self._config_entry.entry_id}"
                            f"_{mapping[CONF_SLOT]}"
                        )
                        acc = store_manager._accumulators.get(acc_key)
                        if acc is not None:
                            acc.commit_session()

                new_data = dict(self._config_entry.data)
                new_data[CONF_DEVICE_ID] = self._new_device_id
                new_data[CONF_ENTITY_MAPPINGS] = new_mappings

                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data
                )

                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="select_entities",
            data_schema=vol.Schema(
                {vol.Required("entities"): cv.multi_select(eligible)}
            ),
            errors=errors,
        )
