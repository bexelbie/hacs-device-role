# ABOUTME: E2E tests for the device_role service API against a real Home Assistant container.
# ABOUTME: Validates service-driven role management using the seeded integration state.

import pytest


pytestmark = [pytest.mark.e2e]


@pytest.mark.usefixtures("ha_bootstrap")
def test_set_active_service_deactivates_and_reactivates_role(ha_client):
    """The set_active service toggles a seeded role in real Home Assistant."""
    ha_client.call_service("device_role", "set_active", {
        "config_entry_id": "device_role_e2e",
        "active": False,
    })

    state = ha_client.wait_for_state(
        "sensor.e2e_role_temperature", "unavailable", timeout=15,
    )
    assert state is not None

    ha_client.call_service("device_role", "set_active", {
        "config_entry_id": "device_role_e2e",
        "active": True,
    })
    ha_client.call_service("fake_device", "set_value", {
        "entity_id": "sensor.test_plug_temperature",
        "value": 28.5,
    })

    state = ha_client.wait_for_state(
        "sensor.e2e_role_temperature", "28.5", timeout=15,
    )
    assert state is not None
