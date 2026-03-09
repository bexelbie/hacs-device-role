# ABOUTME: Helpers for pre-seeding HA .storage/ files before container start.
# ABOUTME: Generates config entries, device/entity registry data for E2E tests.

from __future__ import annotations

import json
import os
from pathlib import Path


# Fixed timestamp for reproducible seeds
_SEED_TIMESTAMP = "2025-01-01T00:00:00.000000+00:00"


def write_storage_file(config_dir: str | Path, key: str, data: dict) -> None:
    """Write a .storage/ JSON file in HA's internal format."""
    storage_dir = Path(config_dir) / ".storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    path = storage_dir / key
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def read_storage_file(config_dir: str | Path, key: str) -> dict | None:
    """Read a .storage/ JSON file. Returns None if it doesn't exist."""
    path = Path(config_dir) / ".storage" / key
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def seed_config_entries(config_dir: str | Path, entries: list[dict]) -> None:
    """Write core.config_entries with the given entries."""
    write_storage_file(config_dir, "core.config_entries", {
        "version": 1,
        "minor_version": 5,
        "key": "core.config_entries",
        "data": {"entries": entries},
    })


def make_fake_device_entry(
    entry_id: str = "fake_device_e2e",
    name: str = "test_plug",
) -> dict:
    """Build a config entry dict for a fake_device instance."""
    return {
        "entry_id": entry_id,
        "domain": "fake_device",
        "title": name,
        "data": {"name": name},
        "options": {},
        "version": 1,
        "minor_version": 1,
        "source": "user",
        "unique_id": None,
        "disabled_by": None,
        "pref_disable_new_entities": False,
        "pref_disable_polling": False,
        "created_at": _SEED_TIMESTAMP,
        "modified_at": _SEED_TIMESTAMP,
        "discovery_keys": {},
        "subentries": [],
    }


def make_device_role_entry(
    entry_id: str,
    role_name: str,
    device_id: str,
    entity_mappings: list[dict],
    active: bool = True,
) -> dict:
    """Build a config entry dict for a device_role instance."""
    return {
        "entry_id": entry_id,
        "domain": "device_role",
        "title": role_name,
        "data": {
            "role_name": role_name,
            "device_id": device_id,
            "active": active,
            "entity_mappings": entity_mappings,
        },
        "options": {},
        "version": 1,
        "minor_version": 1,
        "source": "user",
        "unique_id": None,
        "disabled_by": None,
        "pref_disable_new_entities": False,
        "pref_disable_polling": False,
        "created_at": _SEED_TIMESTAMP,
        "modified_at": _SEED_TIMESTAMP,
        "discovery_keys": {},
        "subentries": [],
    }


def seed_accumulator_state(
    config_dir: str | Path,
    accumulators: dict[str, dict],
) -> None:
    """Write device_role_accumulators.json with pre-set accumulator state."""
    write_storage_file(config_dir, "device_role_accumulators.json", {
        "version": 1,
        "minor_version": 1,
        "key": "device_role_accumulators.json",
        "data": {"accumulators": accumulators},
    })


def discover_fake_device_ids(config_dir: str | Path, entry_id: str) -> dict:
    """Read device and entity registry to find IDs created by fake_device.

    Returns a dict with:
      - device_id: str
      - entities: dict mapping entity_id to {unique_id, domain, device_class}
    """
    device_reg = read_storage_file(config_dir, "core.device_registry")
    entity_reg = read_storage_file(config_dir, "core.entity_registry")

    if not device_reg or not entity_reg:
        raise RuntimeError(
            "Device/entity registry not found. Has HA booted at least once?"
        )

    # Find device by config_entry_id
    device_id = None
    for device in device_reg.get("data", {}).get("devices", []):
        if entry_id in device.get("config_entries", []):
            device_id = device["id"]
            break

    if not device_id:
        raise RuntimeError(f"No device found for config entry {entry_id}")

    # Find entities for this device
    entities = {}
    for entity in entity_reg.get("data", {}).get("entities", []):
        if entity.get("device_id") == device_id:
            entities[entity["entity_id"]] = {
                "unique_id": entity["unique_id"],
                "domain": entity["entity_id"].split(".")[0],
                "device_class": entity.get("original_device_class"),
            }

    return {"device_id": device_id, "entities": entities}
