# ABOUTME: Tests for device_role integration setup and teardown.
# ABOUTME: Verifies config entry loading, unloading, and shutdown accumulator save.

import pytest
import attr

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, MAJOR_VERSION, MINOR_VERSION
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
    CONF_STATE_CLASS,
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
    device_class: str = "temperature",
    unit_of_measurement: str | None = None,
    state_class: str | None = None,
    initial_state: str = "22",
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
        original_device_class=device_class,
        unit_of_measurement=unit_of_measurement,
    )
    attributes = {}
    if unit_of_measurement is not None:
        attributes["unit_of_measurement"] = unit_of_measurement
    if state_class is not None:
        attributes["state_class"] = state_class
    hass.states.async_set(source.entity_id, initial_state, attributes)
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


def _mapping(
    source: er.RegistryEntry,
    slot: str,
    *,
    device_class: str = "temperature",
    state_class: str | None = None,
) -> dict:
    """Build a role source mapping."""
    mapping = {
        CONF_SLOT: slot,
        CONF_SOURCE_UNIQUE_ID: source.unique_id,
        CONF_SOURCE_ENTITY_ID: source.entity_id,
        CONF_DOMAIN: "sensor",
        CONF_DEVICE_CLASS: device_class,
    }
    if state_class is not None:
        mapping[CONF_STATE_CLASS] = state_class
    return mapping


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
        hass,
        name="Split Device A",
        identifier="split_device_a",
        device_class="energy",
        unit_of_measurement="kWh",
        state_class="total_increasing",
        initial_state="100",
    )
    device_b, source_b = _create_source(
        hass,
        name="Split Device B",
        identifier="split_device_b",
        device_class="energy",
        unit_of_measurement="kWh",
        state_class="total_increasing",
        initial_state="200",
    )
    composite_id = "pre_2026_8_composite"
    _mark_device_as_split(device_reg, device_a, composite_id)
    _mark_device_as_split(device_reg, device_b, composite_id)

    entry = _role_entry(
        role_name="Projector",
        device_id=composite_id,
        mappings=[
            _mapping(
                source_a,
                "sensor_energy",
                device_class="energy",
                state_class="total_increasing",
            ),
            _mapping(
                source_b,
                "sensor_energy_2",
                device_class="energy",
                state_class="total_increasing",
            ),
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
    entity_reg = er.async_get(hass)
    role_energy_entity_id = entity_reg.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_sensor_energy"
    )
    assert role_energy_entity_id is not None
    role_state = hass.states.get(role_energy_entity_id)
    assert role_state is not None
    assert float(role_state.state) == 0.0
    role_energy_entity_id_2 = entity_reg.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_sensor_energy_2"
    )
    assert role_energy_entity_id_2 is not None
    assert hass.states.get(role_energy_entity_id_2) is not None

    hass.states.async_set(
        source_a.entity_id,
        "110",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )
    await hass.async_block_till_done()
    updated_role_state = hass.states.get(role_energy_entity_id)
    assert updated_role_state is not None
    assert float(updated_role_state.state) == 10.0

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(
        DOMAIN, f"{DEVICE_SPLIT_ISSUE}_{entry.entry_id}"
    ) is None


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_role_from_main_device_behind_hub_keeps_via_link(
    hass: HomeAssistant,
) -> None:
    """A main device behind a hub remains a valid Connected-via target."""
    parent, _ = _create_source(
        hass, name="Parent Device", identifier="parent_device"
    )
    source_entry = MockConfigEntry(domain="test", title="Hub device source")
    source_entry.add_to_hass(hass)
    device_reg = dr.async_get(hass)
    device = device_reg.async_get_or_create(
        config_entry_id=source_entry.entry_id,
        identifiers={("test", "hub_device")},
        name="Hub Device",
        via_device_id=parent.id,
    )
    source = er.async_get(hass).async_get_or_create(
        "sensor",
        "test",
        "hub_temperature",
        suggested_object_id="hub_temperature",
        device_id=device.id,
        original_name="Temperature",
        original_device_class="temperature",
    )
    hass.states.async_set(source.entity_id, "22")

    entry = _role_entry(
        role_name="Projector",
        device_id=device.id,
        mappings=[_mapping(source, "sensor_temperature")],
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    role_state = hass.states.get("sensor.projector_temperature")
    assert role_state is not None
    role_entry = er.async_get(hass).async_get("sensor.projector_temperature")
    assert role_entry is not None
    assert role_entry.device_id is not None
    role_device = device_reg.async_get(role_entry.device_id)
    assert role_device is not None
    assert role_device.via_device_id == device.id


@pytest.mark.skipif(
    (MAJOR_VERSION, MINOR_VERSION) < (2026, 9),
    reason="requires Home Assistant 2026.9 child devices",
)
@pytest.mark.usefixtures("enable_custom_integrations")
async def test_role_from_child_device_omits_via_link(hass: HomeAssistant) -> None:
    """A role sourced from a child device still loads without a parent link."""
    source_entry = MockConfigEntry(domain="test", title="Child source")
    source_entry.add_to_hass(hass)
    device_reg = dr.async_get(hass)
    parent = device_reg.async_get_or_create(
        config_entry_id=source_entry.entry_id,
        identifiers={("test", "parent_device")},
        name="Parent Device",
    )
    child = device_reg.async_get_or_create_child(
        config_entry_id=source_entry.entry_id,
        identifiers={("test", "child_device")},
        name="Child Device",
        parent_device_id=parent.id,
    )
    source = er.async_get(hass).async_get_or_create(
        "sensor",
        "test",
        "child_temperature",
        suggested_object_id="child_temperature",
        device_id=child.id,
        original_name="Temperature",
        original_device_class="temperature",
    )
    hass.states.async_set(source.entity_id, "22")

    entry = _role_entry(
        role_name="Projector",
        device_id=child.id,
        mappings=[_mapping(source, "sensor_temperature")],
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    role_state = hass.states.get("sensor.projector_temperature")
    assert role_state is not None
    role_entry = er.async_get(hass).async_get("sensor.projector_temperature")
    assert role_entry is not None
    assert role_entry.device_id is not None
    role_device = device_reg.async_get(role_entry.device_id)
    assert role_device is not None
    assert role_device.via_device_id is None


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
