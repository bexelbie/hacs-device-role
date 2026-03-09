# ABOUTME: Shared test fixtures for device_role integration tests.
# ABOUTME: Provides common setup for config entries, mock devices, and HA test helpers.

import pytest

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.device_role.const import DOMAIN


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Create a mock config entry for a device role."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Role",
        data={
            "role_name": "Test Role",
            "device_id": "test_device_id",
            "active": True,
            "entity_mappings": [],
        },
    )
