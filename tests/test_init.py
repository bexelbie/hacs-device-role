# ABOUTME: Tests for device_role integration setup and teardown.
# ABOUTME: Verifies config entry loading, unloading, and shutdown accumulator save.

import pytest
import attr

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.device_role.const import (
    CONF_ACTIVE,
    CONF_DEVICE_CLASS,
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_MAPPINGS,
    CONF_ROLE_NAME,
    CONF_SLOT,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_UNIQUE_ID,
    DEVICE_SPLIT_ISSUE,
    DOMAIN,
)
from homeassistant.helpers import issue_registry as ir


def _mark_device_as_split(
    device_reg: dr.DeviceRegistry,
    device: dr.DeviceEntry,
    composite_id: str,
) -> dr.DeviceEntry:
    """Model a device registry entry created by the 2026.8 split migration."""
    split = attr.evolve(
        device,
        composite_device_id=composite_id,
        composite_primary_config_entry=device.config_entry_id,
    )
    device_reg.devices[device.id] = split
    return split


def _create_source(
    hass: HomeAssistant,
    *,
    name: str,
    identifier: str,
) -> tuple[dr.DeviceEntry, er.RegistryEntry]:
    """Create a physical device and one source sensor."""
    source_entry = MockConfigEntry(domain="test", title=f"{name} source")
    source_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=source_entry.entry_id,
        identifiers={("test", identifier)},
        name=name,
    )
    source = er.async_get(hass).async_get_or_create(
        "sensor",
        "test",
        f"{identifier}_temperature",
        suggested_object_id=f"{identifier}_temperature",
        device_id=device.id,
        original_name="Temperature",
        original_device_class="temperature",
    )
    hass.states.async_set(source.entity_id, "22")
    return device, source


def _role_entry(
    *,
    role_name: str,
    device_id: str,
    mappings: list[dict],
) -> MockConfigEntry:
    """Create a role entry for setup tests."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=role_name,
        data={
            CONF_ROLE_NAME: role_name,
            CONF_DEVICE_ID: device_id,
            CONF_ACTIVE: True,
            CONF_ENTITY_MAPPINGS: mappings,
        },
    )


def _mapping(source: er.RegistryEntry, slot: str) -> dict:
    """Build a role source mapping."""
    return {
        CONF_SLOT: slot,
        CONF_SOURCE_UNIQUE_ID: source.unique_id,
        CONF_SOURCE_ENTITY_ID: source.entity_id,
        CONF_DOMAIN: "sensor",
        CONF_DEVICE_CLASS: "temperature",
    }


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_composite_role_device_is_canonicalized_in_place(
    hass: HomeAssistant,
) -> None:
    """A composite source ID is replaced with its one concrete source device."""
    device_reg = dr.async_get(hass)
    device, source = _create_source(
        hass, name="Split Device", identifier="split_device_a"
    )
    composite_id = "pre_2026_8_composite"
    _mark_device_as_split(device_reg, device, composite_id)

    entry = _role_entry(
        role_name="Projector",
        device_id=composite_id,
        mappings=[_mapping(source, "sensor_temperature")],
    )
    entry.add_to_hass(hass)
    role_device = device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="Projector",
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.data[CONF_DEVICE_ID] == device.id
    assert device_reg.async_get(role_device.id).id == role_device.id
    assert device_reg.async_get(role_device.id).via_device_id == device.id
    assert hass.states.get("sensor.projector_temperature") is not None
    assert ir.async_get(hass).async_get_issue(
        DOMAIN, f"{DEVICE_SPLIT_ISSUE}_{entry.entry_id}"
    ) is None


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_ambiguous_composite_role_keeps_entities_and_creates_targeted_repair(
    hass: HomeAssistant,
) -> None:
    """Different split source devices create only the role-specific repair."""
    device_reg = dr.async_get(hass)
    device_a, source_a = _create_source(
        hass, name="Split Device A", identifier="split_device_a"
    )
    device_b, source_b = _create_source(
        hass, name="Split Device B", identifier="split_device_b"
    )
    composite_id = "pre_2026_8_composite"
    _mark_device_as_split(device_reg, device_a, composite_id)
    _mark_device_as_split(device_reg, device_b, composite_id)

    entry = _role_entry(
        role_name="Projector",
        device_id=composite_id,
        mappings=[
            _mapping(source_a, "sensor_temperature"),
            _mapping(source_b, "sensor_temperature_2"),
        ],
    )
    entry.add_to_hass(hass)
    role_device = device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="Projector",
        via_device_id=device_a.id,
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"{DEVICE_SPLIT_ISSUE}_{entry.entry_id}"
    )
    assert issue is not None
    assert issue.translation_key == DEVICE_SPLIT_ISSUE
    assert issue.severity.value == "warning"
    assert device_reg.async_get(role_device.id).via_device_id is None
    assert hass.states.get("sensor.projector_temperature") is not None
    assert hass.states.get("sensor.projector_temperature_2") is not None


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_configuring_ambiguous_role_canonicalizes_and_clears_repair(
    hass: HomeAssistant,
) -> None:
    """Choosing one split source persists its device ID and clears the repair."""
    device_reg = dr.async_get(hass)
    device_a, source_a = _create_source(
        hass, name="Split Device A", identifier="split_device_a"
    )
    device_b, source_b = _create_source(
        hass, name="Split Device B", identifier="split_device_b"
    )
    composite_id = "pre_2026_8_composite"
    _mark_device_as_split(device_reg, device_a, composite_id)
    _mark_device_as_split(device_reg, device_b, composite_id)

    entry = _role_entry(
        role_name="Projector",
        device_id=composite_id,
        mappings=[
            _mapping(source_a, "sensor_temperature"),
            _mapping(source_b, "sensor_temperature_2"),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    issue_id = f"{DEVICE_SPLIT_ISSUE}_{entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    response = await hass.services.async_call(
        DOMAIN,
        "configure_entities",
        {
            "config_entry_id": entry.entry_id,
            "entity_ids": [source_a.entity_id],
        },
        blocking=True,
        return_response=True,
    )
    assert response["role"]["device_id"] == device_a.id
    assert entry.data[CONF_DEVICE_ID] == device_a.id
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


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
