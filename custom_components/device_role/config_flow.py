# ABOUTME: Config flow for the device_role integration.
# ABOUTME: Guides user through role creation: name → device selection → entity selection.

from homeassistant import config_entries

from .const import DOMAIN


class DeviceRoleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for creating a device role."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        # Placeholder — will be implemented in Phase 2
        return self.async_abort(reason="not_implemented")
