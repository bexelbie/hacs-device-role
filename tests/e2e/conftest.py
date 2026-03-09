# ABOUTME: Pytest fixtures for E2E tests against a real HA Docker container.
# ABOUTME: Manages container lifecycle, two-phase bootstrap, and REST client.

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

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
HA_URL = f"http://localhost:{HA_PORT}"

# Location of custom_components relative to repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
CUSTOM_COMPONENTS = REPO_ROOT / "custom_components"

FAKE_DEVICE_ENTRY_ID = "fake_device_e2e"
DEVICE_ROLE_ENTRY_ID = "device_role_e2e"
ROLE_NAME = "E2E Role"
FAKE_DEVICE_NAME = "test_plug"


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

    # Copy custom_components
    shutil.copytree(CUSTOM_COMPONENTS, config_path / "custom_components")

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

    _start_container(config_dir)

    # Wait for HA to be ready and complete onboarding
    loop = asyncio.new_event_loop()
    try:
        async def _phase1():
            async with HAClient(HA_URL) as client:
                await client.wait_for_ready(timeout=120)
                await client.onboard_and_authenticate()
                # Give HA a moment to write registries to .storage/
                await asyncio.sleep(5)

        loop.run_until_complete(_phase1())
    finally:
        loop.close()

    # Stop container so we can read .storage/ safely
    _docker("stop", CONTAINER_NAME)

    # Discover fake_device's device_id and entity IDs
    discovered = discover_fake_device_ids(config_dir, FAKE_DEVICE_ENTRY_ID)
    _LOGGER.info("Discovered fake_device IDs: %s", discovered)

    # Phase 2: add device_role entry and restart
    entity_mappings = _build_entity_mappings(discovered["entities"])

    seed_config_entries(config_dir, [
        make_fake_device_entry(entry_id=FAKE_DEVICE_ENTRY_ID, name=FAKE_DEVICE_NAME),
        make_device_role_entry(
            entry_id=DEVICE_ROLE_ENTRY_ID,
            role_name=ROLE_NAME,
            device_id=discovered["device_id"],
            entity_mappings=entity_mappings,
        ),
    ])

    _docker("start", CONTAINER_NAME)

    loop = asyncio.new_event_loop()
    try:
        async def _phase2():
            async with HAClient(HA_URL) as client:
                await client.wait_for_ready(timeout=120)
                await client.onboard_and_authenticate()

        loop.run_until_complete(_phase2())
    finally:
        loop.close()

    yield {
        "device_id": discovered["device_id"],
        "entities": discovered["entities"],
        "entity_mappings": entity_mappings,
        "config_dir": config_dir,
    }

    # Teardown: remove container
    _remove_container()


@pytest_asyncio.fixture
async def ha_client(ha_bootstrap):
    """Provide an authenticated HAClient for each test."""
    async with HAClient(HA_URL) as client:
        await client.wait_for_ready(timeout=60)
        await client.onboard_and_authenticate()
        yield client


@pytest.fixture
def restart_ha():
    """Return a callable that restarts the HA container and waits for ready."""
    async def _restart():
        _restart_container()
        async with HAClient(HA_URL) as client:
            await client.wait_for_ready(timeout=120)
            await client.onboard_and_authenticate()

    def sync_restart():
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_restart())
        finally:
            loop.close()

    return sync_restart
