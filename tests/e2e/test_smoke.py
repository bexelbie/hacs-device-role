# ABOUTME: E2E smoke test verifying both integrations load in real HA.
# ABOUTME: Checks basic entity mirroring via REST API against a Docker container.

import pytest


pytestmark = [pytest.mark.e2e]


@pytest.mark.usefixtures("ha_bootstrap")
def test_fake_device_entities_exist(ha_client):
    """Both integrations load and fake_device entities are reachable."""
    state = ha_client.get_state("sensor.test_plug_temperature")
    assert state is not None
    assert state["state"] != "unavailable"


@pytest.mark.usefixtures("ha_bootstrap")
def test_role_mirrors_temperature(ha_client):
    """Set a value on fake_device and verify the role sensor mirrors it."""
    ha_client.call_service("fake_device", "set_value", {
        "entity_id": "sensor.test_plug_temperature",
        "value": 25.5,
    })

    state = ha_client.wait_for_state(
        "sensor.e2e_role_sensor_temperature", "25.5", timeout=15,
    )
    assert state is not None


@pytest.mark.usefixtures("ha_bootstrap")
def test_role_mirrors_switch(ha_client):
    """Toggle fake_device switch and verify the role switch mirrors it."""
    ha_client.call_service("fake_device", "set_value", {
        "entity_id": "switch.test_plug_outlet",
        "value": True,
    })

    state = ha_client.wait_for_state(
        "switch.e2e_role_switch", "on", timeout=15,
    )
    assert state is not None
