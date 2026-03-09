# ABOUTME: E2E tests verifying multiple roles work independently on one physical device.
# ABOUTME: Checks role isolation and propagation of source entity unavailability.

import pytest


pytestmark = [pytest.mark.e2e]


@pytest.mark.usefixtures("ha_bootstrap")
def test_two_roles_mirror_independently(ha_client):
    """Two roles on the same device mirror their own entities without cross-talk."""
    # Set temperature (role 1's source) to a specific value
    ha_client.call_service("fake_device", "set_value", {
        "entity_id": "sensor.test_plug_temperature",
        "value": 33.3,
    })
    # Set humidity (role 2's source) to a different value
    ha_client.call_service("fake_device", "set_value", {
        "entity_id": "sensor.test_plug_humidity",
        "value": 77.7,
    })

    # Verify role 1 mirrors temperature
    state = ha_client.wait_for_state(
        "sensor.e2e_role_sensor_temperature", "33.3", timeout=15,
    )
    assert state is not None

    # Verify role 2 mirrors humidity
    state = ha_client.wait_for_state(
        "sensor.e2e_role_2_sensor_humidity", "77.7", timeout=15,
    )
    assert state is not None


@pytest.mark.usefixtures("ha_bootstrap")
def test_source_unavailable_propagates_to_role(ha_client):
    """When a source entity becomes unavailable, the role entity reflects it."""
    # Verify role 2 is mirroring normally
    ha_client.call_service("fake_device", "set_value", {
        "entity_id": "sensor.test_plug_humidity",
        "value": 55.0,
    })
    ha_client.wait_for_state(
        "sensor.e2e_role_2_sensor_humidity", "55.0", timeout=15,
    )

    # Make the source entity unavailable
    ha_client.call_service("fake_device", "set_value", {
        "entity_id": "sensor.test_plug_humidity",
        "value": "unavailable",
    })

    # Role entity should show "unknown" (entity is available but has no value)
    state = ha_client.wait_for_state(
        "sensor.e2e_role_2_sensor_humidity", "unknown", timeout=15,
    )
    assert state is not None

    # Restore source and verify role recovers
    ha_client.call_service("fake_device", "set_value", {
        "entity_id": "sensor.test_plug_humidity",
        "value": 60.0,
    })
    state = ha_client.wait_for_state(
        "sensor.e2e_role_2_sensor_humidity", "60.0", timeout=15,
    )
    assert state is not None
