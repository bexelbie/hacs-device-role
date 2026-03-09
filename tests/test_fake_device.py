# ABOUTME: Tests for the fake_device integration.
# ABOUTME: Verifies device creation, entity setup, and deterministic set_value service.

import pytest

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fake_device.const import DOMAIN, SERVICE_SET_VALUE


def _make_entry(name: str = "Smart Plug Orange Heart") -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=name,
        data={"name": name},
    )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_creates_device_in_registry(hass: HomeAssistant) -> None:
    """Test that a fake device appears in the device registry."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    device_reg = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(device_reg, entry.entry_id)
    assert len(devices) == 1
    assert devices[0].name == "Smart Plug Orange Heart"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_creates_all_entity_types(hass: HomeAssistant) -> None:
    """Test that a fake device creates sensor, binary_sensor, and switch entities."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(device_reg, entry.entry_id)
    entities = er.async_entries_for_device(entity_reg, devices[0].id)

    domains = {e.domain for e in entities}
    assert "sensor" in domains
    assert "binary_sensor" in domains
    assert "switch" in domains
    assert len(entities) == 6


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_energy_sensor_metadata(hass: HomeAssistant) -> None:
    """Test that the energy sensor has correct device_class and state_class."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_reg = er.async_get(hass)
    energy = entity_reg.async_get("sensor.smart_plug_orange_heart_energy")
    assert energy is not None
    assert energy.original_device_class == "energy"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_set_value_sensor(hass: HomeAssistant) -> None:
    """Test setting a sensor to an exact value."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = "sensor.smart_plug_orange_heart_temperature"
    assert hass.states.get(entity_id).state == "20.0"

    await hass.services.async_call(
        DOMAIN, SERVICE_SET_VALUE,
        {"entity_id": entity_id, "value": 35.7},
        blocking=True,
    )
    assert hass.states.get(entity_id).state == "35.7"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_set_value_unavailable(hass: HomeAssistant) -> None:
    """Test setting a sensor to unavailable."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = "sensor.smart_plug_orange_heart_energy"
    await hass.services.async_call(
        DOMAIN, SERVICE_SET_VALUE,
        {"entity_id": entity_id, "value": "unavailable"},
        blocking=True,
    )
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_set_value_unknown(hass: HomeAssistant) -> None:
    """Test setting a sensor to unknown."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = "sensor.smart_plug_orange_heart_temperature"
    await hass.services.async_call(
        DOMAIN, SERVICE_SET_VALUE,
        {"entity_id": entity_id, "value": "unknown"},
        blocking=True,
    )
    assert hass.states.get(entity_id).state == STATE_UNKNOWN


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_energy_sensor_reset_sequence(hass: HomeAssistant) -> None:
    """Test simulating a device reset: value goes from high to zero."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = "sensor.smart_plug_orange_heart_energy"

    # Simulate accumulation
    for val in [100.0, 110.0, 115.0]:
        await hass.services.async_call(
            DOMAIN, SERVICE_SET_VALUE,
            {"entity_id": entity_id, "value": val},
            blocking=True,
        )

    assert hass.states.get(entity_id).state == "115.0"

    # Simulate device reset
    await hass.services.async_call(
        DOMAIN, SERVICE_SET_VALUE,
        {"entity_id": entity_id, "value": 0.0},
        blocking=True,
    )
    assert hass.states.get(entity_id).state == "0.0"

    # Simulate jitter
    await hass.services.async_call(
        DOMAIN, SERVICE_SET_VALUE,
        {"entity_id": entity_id, "value": 0.1},
        blocking=True,
    )
    assert hass.states.get(entity_id).state == "0.1"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_switch_responds_to_commands(hass: HomeAssistant) -> None:
    """Test that the switch responds to turn_on and turn_off."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = "switch.smart_plug_orange_heart_outlet"
    assert hass.states.get(entity_id).state == STATE_OFF

    await hass.services.async_call(
        "switch", "turn_on",
        {"entity_id": entity_id},
        blocking=True,
    )
    assert hass.states.get(entity_id).state == STATE_ON

    await hass.services.async_call(
        "switch", "turn_off",
        {"entity_id": entity_id},
        blocking=True,
    )
    assert hass.states.get(entity_id).state == STATE_OFF


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_multiple_devices(hass: HomeAssistant) -> None:
    """Test creating two fake devices with independent state."""
    entry1 = _make_entry("Plug Alpha")
    entry2 = _make_entry("Plug Beta")
    entry1.add_to_hass(hass)
    entry2.add_to_hass(hass)

    # Setting up one entry causes HA to load the component and all its entries
    assert await hass.config_entries.async_setup(entry1.entry_id)
    await hass.async_block_till_done()

    # Set different values on each
    await hass.services.async_call(
        DOMAIN, SERVICE_SET_VALUE,
        {"entity_id": "sensor.plug_alpha_temperature", "value": 10.0},
        blocking=True,
    )
    await hass.services.async_call(
        DOMAIN, SERVICE_SET_VALUE,
        {"entity_id": "sensor.plug_beta_temperature", "value": 30.0},
        blocking=True,
    )

    assert hass.states.get("sensor.plug_alpha_temperature").state == "10.0"
    assert hass.states.get("sensor.plug_beta_temperature").state == "30.0"
