# ABOUTME: Tests for the shared helpers module.
# ABOUTME: Covers resolve_via_device, build_role_device_info, and resolve_source_entity_id.

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.device_role.helpers import (
    build_role_device_info,
    resolve_via_device,
)

DOMAIN = "device_role"


@pytest.fixture
def device_reg(hass: HomeAssistant) -> dr.DeviceRegistry:
    """Return the device registry."""
    return dr.async_get(hass)


def _create_device(
    hass: HomeAssistant,
    device_reg: dr.DeviceRegistry,
    identifiers: set[tuple[str, str]],
    **kwargs,
) -> dr.DeviceEntry:
    """Create a device backed by a mock config entry."""
    entry = MockConfigEntry(domain="test", title="test")
    entry.add_to_hass(hass)
    return device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers=identifiers,
        **kwargs,
    )


async def test_resolve_via_device_returns_identifier(
    hass: HomeAssistant, device_reg: dr.DeviceRegistry,
) -> None:
    """resolve_via_device returns the first identifier tuple of the device."""
    device = _create_device(
        hass, device_reg,
        identifiers={("zigbee", "0x1234")},
        name="Zigbee Plug",
    )
    result = resolve_via_device(hass, device.id)
    assert result == ("zigbee", "0x1234")


async def test_resolve_via_device_missing_device(hass: HomeAssistant) -> None:
    """resolve_via_device returns None when device_id doesn't exist."""
    result = resolve_via_device(hass, "nonexistent_device_id")
    assert result is None


async def test_resolve_via_device_empty_string(hass: HomeAssistant) -> None:
    """resolve_via_device returns None for empty device_id."""
    result = resolve_via_device(hass, "")
    assert result is None


async def test_resolve_via_device_no_identifiers(
    hass: HomeAssistant, device_reg: dr.DeviceRegistry,
) -> None:
    """resolve_via_device returns None when device has no identifiers."""
    device = _create_device(
        hass, device_reg,
        identifiers=set(),
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")},
        name="MAC-only Device",
    )
    result = resolve_via_device(hass, device.id)
    assert result is None


def test_build_role_device_info_without_via() -> None:
    """build_role_device_info without via_device omits the key."""
    info = build_role_device_info("entry_123", "Projector")
    assert info == {
        "identifiers": {(DOMAIN, "entry_123")},
        "name": "Projector",
        "manufacturer": "Device Role",
    }
    assert "via_device" not in info


def test_build_role_device_info_with_via() -> None:
    """build_role_device_info with via_device includes the link."""
    info = build_role_device_info(
        "entry_123", "Projector", via_device_id=("zigbee", "0x1234"),
    )
    assert info["via_device"] == ("zigbee", "0x1234")
    assert info["identifiers"] == {(DOMAIN, "entry_123")}
    assert info["name"] == "Projector"


def test_build_role_device_info_with_none_via() -> None:
    """build_role_device_info with explicit None omits via_device."""
    info = build_role_device_info("entry_123", "Projector", via_device_id=None)
    assert "via_device" not in info
