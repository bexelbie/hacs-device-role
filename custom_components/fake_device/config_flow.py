# ABOUTME: Config flow for the fake_device integration.
# ABOUTME: Single-step flow: enter a device name, get a multi-entity device.

import voluptuous as vol

from homeassistant import config_entries

from .const import DOMAIN


class FakeDeviceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow to create a fake device."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Ask for a device name and create the entry."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input["name"],
                data={"name": user_input["name"]},
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("name"): str}),
        )
