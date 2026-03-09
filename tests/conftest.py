# ABOUTME: Shared test fixtures for device_role integration tests.
# ABOUTME: Provides common setup for config entries, mock devices, and HA test helpers.

import os
from pathlib import Path

import pytest

from pytest_homeassistant_custom_component.common import MockConfigEntry

# Make fake_device available to HA's integration loader during tests.
# It lives in tests/fixtures/ to keep custom_components/ HACS-clean.
# Must happen before module collection so imports resolve.
_FAKE_DEVICE_SRC = Path(__file__).parent / "fixtures" / "fake_device"
_FAKE_DEVICE_DST = Path(__file__).parents[1] / "custom_components" / "fake_device"

if not _FAKE_DEVICE_DST.exists():
    os.symlink(_FAKE_DEVICE_SRC.resolve(), _FAKE_DEVICE_DST)

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
