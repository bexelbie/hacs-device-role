# ABOUTME: Tests for the device_role config flow.
# ABOUTME: Covers role creation steps: name, device selection, entity selection, and validation.

import pytest
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_device_registry,
    mock_registry,
)

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


def _create_mock_device(
    hass: HomeAssistant,
    device_reg: dr.DeviceRegistry,
    name: str = "Test Device",
    identifiers: set | None = None,
) -> dr.DeviceEntry:
    """Create a mock device in the device registry."""
    if identifiers is None:
        identifiers = {("test", "device_1")}
    # Devices must be linked to a valid config entry
    source_entry = MockConfigEntry(domain="test", title="test source")
    source_entry.add_to_hass(hass)
    return device_reg.async_get_or_create(
        config_entry_id=source_entry.entry_id,
        identifiers=identifiers,
        name=name,
        manufacturer="Test Manufacturer",
        model="Test Model",
    )


def _create_mock_entity(
    entity_reg: er.EntityRegistry,
    device_id: str,
    domain: str = "sensor",
    unique_id: str = "test_unique_1",
    entity_id: str | None = None,
    device_class: str | None = None,
    original_name: str | None = None,
) -> er.RegistryEntry:
    """Create a mock entity in the entity registry."""
    if entity_id is None:
        entity_id = f"{domain}.test_{unique_id}"
    entry = entity_reg.async_get_or_create(
        domain,
        "test",
        unique_id,
        suggested_object_id=entity_id.split(".", 1)[1] if "." in entity_id else unique_id,
        device_id=device_id,
        original_device_class=device_class,
        original_name=original_name,
    )
    return entry


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_user_step_shows_name_form(hass: HomeAssistant) -> None:
    """Test that the first step shows a form for the role name."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_user_step_duplicate_name(hass: HomeAssistant) -> None:
    """Test that a duplicate role name is rejected."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        title="Projector",
        data={CONF_ROLE_NAME: "Projector", CONF_DEVICE_ID: "d1", CONF_ACTIVE: True, CONF_ENTITY_MAPPINGS: []},
    )
    existing.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ROLE_NAME: "Projector"},
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "name_exists"}


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_device_step_shows_devices(hass: HomeAssistant) -> None:
    """Test that the device selection step lists available devices."""
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)
    device = _create_mock_device(hass, device_reg, name="Smart Plug Orange Heart")
    _create_mock_entity(
        entity_reg, device.id,
        domain="sensor", unique_id="temp_1", device_class="temperature",
        original_name="Temperature",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ROLE_NAME: "Projector"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "select_device"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_entity_step_shows_entities(hass: HomeAssistant) -> None:
    """Test that the entity selection step lists entities from the chosen device."""
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    device = _create_mock_device(hass, device_reg, name="Smart Plug Orange Heart")
    _create_mock_entity(
        entity_reg, device.id,
        domain="sensor", unique_id="temp_1", device_class="temperature",
        original_name="Temperature",
    )
    _create_mock_entity(
        entity_reg, device.id,
        domain="switch", unique_id="switch_1",
        original_name="Switch",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ROLE_NAME: "Projector"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_DEVICE_ID: device.id},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "select_entities"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_full_flow_creates_entry(hass: HomeAssistant) -> None:
    """Test the complete flow creates a config entry with correct data."""
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    device = _create_mock_device(hass, device_reg, name="Smart Plug Orange Heart")
    temp_entity = _create_mock_entity(
        entity_reg, device.id,
        domain="sensor", unique_id="temp_1", device_class="temperature",
        original_name="Temperature",
    )
    switch_entity = _create_mock_entity(
        entity_reg, device.id,
        domain="switch", unique_id="switch_1",
        original_name="Switch",
    )

    # Step 1: Name
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    # Step 2: Device
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ROLE_NAME: "Projector"},
    )
    # Step 3: Entities
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_DEVICE_ID: device.id},
    )
    # Create entry
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"entities": [temp_entity.entity_id, switch_entity.entity_id]},
    )

    assert result["type"] == "create_entry"
    assert result["title"] == "Projector"

    data = result["data"]
    assert data[CONF_ROLE_NAME] == "Projector"
    assert data[CONF_DEVICE_ID] == device.id
    assert data[CONF_ACTIVE] is True
    assert len(data[CONF_ENTITY_MAPPINGS]) == 2

    # Verify mappings
    slots = {m[CONF_SLOT] for m in data[CONF_ENTITY_MAPPINGS]}
    assert "sensor_temperature" in slots
    assert "switch" in slots


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_entity_claimed_by_another_role(hass: HomeAssistant) -> None:
    """Test that an entity already claimed by an active role is rejected."""
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    device = _create_mock_device(hass, device_reg, name="Smart Plug Orange Heart")
    temp_entity = _create_mock_entity(
        entity_reg, device.id,
        domain="sensor", unique_id="temp_1", device_class="temperature",
        original_name="Temperature",
    )

    # Existing role already claims this entity
    existing = MockConfigEntry(
        domain=DOMAIN,
        title="Balcony",
        data={
            CONF_ROLE_NAME: "Balcony",
            CONF_DEVICE_ID: device.id,
            CONF_ACTIVE: True,
            CONF_ENTITY_MAPPINGS: [
                {
                    CONF_SLOT: "sensor_temperature",
                    CONF_SOURCE_UNIQUE_ID: "temp_1",
                    CONF_SOURCE_ENTITY_ID: temp_entity.entity_id,
                    CONF_DOMAIN: "sensor",
                    CONF_DEVICE_CLASS: "temperature",
                },
            ],
        },
    )
    existing.add_to_hass(hass)

    # Try to create another role claiming the same entity
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ROLE_NAME: "Projector"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_DEVICE_ID: device.id},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"entities": [temp_entity.entity_id]},
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "entity_claimed"}


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_no_devices_aborts(hass: HomeAssistant) -> None:
    """Test that the flow shows an error when no devices exist."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ROLE_NAME: "Projector"},
    )
    # With no devices, the flow should abort
    assert result["type"] == "abort"
    assert result["reason"] == "no_devices"
