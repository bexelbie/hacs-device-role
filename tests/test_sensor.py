# ABOUTME: Tests for device_role measurement sensor entities.
# ABOUTME: Verifies state mirroring, metadata propagation, and inactive behavior.

import pytest

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature, STATE_UNAVAILABLE
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


def _setup_physical_device(hass: HomeAssistant):
    """Create a physical device with a temperature sensor entity."""
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
        "temp_1",
        suggested_object_id="orange_heart_temperature",
        device_id=device.id,
        original_device_class=SensorDeviceClass.TEMPERATURE,
        original_name="Temperature",
        unit_of_measurement=UnitOfTemperature.CELSIUS,
    )

    return device, entity_entry


def _make_role_entry(
    device_id: str,
    source_unique_id: str,
    source_entity_id: str,
    active: bool = True,
    role_name: str = "Balcony",
) -> MockConfigEntry:
    """Create a mock config entry for a role with one temperature sensor."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=role_name,
        data={
            CONF_ROLE_NAME: role_name,
            CONF_DEVICE_ID: device_id,
            CONF_ACTIVE: active,
            CONF_ENTITY_MAPPINGS: [
                {
                    CONF_SLOT: "sensor_temperature",
                    CONF_SOURCE_UNIQUE_ID: source_unique_id,
                    CONF_SOURCE_ENTITY_ID: source_entity_id,
                    CONF_DOMAIN: "sensor",
                    CONF_DEVICE_CLASS: "temperature",
                },
            ],
        },
    )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_measurement_sensor_mirrors_state(hass: HomeAssistant) -> None:
    """Test that a role sensor mirrors the physical sensor's state."""
    device, entity_entry = _setup_physical_device(hass)

    # Set up the physical sensor state
    hass.states.async_set(
        entity_entry.entity_id, "22.5",
        {"unit_of_measurement": "°C", "device_class": "temperature"},
    )

    entry = _make_role_entry(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # The role sensor should mirror the physical value
    role_state = hass.states.get(f"sensor.balcony_temperature")
    assert role_state is not None
    assert role_state.state == "22.5"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_measurement_sensor_tracks_changes(hass: HomeAssistant) -> None:
    """Test that a role sensor updates when the physical sensor changes."""
    device, entity_entry = _setup_physical_device(hass)

    hass.states.async_set(entity_entry.entity_id, "20.0")

    entry = _make_role_entry(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Update the physical sensor
    hass.states.async_set(entity_entry.entity_id, "25.3")
    await hass.async_block_till_done()

    role_state = hass.states.get(f"sensor.balcony_temperature")
    assert role_state is not None
    assert role_state.state == "25.3"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_measurement_sensor_metadata(hass: HomeAssistant) -> None:
    """Test that role sensor copies device_class and state_class from source."""
    device, entity_entry = _setup_physical_device(hass)

    hass.states.async_set(
        entity_entry.entity_id, "22.0",
        {"state_class": "measurement"},
    )

    entry = _make_role_entry(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    role_entity_id = f"sensor.balcony_temperature"
    role_state = hass.states.get(role_entity_id)
    assert role_state is not None
    assert role_state.attributes.get("state_class") == "measurement"

    # Check entity registry for metadata
    entity_reg = er.async_get(hass)
    role_reg_entry = entity_reg.async_get(role_entity_id)
    assert role_reg_entry is not None
    assert role_reg_entry.original_device_class == "temperature"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_inactive_role_sensor_unavailable(hass: HomeAssistant) -> None:
    """Test that a measurement sensor for an inactive role is unavailable."""
    device, entity_entry = _setup_physical_device(hass)

    hass.states.async_set(entity_entry.entity_id, "22.0")

    entry = _make_role_entry(
        device.id, entity_entry.unique_id, entity_entry.entity_id, active=False
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    role_state = hass.states.get(f"sensor.balcony_temperature")
    assert role_state is not None
    assert role_state.state == STATE_UNAVAILABLE


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_sensor_resolves_entity_id_from_unique_id(hass: HomeAssistant) -> None:
    """Test that mirroring works even if the source entity_id was renamed."""
    device, entity_entry = _setup_physical_device(hass)

    # Record the original entity_id in the role config
    original_entity_id = entity_entry.entity_id

    # Rename the entity in the registry (simulates user rename)
    entity_reg = er.async_get(hass)
    entity_reg.async_update_entity(
        original_entity_id, new_entity_id="sensor.renamed_temperature"
    )

    # Set state on the new entity_id
    hass.states.async_set(
        "sensor.renamed_temperature", "19.5",
        {"unit_of_measurement": "°C", "device_class": "temperature"},
    )

    # Role config still has the OLD entity_id, but has the correct unique_id
    entry = _make_role_entry(
        device.id, entity_entry.unique_id, original_entity_id
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    role_state = hass.states.get("sensor.balcony_temperature")
    assert role_state is not None
    assert role_state.state == "19.5"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_role_creates_device(hass: HomeAssistant) -> None:
    """Test that a role creates its own logical device in the device registry."""
    device, entity_entry = _setup_physical_device(hass)

    hass.states.async_set(entity_entry.entity_id, "22.0")

    entry = _make_role_entry(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # The role entity should be on a role device, not the physical device
    entity_reg = er.async_get(hass)
    role_reg_entry = entity_reg.async_get(f"sensor.balcony_temperature")
    assert role_reg_entry is not None
    assert role_reg_entry.device_id is not None

    device_reg = dr.async_get(hass)
    role_device = device_reg.async_get(role_reg_entry.device_id)
    assert role_device is not None
    assert role_device.name == "Balcony"
