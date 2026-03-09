# ABOUTME: Tests for device_role switch entities.
# ABOUTME: Verifies state mirroring, command forwarding, and inactive behavior.

import pytest
from unittest.mock import patch

from homeassistant.const import (
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
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


def _get_role_entity(hass: HomeAssistant, entity_id: str):
    """Find a role entity object by entity_id from the entity platforms."""
    from homeassistant.helpers.entity_platform import async_get_platforms

    for platform in async_get_platforms(hass, DOMAIN):
        for entity in platform.entities.values():
            if entity.entity_id == entity_id:
                return entity
    return None


def _setup_physical_switch(hass: HomeAssistant):
    """Create a physical device with a switch entity."""
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
        "switch",
        "test",
        "switch_1",
        suggested_object_id="orange_heart",
        device_id=device.id,
        original_name="Switch",
    )

    return device, entity_entry


def _make_switch_role(
    device_id: str,
    source_unique_id: str,
    source_entity_id: str,
    active: bool = True,
) -> MockConfigEntry:
    """Create a mock config entry for a role with one switch."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Projector",
        data={
            CONF_ROLE_NAME: "Projector",
            CONF_DEVICE_ID: device_id,
            CONF_ACTIVE: active,
            CONF_ENTITY_MAPPINGS: [
                {
                    CONF_SLOT: "switch",
                    CONF_SOURCE_UNIQUE_ID: source_unique_id,
                    CONF_SOURCE_ENTITY_ID: source_entity_id,
                    CONF_DOMAIN: "switch",
                    CONF_DEVICE_CLASS: None,
                },
            ],
        },
    )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_switch_mirrors_state(hass: HomeAssistant) -> None:
    """Test that a role switch mirrors the physical switch state."""
    device, entity_entry = _setup_physical_switch(hass)
    hass.states.async_set(entity_entry.entity_id, STATE_ON)

    entry = _make_switch_role(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    role_state = hass.states.get("switch.projector_switch")
    assert role_state is not None
    assert role_state.state == STATE_ON


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_switch_tracks_changes(hass: HomeAssistant) -> None:
    """Test that a role switch updates when the physical switch changes."""
    device, entity_entry = _setup_physical_switch(hass)
    hass.states.async_set(entity_entry.entity_id, STATE_OFF)

    entry = _make_switch_role(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("switch.projector_switch").state == STATE_OFF

    hass.states.async_set(entity_entry.entity_id, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("switch.projector_switch").state == STATE_ON


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_switch_forwards_turn_on(hass: HomeAssistant) -> None:
    """Test that turn_on is forwarded to the physical switch."""
    device, entity_entry = _setup_physical_switch(hass)
    hass.states.async_set(entity_entry.entity_id, STATE_OFF)

    entry = _make_switch_role(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Get the role entity directly from the platform
    role_entity = _get_role_entity(hass, "switch.projector_switch")
    assert role_entity is not None

    # Patch the service call method on the HA core class to capture forwarded calls
    calls_made = []
    original = hass.services.async_call.__func__

    async def intercept(self, *args, **kwargs):
        calls_made.append(args)
        return await original(self, *args, **kwargs)

    with patch.object(type(hass.services), "async_call", intercept):
        await role_entity.async_turn_on()

    assert len(calls_made) == 1
    assert calls_made[0][0] == "switch"
    assert calls_made[0][1] == SERVICE_TURN_ON
    assert calls_made[0][2]["entity_id"] == entity_entry.entity_id


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_switch_forwards_turn_off(hass: HomeAssistant) -> None:
    """Test that turn_off is forwarded to the physical switch."""
    device, entity_entry = _setup_physical_switch(hass)
    hass.states.async_set(entity_entry.entity_id, STATE_ON)

    entry = _make_switch_role(device.id, entity_entry.unique_id, entity_entry.entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    role_entity = _get_role_entity(hass, "switch.projector_switch")
    assert role_entity is not None

    calls_made = []
    original = hass.services.async_call.__func__

    async def intercept(self, *args, **kwargs):
        calls_made.append(args)
        return await original(self, *args, **kwargs)

    with patch.object(type(hass.services), "async_call", intercept):
        await role_entity.async_turn_off()

    assert len(calls_made) == 1
    assert calls_made[0][0] == "switch"
    assert calls_made[0][1] == SERVICE_TURN_OFF
    assert calls_made[0][2]["entity_id"] == entity_entry.entity_id


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_switch_inactive_unavailable(hass: HomeAssistant) -> None:
    """Test that an inactive role switch is unavailable."""
    device, entity_entry = _setup_physical_switch(hass)
    hass.states.async_set(entity_entry.entity_id, STATE_ON)

    entry = _make_switch_role(
        device.id, entity_entry.unique_id, entity_entry.entity_id, active=False
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    role_state = hass.states.get("switch.projector_switch")
    assert role_state is not None
    assert role_state.state == STATE_UNAVAILABLE


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_switch_inactive_blocks_commands(hass: HomeAssistant) -> None:
    """Test that an inactive role switch does not forward commands."""
    device, entity_entry = _setup_physical_switch(hass)
    hass.states.async_set(entity_entry.entity_id, STATE_OFF)

    entry = _make_switch_role(
        device.id, entity_entry.unique_id, entity_entry.entity_id, active=False
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    role_entity = _get_role_entity(hass, "switch.projector_switch")
    assert role_entity is not None

    calls_made = []
    original = hass.services.async_call.__func__

    async def intercept(self, *args, **kwargs):
        calls_made.append(args)
        return await original(self, *args, **kwargs)

    with patch.object(type(hass.services), "async_call", intercept):
        await role_entity.async_turn_on()
        await role_entity.async_turn_off()

    # No service calls should have been forwarded
    assert len(calls_made) == 0
