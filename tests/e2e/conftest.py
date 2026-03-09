# ABOUTME: Pytest fixtures for E2E tests against a real HA Docker container.
# ABOUTME: Manages container lifecycle, two-phase bootstrap, and REST client.

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from .ha_client import HAClient
from .seed import (
    discover_fake_device_ids,
    make_device_role_entry,
    make_fake_device_entry,
    read_storage_file,
    seed_accumulator_state,
    seed_config_entries,
)

_LOGGER = logging.getLogger(__name__)

HA_IMAGE = os.environ.get(
    "HA_E2E_IMAGE", "ghcr.io/home-assistant/home-assistant:stable"
)
CONTAINER_NAME = "ha-e2e-test"
HA_PORT = int(os.environ.get("HA_E2E_PORT", "18123"))
HA_URL = f"http://127.0.0.1:{HA_PORT}"

# Location of custom_components and test fixtures relative to repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
CUSTOM_COMPONENTS = REPO_ROOT / "custom_components"
FAKE_DEVICE_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "fake_device"

FAKE_DEVICE_ENTRY_ID = "fake_device_e2e"
DEVICE_ROLE_ENTRY_ID = "device_role_e2e"
DEVICE_ROLE_ENTRY_ID_2 = "device_role_e2e_2"
ROLE_NAME = "E2E Role"
ROLE_NAME_2 = "E2E Role 2"
FAKE_DEVICE_NAME = "test_plug"

# Entity slots assigned to each role (must not overlap)
ROLE_1_SLOTS = {"sensor_temperature", "sensor_energy", "switch"}
ROLE_2_SLOTS = {"sensor_humidity", "sensor_power", "binary_sensor_connectivity"}


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a docker command."""
    result = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        _LOGGER.error("docker %s failed:\n%s", " ".join(args), result.stderr)
        result.check_returncode()
    return result


def _dump_container_logs() -> None:
    """Print HA container logs for debugging."""
    result = _docker("logs", "--tail", "200", CONTAINER_NAME, check=False)
    print(f"\n=== HA Container Logs (last 200 lines) ===\n{result.stdout}")
    if result.stderr:
        print(f"=== HA Container Stderr ===\n{result.stderr}")


def _container_exists() -> bool:
    result = _docker("inspect", CONTAINER_NAME, check=False)
    return result.returncode == 0


def _stop_container() -> None:
    if _container_exists():
        _docker("stop", CONTAINER_NAME, check=False)


def _remove_container() -> None:
    _stop_container()
    if _container_exists():
        _docker("rm", CONTAINER_NAME, check=False)


def _start_container(config_dir: Path) -> None:
    """Start (or restart) the HA container with the given config directory."""
    _docker(
        "run", "-d",
        "--name", CONTAINER_NAME,
        "-p", f"{HA_PORT}:8123",
        "-v", f"{config_dir}:/config",
        HA_IMAGE,
    )


def _restart_container() -> None:
    """Stop and start the existing container (preserves .storage/)."""
    _docker("stop", CONTAINER_NAME)
    _docker("start", CONTAINER_NAME)


def _build_entity_mappings(entities: dict) -> list[dict]:
    """Build device_role entity_mappings from discovered fake_device entities."""
    mappings = []
    for entity_id, info in entities.items():
        domain = info["domain"]
        device_class = info.get("device_class") or ""
        slot = f"{domain}_{device_class}" if device_class else domain
        mappings.append({
            "slot": slot,
            "source_unique_id": info["unique_id"],
            "source_entity_id": entity_id,
            "domain": domain,
            "device_class": device_class,
        })
    return mappings


@pytest.fixture(scope="session")
def config_dir():
    """Create a temporary HA config directory with custom_components."""
    tmpdir = tempfile.mkdtemp(prefix="ha_e2e_")
    config_path = Path(tmpdir)

    # Copy custom_components (device_role only in repo)
    shutil.copytree(CUSTOM_COMPONENTS, config_path / "custom_components")

    # Copy fake_device from test fixtures into the container's custom_components.
    # May already exist if the unit-test conftest.py symlink was followed by copytree above.
    fake_dest = config_path / "custom_components" / "fake_device"
    if not fake_dest.exists():
        shutil.copytree(FAKE_DEVICE_FIXTURE, fake_dest)

    # Minimal configuration.yaml
    (config_path / "configuration.yaml").write_text("homeassistant:\n")

    yield config_path

    # Cleanup
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="session")
def ha_bootstrap(config_dir):
    """Two-phase bootstrap: boot with fake_device, discover IDs, add device_role.

    Returns a dict with discovered device_id and entity_mappings.
    """
    _remove_container()

    # Phase 1: seed only fake_device, boot HA to create device + entities
    seed_config_entries(config_dir, [
        make_fake_device_entry(entry_id=FAKE_DEVICE_ENTRY_ID, name=FAKE_DEVICE_NAME),
    ])

    # Dump seeded config for debugging
    seeded = read_storage_file(config_dir, "core.config_entries")
    print(f"\n=== Seeded config_entries ===\n{json.dumps(seeded, indent=2)}")

    _start_container(config_dir)

    # Wait for HA to be ready and complete onboarding
    client = HAClient(HA_URL)
    try:
        client.wait_for_ready(timeout=120)
        client.onboard_and_authenticate()
        # Give HA a moment to write registries to .storage/
        import time
        time.sleep(5)
    except Exception:
        _dump_container_logs()
        raise
    finally:
        client.close()

    # Stop container so we can read .storage/ safely
    _docker("stop", CONTAINER_NAME)

    # Fix ownership: HA runs as root in Docker, so .storage/ files are root-owned.
    # Make them writable so we can overwrite config_entries for phase 2.
    _docker(
        "run", "--rm",
        "-v", f"{config_dir}:/config",
        HA_IMAGE,
        "bash", "-c", "chmod -R a+rw /config/.storage",
    )

    # Discover fake_device's device_id and entity IDs
    discovered = discover_fake_device_ids(config_dir, FAKE_DEVICE_ENTRY_ID)
    print(f"\n=== Discovered fake_device IDs ===\n{json.dumps(discovered, indent=2)}")

    # Phase 2: add device_role entries and restart
    all_mappings = _build_entity_mappings(discovered["entities"])
    role_1_mappings = [m for m in all_mappings if m["slot"] in ROLE_1_SLOTS]
    role_2_mappings = [m for m in all_mappings if m["slot"] in ROLE_2_SLOTS]

    seed_config_entries(config_dir, [
        make_fake_device_entry(entry_id=FAKE_DEVICE_ENTRY_ID, name=FAKE_DEVICE_NAME),
        make_device_role_entry(
            entry_id=DEVICE_ROLE_ENTRY_ID,
            role_name=ROLE_NAME,
            device_id=discovered["device_id"],
            entity_mappings=role_1_mappings,
        ),
        make_device_role_entry(
            entry_id=DEVICE_ROLE_ENTRY_ID_2,
            role_name=ROLE_NAME_2,
            device_id=discovered["device_id"],
            entity_mappings=role_2_mappings,
        ),
    ])

    _docker("start", CONTAINER_NAME)

    client = HAClient(HA_URL)
    try:
        client.wait_for_ready(timeout=120)
        client.onboard_and_authenticate()
    except Exception:
        _dump_container_logs()
        raise
    finally:
        client.close()

    yield {
        "device_id": discovered["device_id"],
        "entities": discovered["entities"],
        "entity_mappings": role_1_mappings,
        "entity_mappings_2": role_2_mappings,
        "config_dir": config_dir,
    }

    # Teardown: remove container
    _remove_container()


@pytest.fixture
def ha_client(ha_bootstrap):
    """Provide an authenticated HAClient for each test."""
    client = HAClient(HA_URL)
    client.wait_for_ready(timeout=60)
    client.onboard_and_authenticate()
    yield client
    client.close()


@pytest.fixture
def restart_ha():
    """Return a callable that restarts the HA container and waits for ready."""
    def _restart():
        _restart_container()
        client = HAClient(HA_URL)
        try:
            client.wait_for_ready(timeout=120)
            client.onboard_and_authenticate()
        finally:
            client.close()

    return _restart
