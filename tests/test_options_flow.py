# ABOUTME: Tests for the device_role options flow.
# ABOUTME: Covers toggling active state and adding/removing entity mappings.

import pytest

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import STATE_UNAVAILABLE
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


def _setup_device_with_sensor(hass, name="Smart Plug", identifiers=None):
    """Create a device with a temperature sensor."""
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    source_entry = MockConfigEntry(domain="test", title="test")
    source_entry.add_to_hass(hass)

    if identifiers is None:
        identifiers = {("test", "device_1")}

    device = device_reg.async_get_or_create(
        config_entry_id=source_entry.entry_id,
        identifiers=identifiers,
        name=name,
    )

    entity_entry = entity_reg.async_get_or_create(
        "sensor",
        "test",
        f"temp_{name.replace(' ', '_').lower()}",
        suggested_object_id=f"{name.replace(' ', '_').lower()}_temperature",
        device_id=device.id,
        original_device_class=SensorDeviceClass.TEMPERATURE,
        original_name="Temperature",
    )

    return device, entity_entry


def _make_role_entry(
    device_id, source_unique_id, source_entity_id, active=True
) -> MockConfigEntry:
    """Create a role config entry with one sensor mapping."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Balcony",
        data={
            CONF_ROLE_NAME: "Balcony",
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
async def test_options_flow_toggle_active(hass: HomeAssistant) -> None:
    """Test toggling the active state via options flow reloads the entry."""
    device, entity_entry = _setup_device_with_sensor(hass)
    hass.states.async_set(entity_entry.entity_id, "22.0")

    entry = _make_role_entry(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Sensor should be active and mirroring
    role_state = hass.states.get("sensor.balcony_sensor_temperature")
    assert role_state is not None
    assert role_state.state == "22.0"

    # Open options flow and deactivate
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_ACTIVE: False},
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()

    # After options update and reload, sensor should be unavailable
    assert entry.data[CONF_ACTIVE] is False
    role_state = hass.states.get("sensor.balcony_sensor_temperature")
    assert role_state is not None
    assert role_state.state == STATE_UNAVAILABLE


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_options_flow_reactivate(hass: HomeAssistant) -> None:
    """Test reactivating an inactive role via options flow."""
    device, entity_entry = _setup_device_with_sensor(hass)
    hass.states.async_set(entity_entry.entity_id, "22.0")

    entry = _make_role_entry(
        device.id, entity_entry.unique_id, entity_entry.entity_id, active=False
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Open options flow and activate
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_ACTIVE: True},
    )
    assert result["type"] == "create_entry"
    assert entry.data[CONF_ACTIVE] is True


def _setup_device_with_multiple_entities(hass):
    """Create a device with temperature, humidity, and switch entities."""
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    source_entry = MockConfigEntry(domain="test", title="test multi")
    source_entry.add_to_hass(hass)

    device = device_reg.async_get_or_create(
        config_entry_id=source_entry.entry_id,
        identifiers={("test", "device_multi")},
        name="Multi Sensor",
    )

    temp = entity_reg.async_get_or_create(
        "sensor", "test", "multi_temp",
        suggested_object_id="multi_sensor_temperature",
        device_id=device.id,
        original_device_class=SensorDeviceClass.TEMPERATURE,
        original_name="Temperature",
    )
    humidity = entity_reg.async_get_or_create(
        "sensor", "test", "multi_humidity",
        suggested_object_id="multi_sensor_humidity",
        device_id=device.id,
        original_device_class=SensorDeviceClass.HUMIDITY,
        original_name="Humidity",
    )
    switch = entity_reg.async_get_or_create(
        "switch", "test", "multi_switch",
        suggested_object_id="multi_sensor_switch",
        device_id=device.id,
        original_name="Switch",
    )

    return device, temp, humidity, switch


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_options_flow_add_entity(hass: HomeAssistant) -> None:
    """Test adding a new entity to an existing role via options flow."""
    device, temp, humidity, switch = _setup_device_with_multiple_entities(hass)
    hass.states.async_set(temp.entity_id, "22.0")
    hass.states.async_set(humidity.entity_id, "55.0")

    # Start with only temperature mapped
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Balcony",
        data={
            CONF_ROLE_NAME: "Balcony",
            CONF_DEVICE_ID: device.id,
            CONF_ACTIVE: True,
            CONF_ENTITY_MAPPINGS: [
                {
                    CONF_SLOT: "sensor_temperature",
                    CONF_SOURCE_UNIQUE_ID: temp.unique_id,
                    CONF_SOURCE_ENTITY_ID: temp.entity_id,
                    CONF_DOMAIN: "sensor",
                    CONF_DEVICE_CLASS: "temperature",
                },
            ],
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Open options and add humidity
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_ACTIVE: True,
            "entities": [temp.entity_id, humidity.entity_id],
        },
    )
    assert result["type"] == "create_entry"

    # Should now have two mappings
    mappings = entry.data[CONF_ENTITY_MAPPINGS]
    assert len(mappings) == 2
    slots = {m[CONF_SLOT] for m in mappings}
    assert "sensor_temperature" in slots
    assert "sensor_humidity" in slots


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_options_flow_remove_entity(hass: HomeAssistant) -> None:
    """Test removing an entity from an existing role via options flow."""
    device, temp, humidity, switch = _setup_device_with_multiple_entities(hass)
    hass.states.async_set(temp.entity_id, "22.0")
    hass.states.async_set(humidity.entity_id, "55.0")

    # Start with both temperature and humidity mapped
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Balcony",
        data={
            CONF_ROLE_NAME: "Balcony",
            CONF_DEVICE_ID: device.id,
            CONF_ACTIVE: True,
            CONF_ENTITY_MAPPINGS: [
                {
                    CONF_SLOT: "sensor_temperature",
                    CONF_SOURCE_UNIQUE_ID: temp.unique_id,
                    CONF_SOURCE_ENTITY_ID: temp.entity_id,
                    CONF_DOMAIN: "sensor",
                    CONF_DEVICE_CLASS: "temperature",
                },
                {
                    CONF_SLOT: "sensor_humidity",
                    CONF_SOURCE_UNIQUE_ID: humidity.unique_id,
                    CONF_SOURCE_ENTITY_ID: humidity.entity_id,
                    CONF_DOMAIN: "sensor",
                    CONF_DEVICE_CLASS: "humidity",
                },
            ],
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Open options and deselect humidity
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_ACTIVE: True,
            "entities": [temp.entity_id],
        },
    )
    assert result["type"] == "create_entry"

    # Should now have only one mapping
    mappings = entry.data[CONF_ENTITY_MAPPINGS]
    assert len(mappings) == 1
    assert mappings[0][CONF_SLOT] == "sensor_temperature"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_options_flow_preserves_existing_slots(hass: HomeAssistant) -> None:
    """Test that existing slot names are preserved when entities are added."""
    device, temp, humidity, switch = _setup_device_with_multiple_entities(hass)
    hass.states.async_set(temp.entity_id, "22.0")

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Balcony",
        data={
            CONF_ROLE_NAME: "Balcony",
            CONF_DEVICE_ID: device.id,
            CONF_ACTIVE: True,
            CONF_ENTITY_MAPPINGS: [
                {
                    CONF_SLOT: "sensor_temperature",
                    CONF_SOURCE_UNIQUE_ID: temp.unique_id,
                    CONF_SOURCE_ENTITY_ID: temp.entity_id,
                    CONF_DOMAIN: "sensor",
                    CONF_DEVICE_CLASS: "temperature",
                },
            ],
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Add switch — temperature slot name should remain unchanged
    hass.states.async_set(switch.entity_id, "off")
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_ACTIVE: True,
            "entities": [temp.entity_id, switch.entity_id],
        },
    )
    assert result["type"] == "create_entry"

    mappings = entry.data[CONF_ENTITY_MAPPINGS]
    temp_mapping = next(m for m in mappings if m[CONF_SOURCE_UNIQUE_ID] == temp.unique_id)
    assert temp_mapping[CONF_SLOT] == "sensor_temperature"  # Unchanged


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_options_flow_rejects_claimed_entities(
    hass: HomeAssistant,
) -> None:
    """Test that options flow rejects entities claimed by another active role."""
    device, temp, humidity, switch = _setup_device_with_multiple_entities(hass)
    hass.states.async_set(temp.entity_id, "22.0")
    hass.states.async_set(humidity.entity_id, "55.0")

    # Role A owns temperature
    entry_a = MockConfigEntry(
        domain=DOMAIN,
        title="Balcony",
        data={
            CONF_ROLE_NAME: "Balcony",
            CONF_DEVICE_ID: device.id,
            CONF_ACTIVE: True,
            CONF_ENTITY_MAPPINGS: [
                {
                    CONF_SLOT: "sensor_temperature",
                    CONF_SOURCE_UNIQUE_ID: temp.unique_id,
                    CONF_SOURCE_ENTITY_ID: temp.entity_id,
                    CONF_DOMAIN: "sensor",
                    CONF_DEVICE_CLASS: "temperature",
                },
            ],
        },
    )
    entry_a.add_to_hass(hass)

    # Role B owns humidity, tries to also claim temperature
    entry_b = MockConfigEntry(
        domain=DOMAIN,
        title="Kitchen",
        data={
            CONF_ROLE_NAME: "Kitchen",
            CONF_DEVICE_ID: device.id,
            CONF_ACTIVE: True,
            CONF_ENTITY_MAPPINGS: [
                {
                    CONF_SLOT: "sensor_humidity",
                    CONF_SOURCE_UNIQUE_ID: humidity.unique_id,
                    CONF_SOURCE_ENTITY_ID: humidity.entity_id,
                    CONF_DOMAIN: "sensor",
                    CONF_DEVICE_CLASS: "humidity",
                },
            ],
        },
    )
    entry_b.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry_a.entry_id)
    await hass.async_block_till_done()

    # entry_b is auto-loaded when the domain loads for entry_a

    # Role B tries to add temperature (claimed by active Role A) via options
    result = await hass.config_entries.options.async_init(entry_b.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_ACTIVE: True,
            "entities": [humidity.entity_id, temp.entity_id],
        },
    )

    # Should show an error, not create the entry
    assert result["type"] == "form"
    assert result["errors"]["base"] == "entity_claimed"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_options_flow_reassign_device(hass: HomeAssistant) -> None:
    """Test reassigning a role to a different physical device."""
    # Create two physical devices
    device_a, temp_a = _setup_device_with_sensor(
        hass, name="Plug A", identifiers={("test", "plug_a")}
    )
    device_b, temp_b = _setup_device_with_sensor(
        hass, name="Plug B", identifiers={("test", "plug_b")}
    )
    hass.states.async_set(temp_a.entity_id, "22.0")
    hass.states.async_set(temp_b.entity_id, "18.0")

    # Role starts on device A
    entry = _make_role_entry(device_a.id, temp_a.unique_id, temp_a.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    role_state = hass.states.get("sensor.balcony_sensor_temperature")
    assert role_state.state == "22.0"

    # Open options and request device change
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_ACTIVE: True, "change_device": True},
    )
    assert result["step_id"] == "select_device"

    # Select device B
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_DEVICE_ID: device_b.id},
    )
    assert result["step_id"] == "select_entities"

    # Select temperature from device B
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"entities": [temp_b.entity_id]},
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()

    # Role should now mirror device B
    assert entry.data[CONF_DEVICE_ID] == device_b.id
    role_state = hass.states.get("sensor.balcony_sensor_temperature")
    assert role_state is not None
    assert role_state.state == "18.0"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_options_flow_shows_current_entities_preselected(
    hass: HomeAssistant,
) -> None:
    """Test that the options form pre-selects currently mapped entities."""
    device, temp, humidity, switch = _setup_device_with_multiple_entities(hass)
    hass.states.async_set(temp.entity_id, "22.0")

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Balcony",
        data={
            CONF_ROLE_NAME: "Balcony",
            CONF_DEVICE_ID: device.id,
            CONF_ACTIVE: True,
            CONF_ENTITY_MAPPINGS: [
                {
                    CONF_SLOT: "sensor_temperature",
                    CONF_SOURCE_UNIQUE_ID: temp.unique_id,
                    CONF_SOURCE_ENTITY_ID: temp.entity_id,
                    CONF_DOMAIN: "sensor",
                    CONF_DEVICE_CLASS: "temperature",
                },
            ],
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"

    # The form should have an "entities" field with the current selection as default
    schema = result["data_schema"]
    schema_dict = dict(schema.schema)
    # Find the entities key (it's a vol.Optional or vol.Required with default)
    entities_key = next(k for k in schema_dict if str(k) == "entities")
    assert entities_key.default() == [temp.entity_id]
