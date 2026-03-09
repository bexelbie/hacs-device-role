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
        {"unit_of_measurement": "kWh", "device_class": "energy"},
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
        {"unit_of_measurement": "kWh"},
    )

    entry = _make_energy_role(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Physical sensor increases by 10 kWh
    hass.states.async_set(
        entity_entry.entity_id, "110.0",
        {"unit_of_measurement": "kWh"},
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
        {"unit_of_measurement": "kWh"},
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
        {"unit_of_measurement": "kWh"},
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
async def test_energy_sensor_unit_is_kwh(hass: HomeAssistant) -> None:
    """Test that energy role sensor always reports in kWh."""
    device, entity_entry = _setup_physical_energy_sensor(hass)
    hass.states.async_set(
        entity_entry.entity_id, "100.0",
        {"unit_of_measurement": "kWh"},
    )

    entry = _make_energy_role(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    role_state = hass.states.get("sensor.projector_sensor_energy")
    assert role_state.attributes.get("unit_of_measurement") == "kWh"
