# ABOUTME: Tests for E2E Home Assistant storage seeding and discovery.
# ABOUTME: Verifies persisted registry data is read using current schemas.

from tests.e2e.seed import discover_fake_device_ids, write_storage_file


def test_discovers_device_by_config_entry_id(tmp_path) -> None:
    """Find a device using Home Assistant's singular config entry field."""
    write_storage_file(
        tmp_path,
        "core.device_registry",
        {
            "data": {
                "devices": [
                    {
                        "id": "device-id",
                        "config_entry_id": "fake_device_e2e",
                    }
                ]
            }
        },
    )
    write_storage_file(
        tmp_path,
        "core.entity_registry",
        {
            "data": {
                "entities": [
                    {
                        "entity_id": "sensor.test_plug_temperature",
                        "unique_id": "temperature",
                        "device_id": "device-id",
                        "original_device_class": "temperature",
                        "capabilities": {"state_class": "measurement"},
                    }
                ]
            }
        },
    )

    discovered = discover_fake_device_ids(tmp_path, "fake_device_e2e")

    assert discovered["device_id"] == "device-id"
    assert "sensor.test_plug_temperature" in discovered["entities"]
