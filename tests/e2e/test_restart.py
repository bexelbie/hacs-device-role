# ABOUTME: E2E restart persistence tests for energy accumulator.
# ABOUTME: Verifies accumulated energy survives real HA container restarts.

import sqlite3
import time
from contextlib import closing
from pathlib import Path

import pytest

from .conftest import _docker, CONTAINER_NAME, HA_IMAGE, HA_URL
from .ha_client import HAClient
from .seed import make_device_role_entry, read_storage_file, write_storage_file


pytestmark = [pytest.mark.e2e]


def _backup_storage_snapshot(config_dir: Path, names: tuple[str, ...]) -> dict[str, dict | None]:
    """Snapshot exact HA storage files the test mutates."""
    snapshot = {}
    storage_dir = config_dir / ".storage"
    storage_dir.mkdir(exist_ok=True)

    for name in names:
        source = storage_dir / name
        snapshot[name] = read_storage_file(config_dir, name)
    return snapshot


def _restore_storage_snapshot(config_dir: Path, snapshot: dict[str, dict | None]) -> None:
    """Restore exact HA storage files without touching unrelated test state."""
    storage_dir = config_dir / ".storage"
    storage_dir.mkdir(exist_ok=True)

    for name, data in snapshot.items():
        destination = storage_dir / name
        if data is None:
            if destination.exists():
                destination.unlink()
        else:
            write_storage_file(config_dir, name, data)


def _read_recorder_raw_state(config_dir: Path, entity_id: str) -> str | None:
    """Read the newest raw state for an entity straight out of the recorder DB.

    Opened read-only so it is safe to poll while HA is running.
    """
    db_path = config_dir / "home-assistant_v2.db"
    if not db_path.exists():
        return None

    try:
        with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
            row = conn.execute(
                """
                SELECT states.state
                FROM states
                JOIN states_meta ON states.metadata_id = states_meta.metadata_id
                WHERE states_meta.entity_id = ?
                ORDER BY states.last_updated_ts DESC, states.state_id DESC
                LIMIT 1
                """,
                (entity_id,),
            ).fetchone()
    except sqlite3.Error:
        return None

    return row[0] if row is not None else None


def _assert_recorder_has_raw_state(config_dir: Path, entity_id: str, expected: str) -> None:
    """Verify HA recorder actually contains the raw pre-restart state."""
    db_path = config_dir / "home-assistant_v2.db"
    assert db_path.exists(), f"Recorder DB missing: {db_path}"

    actual = _read_recorder_raw_state(config_dir, entity_id)
    assert actual is not None, f"Recorder has no state for {entity_id}"
    assert actual == expected, (
        f"Recorder raw state mismatch for {entity_id}: expected {expected}, got {actual}"
    )


def _wait_for_recorder_raw_state(
    config_dir: Path, entity_id: str, expected: str, timeout: float = 30
) -> None:
    """Wait until the recorder has durably committed a raw state.

    The recorder batches writes, so a value visible over the API is not yet
    guaranteed to survive a SIGKILL. Tests that kill the container must confirm
    the value is on disk first, or a failure is ambiguous between "the floor
    did not work" and "there was nothing to read".
    """
    deadline = time.monotonic() + timeout
    actual = None
    while time.monotonic() < deadline:
        actual = _read_recorder_raw_state(config_dir, entity_id)
        if actual == expected:
            return
        time.sleep(0.5)

    raise AssertionError(
        f"Recorder never committed {expected} for {entity_id} within {timeout}s "
        f"(last seen: {actual})"
    )


@pytest.mark.usefixtures("ha_bootstrap")
def test_energy_accumulation_survives_restart(ha_client, restart_ha):
    """Energy accumulated before restart is preserved after restart."""
    # Set initial energy reading
    ha_client.call_service("fake_device", "set_value", {
        "entity_id": "sensor.test_plug_energy",
        "value": 100.0,
    })
    # Wait for the role energy sensor to pick it up.
    # session_start deferred from 0.0 to first non-zero reading (100.0),
    # so role_value = 0 + (100 - 100) = 0.0
    ha_client.wait_for_state(
        "sensor.e2e_role_energy", "0.0", timeout=15,
    )

    # Accumulate 50 kWh delta
    ha_client.call_service("fake_device", "set_value", {
        "entity_id": "sensor.test_plug_energy",
        "value": 150.0,
    })
    state = ha_client.wait_for_state(
        "sensor.e2e_role_energy", "50.0", timeout=15,
    )
    assert state is not None

    # Restart HA container (graceful stop preserves .storage/)
    restart_ha()

    # After restart, fake_device's energy resets to 0.0.
    # The accumulator detects the reset (drop 150→0 > threshold),
    # commits the pre-restart delta (50) to historical_sum,
    # and starts a new session from 0.
    # Set energy to 50 → role_value = 50 (historical) + (50 - 0) = 100
    ha_client.call_service("fake_device", "set_value", {
        "entity_id": "sensor.test_plug_energy",
        "value": 50.0,
    })

    state = ha_client.wait_for_state(
        "sensor.e2e_role_energy", "100.0", timeout=30,
    )
    assert state is not None


@pytest.mark.usefixtures("ha_bootstrap")
def test_energy_survives_unclean_kill(ha_client, ha_bootstrap, restart_ha):
    """An accumulated value survives SIGKILL, where no shutdown handler runs.

    This is the case the recorder floor exists for. A graceful stop lets the
    EVENT_HOMEASSISTANT_STOP handler flush the accumulator, so it proves nothing
    about a power loss or an OOM kill. Here nothing is flushed and no test files
    are touched: whatever is on disk is whatever the running system happened to
    leave there, which is the honest reproduction of an unclean death.
    """
    config_dir = ha_bootstrap["config_dir"]
    source_entity_id = "sensor.test_plug_energy"
    role_entity_id = "sensor.e2e_role_energy"

    # Advance the source so the role holds a delta newer than any store write.
    # STORAGE_SAVE_INTERVAL is 30 minutes, far longer than this suite, so this
    # delta is guaranteed to be unpersisted.
    source_before = float(ha_client.get_state(source_entity_id)["state"])
    ha_client.call_service("fake_device", "set_value", {
        "entity_id": source_entity_id,
        "value": source_before + 50.0,
    })
    time.sleep(3)

    role_before = ha_client.get_state(role_entity_id)["state"]
    assert float(role_before) > 0, (
        "Role value must be non-zero before the kill or the test proves nothing"
    )

    # The recorder batches writes; confirm the floor's only surviving source is
    # actually on disk, so a failure below is unambiguous.
    _wait_for_recorder_raw_state(config_dir, role_entity_id, role_before)

    restart_ha("kill")

    state = ha_client.wait_for_state(role_entity_id, role_before, timeout=30)
    assert state is not None, (
        f"Role value must not decrease after SIGKILL: expected {role_before}, "
        f"got {ha_client.get_state(role_entity_id)}"
    )


@pytest.mark.usefixtures("ha_bootstrap")
def test_upgrade_gap_uses_recorder_floor_on_restart(ha_bootstrap):
    """A v0.4-like restart should restore from the last raw recorder value."""
    config_dir = ha_bootstrap["config_dir"]
    device_id = ha_bootstrap["device_id"]
    config_entry_id = "device_role_e2e_upgrade_gap"
    role_name = "Upgrade Gap"
    source_entity_id = "sensor.test_plug_energy"
    source_unique_id = ha_bootstrap["entities"][source_entity_id]["unique_id"]
    mapping = {
        "slot": "sensor_energy",
        "source_unique_id": source_unique_id,
        "source_entity_id": source_entity_id,
        "domain": "sensor",
        "device_class": "energy",
        "state_class": "total_increasing",
    }

    config_entries = read_storage_file(config_dir, "core.config_entries")
    snapshot = _backup_storage_snapshot(
        config_dir,
        ("core.config_entries", "core.device_registry", "core.entity_registry", "device_role_accumulators.json", "core.restore_state"),
    )
    config_entries["data"]["entries"].append(
        make_device_role_entry(
            entry_id=config_entry_id,
            role_name=role_name,
            device_id=device_id,
            entity_mappings=[mapping],
        )
    )

    try:
        _docker("stop", CONTAINER_NAME)
        _docker(
            "run", "--rm",
            "-v", f"{config_dir}:/config",
            HA_IMAGE,
            "bash", "-c",
            "chmod -R a+rw /config/.storage",
        )
        write_storage_file(config_dir, "core.config_entries", config_entries)
        _docker("start", CONTAINER_NAME)

        client = HAClient(HA_URL)
        try:
            client.wait_for_ready(timeout=120)
            client.onboard_and_authenticate()

            entity_id = "sensor.upgrade_gap_energy"
            client.wait_for_entity(entity_id, timeout=60)

            client.call_service("fake_device", "set_value", {
                "entity_id": source_entity_id,
                "value": 100.0,
            })
            client.wait_for_state(entity_id, "0.0", timeout=15)

            client.call_service("fake_device", "set_value", {
                "entity_id": source_entity_id,
                "value": 140.0,
            })
            state = client.wait_for_state(entity_id, "40.0", timeout=15)
            assert state is not None
            assert float(state["state"]) == 40.0

            # Simulate the upgrade restart: stop HA so recorder flushes the 40.0 raw value,
            # then remove the stale custom persistence files before the next boot.
            _docker("stop", CONTAINER_NAME)
            _assert_recorder_has_raw_state(config_dir, entity_id, "40.0")

            _docker(
                "run", "--rm",
                "-v", f"{config_dir}:/config",
                HA_IMAGE,
                "bash", "-c",
                "chmod -R a+rw /config/.storage",
            )
            accum_state = read_storage_file(config_dir, "device_role_accumulators.json") or {
                "data": {"accumulators": {}}
            }
            accum_state.setdefault("data", {})
            accum_state["data"].setdefault("accumulators", {})
            accum_state["data"]["accumulators"].pop(f"{config_entry_id}_sensor_energy", None)
            write_storage_file(config_dir, "device_role_accumulators.json", accum_state)
            restore_state_path = config_dir / ".storage" / "core.restore_state"
            if restore_state_path.exists():
                restore_state_path.unlink()
            _docker("start", CONTAINER_NAME)

            restart_client = HAClient(HA_URL)
            try:
                restart_client.wait_for_ready(timeout=120)
                restart_client.onboard_and_authenticate()
                restart_client.wait_for_entity(entity_id, timeout=60)

                state = restart_client.wait_for_state(entity_id, "40.0", timeout=30)
                assert state is not None
                assert float(state["state"]) == 40.0, (
                    "Role should restore from the last raw recorder value when store and "
                    "restore data are absent"
                )

                restart_client.call_service("fake_device", "set_value", {
                    "entity_id": source_entity_id,
                    "value": 100.0,
                })
                restart_client.wait_for_state(entity_id, "40.0", timeout=15)

                restart_client.call_service("fake_device", "set_value", {
                    "entity_id": source_entity_id,
                    "value": 160.0,
                })
                state = restart_client.wait_for_state(entity_id, "100.0", timeout=30)
                assert state is not None
                assert float(state["state"]) == 100.0
            finally:
                restart_client.close()
        finally:
            client.close()
    finally:
        _docker("stop", CONTAINER_NAME)
        _docker(
            "run", "--rm",
            "-v", f"{config_dir}:/config",
            HA_IMAGE,
            "bash", "-c",
            "chmod -R a+rw /config/.storage",
        )
        _restore_storage_snapshot(config_dir, snapshot)
        _docker("start", CONTAINER_NAME)


@pytest.mark.usefixtures("ha_bootstrap")
def test_deactivate_commit_survives_restart(ha_client, ha_bootstrap, restart_ha):
    """Energy committed on deactivation is preserved across restart."""
    import time

    # Read the current accumulated energy from prior tests
    state = ha_client.get_state("sensor.e2e_role_energy")
    baseline = float(state["state"])

    # Accumulate some delta on top of baseline
    ha_client.call_service("fake_device", "set_value", {
        "entity_id": "sensor.test_plug_energy",
        "value": 300.0,
    })
    time.sleep(3)
    state = ha_client.get_state("sensor.e2e_role_energy")
    pre_deactivate = float(state["state"])
    assert pre_deactivate > baseline, (
        f"Energy should increase: was {baseline}, now {pre_deactivate}"
    )

    config_dir = ha_bootstrap["config_dir"]

    def _reactivate_role():
        """Re-activate the role so subsequent tests aren't broken."""
        _docker("stop", CONTAINER_NAME)
        _docker(
            "run", "--rm",
            "-v", f"{config_dir}:/config",
            HA_IMAGE,
            "bash", "-c", "chmod -R a+rw /config/.storage",
        )
        entries = read_storage_file(config_dir, "core.config_entries")
        for e in entries["data"]["entries"]:
            if e["entry_id"] == "device_role_e2e":
                e["data"]["active"] = True
        write_storage_file(config_dir, "core.config_entries", entries)
        _docker("start", CONTAINER_NAME)
        cleanup_client = HAClient(HA_URL)
        try:
            cleanup_client.wait_for_ready(timeout=120)
            cleanup_client.onboard_and_authenticate()
        finally:
            cleanup_client.close()

    try:
        # Deactivate the role by updating config entry storage and restarting.
        _docker("stop", CONTAINER_NAME)
        _docker(
            "run", "--rm",
            "-v", f"{config_dir}:/config",
            HA_IMAGE,
            "bash", "-c", "chmod -R a+rw /config/.storage",
        )
        config_entries = read_storage_file(config_dir, "core.config_entries")
        for entry in config_entries["data"]["entries"]:
            if entry["entry_id"] == "device_role_e2e":
                entry["data"]["active"] = False
        write_storage_file(config_dir, "core.config_entries", config_entries)

        _docker("start", CONTAINER_NAME)
        client = HAClient(HA_URL)
        try:
            client.wait_for_ready(timeout=120)
            client.onboard_and_authenticate()

            # Wait for the device_role integration to finish setting up
            # entities after restart. The API is reachable before custom
            # integrations have loaded.
            client.wait_for_entity("sensor.e2e_role_energy", timeout=60)

            # Energy sensor should be frozen (available but not updating).
            state = client.get_state("sensor.e2e_role_energy")
            assert state is not None
            frozen_value = float(state["state"])
            assert frozen_value > 0.0, (
                f"Frozen energy should be positive, got {frozen_value}"
            )
        finally:
            client.close()

        # Restart again to verify committed value persists
        restart_ha()

        state = ha_client.get_state("sensor.e2e_role_energy")
        assert state is not None
        after_restart = float(state["state"])
        assert after_restart == frozen_value, (
            f"Energy should be frozen at {frozen_value} after restart, "
            f"got {after_restart}"
        )
    finally:
        _reactivate_role()
