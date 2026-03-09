# ABOUTME: E2E restart persistence tests for energy accumulator.
# ABOUTME: Verifies accumulated energy survives real HA container restarts.

import pytest


pytestmark = [pytest.mark.e2e]


@pytest.mark.usefixtures("ha_bootstrap")
async def test_energy_accumulation_survives_restart(ha_client, restart_ha):
    """Energy accumulated before restart is preserved after restart."""
    # Set initial energy reading
    await ha_client.call_service("fake_device", "set_value", {
        "entity_id": "sensor.test_plug_energy",
        "value": 100.0,
    })
    # Wait for the role energy sensor to pick it up
    await ha_client.wait_for_state(
        "sensor.e2e_role_sensor_energy", "0.0", timeout=15,
    )

    # Accumulate 50 kWh
    await ha_client.call_service("fake_device", "set_value", {
        "entity_id": "sensor.test_plug_energy",
        "value": 150.0,
    })
    state = await ha_client.wait_for_state(
        "sensor.e2e_role_sensor_energy", "50.0", timeout=15,
    )
    assert state is not None

    # Restart HA container (graceful stop preserves .storage/)
    restart_ha()

    # After restart, set energy to a higher value
    await ha_client.call_service("fake_device", "set_value", {
        "entity_id": "sensor.test_plug_energy",
        "value": 200.0,
    })

    # The role energy sensor should show 100.0 total (50 before + 50 after)
    # NOT 200.0 (raw reset) or 0.0 (session lost)
    state = await ha_client.wait_for_state(
        "sensor.e2e_role_sensor_energy", "100.0", timeout=30,
    )
    assert state is not None


@pytest.mark.usefixtures("ha_bootstrap")
async def test_deactivate_commit_survives_restart(
    ha_client, ha_bootstrap, restart_ha,
):
    """Energy committed on deactivation is preserved across restart."""
    # Set energy and accumulate
    await ha_client.call_service("fake_device", "set_value", {
        "entity_id": "sensor.test_plug_energy",
        "value": 100.0,
    })
    await ha_client.wait_for_state(
        "sensor.e2e_role_sensor_energy", "0.0", timeout=15,
    )

    await ha_client.call_service("fake_device", "set_value", {
        "entity_id": "sensor.test_plug_energy",
        "value": 175.0,
    })
    state = await ha_client.wait_for_state(
        "sensor.e2e_role_sensor_energy", "75.0", timeout=15,
    )
    assert state is not None

    # Deactivate the role by updating config entry storage and restarting.
    # This simulates what the options flow does: set active=False + reload.
    config_dir = ha_bootstrap["config_dir"]
    from .seed import read_storage_file, write_storage_file
    from .conftest import _docker, _restart_container, CONTAINER_NAME, HA_URL, HAClient

    # Stop to safely modify .storage/
    _docker("stop", CONTAINER_NAME)

    config_entries = read_storage_file(config_dir, "core.config_entries")
    for entry in config_entries["data"]["entries"]:
        if entry["entry_id"] == "device_role_e2e":
            entry["data"]["active"] = False
    write_storage_file(config_dir, "core.config_entries", config_entries)

    _docker("start", CONTAINER_NAME)
    async with HAClient(HA_URL) as client:
        await client.wait_for_ready(timeout=120)
        await client.onboard_and_authenticate()

        # Energy sensor should be frozen at 75.0 (committed on deactivation)
        state = await client.wait_for_state(
            "sensor.e2e_role_sensor_energy", "75.0", timeout=30,
        )
        assert state is not None

    # Restart again to verify committed value persists
    restart_ha()

    state = await ha_client.wait_for_state(
        "sensor.e2e_role_sensor_energy", "75.0", timeout=30,
    )
    assert state is not None
