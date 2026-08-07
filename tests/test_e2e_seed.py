# ABOUTME: Unit tests for E2E storage seeding/discovery helpers in tests/e2e/seed.py.
# ABOUTME: Guards discover_fake_device_ids against HA's real device-registry schema.

from tests.e2e.seed import discover_fake_device_ids, write_storage_file


def _seed(config_dir, devices, entities):
    write_storage_file(config_dir, "core.device_registry", {"data": {"devices": devices}})
    write_storage_file(config_dir, "core.entity_registry", {"data": {"entities": entities}})


def test_discovers_device_using_real_ha_schema(tmp_path) -> None:
    """HA persists the owner as primary_config_entry + config_entries (never config_entry_id)."""
    _seed(
        tmp_path,
        devices=[
            {"id": "other", "primary_config_entry": "someone_else", "config_entries": ["someone_else"]},
            {"id": "target", "primary_config_entry": "fake_device_e2e", "config_entries": ["fake_device_e2e"]},
        ],
        entities=[
            {
                "device_id": "target",
                "entity_id": "sensor.test_plug_temperature",
                "unique_id": "fake_device_e2e_temperature",
                "original_device_class": "temperature",
                "capabilities": {"state_class": "measurement"},
            }
        ],
    )

    discovered = discover_fake_device_ids(tmp_path, "fake_device_e2e")

    assert discovered["device_id"] == "target"
    assert "sensor.test_plug_temperature" in discovered["entities"]


def test_discovers_device_when_config_entries_dropped(tmp_path) -> None:
    """Fallback path: HA may drop config_entries, leaving only primary_config_entry."""
    _seed(
        tmp_path,
        devices=[{"id": "target", "primary_config_entry": "fake_device_e2e"}],
        entities=[
            {
                "device_id": "target",
                "entity_id": "sensor.test_plug_temperature",
                "unique_id": "fake_device_e2e_temperature",
                "original_device_class": "temperature",
                "capabilities": {},
            }
        ],
    )

    discovered = discover_fake_device_ids(tmp_path, "fake_device_e2e")

    assert discovered["device_id"] == "target"
