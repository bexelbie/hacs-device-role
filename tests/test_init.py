# ABOUTME: Tests for device_role integration setup and teardown.
# ABOUTME: Verifies config entry loading, unloading, and shutdown accumulator save.

import pytest

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.device_role.const import DOMAIN


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_setup_and_unload_entry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test that a config entry can be loaded and unloaded."""
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert DOMAIN in hass.data
    assert mock_config_entry.entry_id in hass.data[DOMAIN]

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.entry_id not in hass.data[DOMAIN]


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_shared_store_manager_created(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test that the shared store manager is created on first entry setup."""
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert "store_manager" in hass.data[DOMAIN]


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_shutdown_saves_accumulators(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test that HA shutdown triggers accumulator save."""
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    store_manager = hass.data[DOMAIN]["store_manager"]
    save_called = False
    original_save = store_manager.async_save_now

    async def track_save():
        nonlocal save_called
        save_called = True
        await original_save()

    store_manager.async_save_now = track_save

    # Fire shutdown event
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    assert save_called


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_remove_entry_purges_accumulators(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry,
) -> None:
    """Test that deleting a config entry purges its accumulator data."""
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    store_manager = hass.data[DOMAIN]["store_manager"]
    # Seed an accumulator for this entry
    acc = store_manager.get_or_create(f"{mock_config_entry.entry_id}_sensor_energy")
    acc.start_session(0.5, "kWh")
    acc.update(1.0)

    # Also seed one for a different entry to confirm it's not removed
    other_acc = store_manager.get_or_create("other_entry_sensor_energy")
    other_acc.start_session(1.5, "kWh")
    other_acc.update(2.0)

    await hass.config_entries.async_remove(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # The entry's accumulator should be gone
    assert f"{mock_config_entry.entry_id}_sensor_energy" not in store_manager._accumulators
    # The other entry's accumulator should remain
    assert "other_entry_sensor_energy" in store_manager._accumulators
