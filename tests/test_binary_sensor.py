# ABOUTME: Tests for device_role binary sensor entities.
# ABOUTME: Verifies state mirroring and inactive behavior for binary sensors.

import pytest

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
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


def _setup_physical_binary_sensor(hass: HomeAssistant):
    """Create a physical device with a door binary sensor."""
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    source_entry = MockConfigEntry(domain="test", title="test source")
    source_entry.add_to_hass(hass)

    device = device_reg.async_get_or_create(
        config_entry_id=source_entry.entry_id,
        identifiers={("test", "device_1")},
        name="Door Sensor Blue Star",
    )

    entity_entry = entity_reg.async_get_or_create(
        "binary_sensor",
        "test",
        "door_1",
        suggested_object_id="blue_star_door",
        device_id=device.id,
        original_device_class=BinarySensorDeviceClass.DOOR,
        original_name="Door",
    )

    return device, entity_entry


def _make_binary_sensor_role(
    device_id: str,
    source_unique_id: str,
    source_entity_id: str,
    active: bool = True,
) -> MockConfigEntry:
    """Create a mock config entry for a role with one binary sensor."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Front Door",
        data={
            CONF_ROLE_NAME: "Front Door",
            CONF_DEVICE_ID: device_id,
            CONF_ACTIVE: active,
            CONF_ENTITY_MAPPINGS: [
                {
                    CONF_SLOT: "binary_sensor_door",
                    CONF_SOURCE_UNIQUE_ID: source_unique_id,
                    CONF_SOURCE_ENTITY_ID: source_entity_id,
                    CONF_DOMAIN: "binary_sensor",
                    CONF_DEVICE_CLASS: "door",
                },
            ],
        },
    )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_binary_sensor_mirrors_state(hass: HomeAssistant) -> None:
    """Test that a role binary sensor mirrors the physical sensor's state."""
    device, entity_entry = _setup_physical_binary_sensor(hass)
    hass.states.async_set(entity_entry.entity_id, STATE_ON)

    entry = _make_binary_sensor_role(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    role_state = hass.states.get("binary_sensor.front_door_binary_sensor_door")
    assert role_state is not None
    assert role_state.state == STATE_ON


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_binary_sensor_tracks_changes(hass: HomeAssistant) -> None:
    """Test that a role binary sensor updates when the physical sensor changes."""
    device, entity_entry = _setup_physical_binary_sensor(hass)
    hass.states.async_set(entity_entry.entity_id, STATE_OFF)

    entry = _make_binary_sensor_role(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.front_door_binary_sensor_door").state == STATE_OFF

    hass.states.async_set(entity_entry.entity_id, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.front_door_binary_sensor_door").state == STATE_ON


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_binary_sensor_inactive_unavailable(hass: HomeAssistant) -> None:
    """Test that an inactive role binary sensor is unavailable."""
    device, entity_entry = _setup_physical_binary_sensor(hass)
    hass.states.async_set(entity_entry.entity_id, STATE_ON)

    entry = _make_binary_sensor_role(
        device.id, entity_entry.unique_id, entity_entry.entity_id, active=False
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    role_state = hass.states.get("binary_sensor.front_door_binary_sensor_door")
    assert role_state is not None
    assert role_state.state == STATE_UNAVAILABLE


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_binary_sensor_metadata(hass: HomeAssistant) -> None:
    """Test that role binary sensor has correct device_class."""
    device, entity_entry = _setup_physical_binary_sensor(hass)
    hass.states.async_set(entity_entry.entity_id, STATE_ON)

    entry = _make_binary_sensor_role(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_reg = er.async_get(hass)
    role_reg_entry = entity_reg.async_get("binary_sensor.front_door_binary_sensor_door")
    assert role_reg_entry is not None
    assert role_reg_entry.original_device_class == "door"
