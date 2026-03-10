# ABOUTME: Tests for device_role energy sensor entities with accumulator.
# ABOUTME: Verifies accumulator integration, persistence, and frozen-when-inactive behavior.

import pytest

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import STATE_UNAVAILABLE, UnitOfEnergy
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
    DOMAIN,
)


def _setup_physical_energy_sensor(hass: HomeAssistant):
    """Create a physical device with an energy sensor entity."""
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    source_entry = MockConfigEntry(domain="test", title="test source")
    source_entry.add_to_hass(hass)

    device = device_reg.async_get_or_create(
        config_entry_id=source_entry.entry_id,
        identifiers={("test", "device_1")},
        name="Smart Plug Orange Heart",
    )

    entity_entry = entity_reg.async_get_or_create(
        "sensor",
        "test",
        "energy_1",
        suggested_object_id="orange_heart_energy",
        device_id=device.id,
        original_device_class=SensorDeviceClass.ENERGY,
        original_name="Energy",
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )

    return device, entity_entry


def _make_energy_role(
    device_id: str,
    source_unique_id: str,
    source_entity_id: str,
    active: bool = True,
    role_name: str = "Projector",
) -> MockConfigEntry:
    """Create a mock config entry for a role with one energy sensor."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=role_name,
        data={
            CONF_ROLE_NAME: role_name,
            CONF_DEVICE_ID: device_id,
            CONF_ACTIVE: active,
            CONF_ENTITY_MAPPINGS: [
                {
                    CONF_SLOT: "sensor_energy",
                    CONF_SOURCE_UNIQUE_ID: source_unique_id,
                    CONF_SOURCE_ENTITY_ID: source_entity_id,
                    CONF_DOMAIN: "sensor",
                    CONF_DEVICE_CLASS: "energy",
                },
            ],
        },
    )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_energy_sensor_starts_at_zero(hass: HomeAssistant) -> None:
    """Test that a new energy role sensor starts at zero."""
    device, entity_entry = _setup_physical_energy_sensor(hass)
    hass.states.async_set(
        entity_entry.entity_id, "100.0",
        {"unit_of_measurement": "kWh", "device_class": "energy", "state_class": "total_increasing"},
    )

    entry = _make_energy_role(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    role_state = hass.states.get("sensor.projector_sensor_energy")
    assert role_state is not None
    assert float(role_state.state) == 0.0


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_energy_sensor_accumulates_deltas(hass: HomeAssistant) -> None:
    """Test that the energy sensor tracks deltas from the physical sensor."""
    device, entity_entry = _setup_physical_energy_sensor(hass)
    hass.states.async_set(
        entity_entry.entity_id, "100.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )

    entry = _make_energy_role(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Physical sensor increases by 10 kWh
    hass.states.async_set(
        entity_entry.entity_id, "110.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )
    await hass.async_block_till_done()

    role_state = hass.states.get("sensor.projector_sensor_energy")
    assert float(role_state.state) == 10.0


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_energy_sensor_metadata(hass: HomeAssistant) -> None:
    """Test that energy sensor has correct device_class and state_class."""
    device, entity_entry = _setup_physical_energy_sensor(hass)
    hass.states.async_set(
        entity_entry.entity_id, "100.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )

    entry = _make_energy_role(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_reg = er.async_get(hass)
    role_reg_entry = entity_reg.async_get("sensor.projector_sensor_energy")
    assert role_reg_entry is not None
    assert role_reg_entry.original_device_class == "energy"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_energy_sensor_frozen_when_inactive(hass: HomeAssistant) -> None:
    """Test that inactive energy sensor stays available but frozen."""
    device, entity_entry = _setup_physical_energy_sensor(hass)
    hass.states.async_set(
        entity_entry.entity_id, "100.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )

    entry = _make_energy_role(
        device.id, entity_entry.unique_id, entity_entry.entity_id, active=False
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    role_state = hass.states.get("sensor.projector_sensor_energy")
    assert role_state is not None
    # Energy sensors should remain available but frozen, not unavailable
    assert role_state.state != STATE_UNAVAILABLE
    assert float(role_state.state) == 0.0


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_energy_sensor_preserves_session_across_restart(
    hass: HomeAssistant,
) -> None:
    """Test that restarting HA does not lose accumulated energy."""
    device, entity_entry = _setup_physical_energy_sensor(hass)

    # Physical meter at 100 kWh, role accumulates 10 kWh delta
    hass.states.async_set(
        entity_entry.entity_id, "100.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )

    entry = _make_energy_role(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Meter increases to 110 → role should show 10
    hass.states.async_set(
        entity_entry.entity_id, "110.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )
    await hass.async_block_till_done()

    role_state = hass.states.get("sensor.projector_sensor_energy")
    assert float(role_state.state) == 10.0

    # Simulate restart: unload preserves the active session (role still active),
    # then reload resumes tracking. Downtime energy (110→112) is attributed.
    store_manager = hass.data[DOMAIN]["store_manager"]
    await store_manager.async_save_now()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set(
        entity_entry.entity_id, "112.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Role shows historical (0) + delta from restored session (112-100=12) = 12
    role_state = hass.states.get("sensor.projector_sensor_energy")
    assert role_state is not None
    assert float(role_state.state) == 12.0

    # Meter advances further — role continues tracking
    hass.states.async_set(
        entity_entry.entity_id, "115.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )
    await hass.async_block_till_done()

    role_state = hass.states.get("sensor.projector_sensor_energy")
    assert float(role_state.state) == 15.0


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_energy_sensor_commits_on_deactivate(hass: HomeAssistant) -> None:
    """Test that unloading commits the session delta to historical sum."""
    device, entity_entry = _setup_physical_energy_sensor(hass)
    hass.states.async_set(
        entity_entry.entity_id, "100.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )

    entry = _make_energy_role(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Accumulate 10 kWh
    hass.states.async_set(
        entity_entry.entity_id, "110.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )
    await hass.async_block_till_done()

    # Get the accumulator and verify session is active
    store_manager = hass.data[DOMAIN]["store_manager"]
    acc_key = f"{entry.entry_id}_sensor_energy"
    accumulator = store_manager.get_or_create(acc_key)
    assert accumulator.session_active is True

    # Deactivate the role (set active=False) then unload — session should commit
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_ACTIVE: False}
    )
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # Session should be committed: historical_sum=10, no active session
    assert accumulator.session_active is False
    assert accumulator.role_value == 10.0


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_energy_sensor_reassignment_commits_session(
    hass: HomeAssistant,
) -> None:
    """Test that reassigning to a new device commits the old session correctly."""
    # Device A: energy at 100, role accumulates 10 kWh (100→110)
    device_a, energy_a = _setup_physical_energy_sensor(hass)
    hass.states.async_set(
        energy_a.entity_id, "100.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )

    entry = _make_energy_role(
        device_a.id, energy_a.unique_id, energy_a.entity_id
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set(
        energy_a.entity_id, "110.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )
    await hass.async_block_till_done()

    role_state = hass.states.get("sensor.projector_sensor_energy")
    assert float(role_state.state) == 10.0

    # Device B: energy at 500 (much higher — different lifetime counter)
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    source_b = MockConfigEntry(domain="test", title="test b")
    source_b.add_to_hass(hass)

    device_b = device_reg.async_get_or_create(
        config_entry_id=source_b.entry_id,
        identifiers={("test", "device_b")},
        name="Smart Plug Beta",
    )
    energy_b = entity_reg.async_get_or_create(
        "sensor", "test", "energy_b",
        suggested_object_id="beta_energy",
        device_id=device_b.id,
        original_device_class=SensorDeviceClass.ENERGY,
        original_name="Energy",
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )
    hass.states.async_set(
        energy_b.entity_id, "500.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )

    # Reassign via options flow: init → change_device → select_device → select_entities
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_ACTIVE: True, "change_device": True},
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_DEVICE_ID: device_b.id},
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"entities": [energy_b.entity_id]},
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()

    # Role should show 10 (from device A) + 0 (fresh session on device B) = 10
    # NOT 10 + (500-100) = 410
    role_state = hass.states.get("sensor.projector_sensor_energy")
    assert role_state is not None
    assert float(role_state.state) == 10.0

    # Device B advances by 3 kWh → role should show 13
    hass.states.async_set(
        energy_b.entity_id, "503.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )
    await hass.async_block_till_done()

    role_state = hass.states.get("sensor.projector_sensor_energy")
    assert float(role_state.state) == 13.0


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_energy_sensor_unit_is_kwh(hass: HomeAssistant) -> None:
    """Test that energy role sensor always reports in kWh."""
    device, entity_entry = _setup_physical_energy_sensor(hass)
    hass.states.async_set(
        entity_entry.entity_id, "100.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )

    entry = _make_energy_role(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    role_state = hass.states.get("sensor.projector_sensor_energy")
    assert role_state.attributes.get("unit_of_measurement") == "kWh"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_energy_sensor_ignores_unsupported_unit(hass: HomeAssistant) -> None:
    """Test that readings with unsupported units are silently dropped."""
    device, entity_entry = _setup_physical_energy_sensor(hass)
    # Start with a valid kWh reading to initialize the session
    hass.states.async_set(
        entity_entry.entity_id, "100.0",
        {"unit_of_measurement": "kWh", "device_class": "energy", "state_class": "total_increasing"},
    )

    entry = _make_energy_role(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Accumulate some valid kWh energy
    hass.states.async_set(
        entity_entry.entity_id, "110.0",
        {"unit_of_measurement": "kWh", "device_class": "energy", "state_class": "total_increasing"},
    )
    await hass.async_block_till_done()

    role_state = hass.states.get("sensor.projector_sensor_energy")
    assert float(role_state.state) == pytest.approx(10.0)

    # Now the source switches to an unsupported unit — should be ignored
    hass.states.async_set(
        entity_entry.entity_id, "999999.0",
        {"unit_of_measurement": "J", "device_class": "energy", "state_class": "total_increasing"},
    )
    await hass.async_block_till_done()

    role_state = hass.states.get("sensor.projector_sensor_energy")
    assert float(role_state.state) == pytest.approx(10.0)


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_energy_session_committed_on_mapping_removal(
    hass: HomeAssistant,
) -> None:
    """Test that removing an energy mapping from an active role commits the session."""
    device, entity_entry = _setup_physical_energy_sensor(hass)
    hass.states.async_set(
        entity_entry.entity_id, "100.0",
        {"unit_of_measurement": "kWh", "device_class": "energy", "state_class": "total_increasing"},
    )

    entry = _make_energy_role(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Accumulate 10 kWh
    hass.states.async_set(
        entity_entry.entity_id, "110.0",
        {"unit_of_measurement": "kWh", "device_class": "energy", "state_class": "total_increasing"},
    )
    await hass.async_block_till_done()

    role_state = hass.states.get("sensor.projector_sensor_energy")
    assert float(role_state.state) == pytest.approx(10.0)

    # Remove the energy mapping while role stays active (simulates options flow).
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_ENTITY_MAPPINGS: []},
    )
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    # The session should have been committed (historical_sum = 10, session_active = False)
    store_manager = hass.data[DOMAIN]["store_manager"]
    acc_key = f"{entry.entry_id}_sensor_energy"
    acc = store_manager._accumulators.get(acc_key)
    assert acc is not None
    acc_data = acc.to_dict()
    assert acc_data["historical_sum"] == pytest.approx(10.0)
    assert acc_data["session_active"] is False
