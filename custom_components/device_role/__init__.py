# ABOUTME: Integration setup and teardown for the device_role integration.
# ABOUTME: Manages platform forwarding and accumulator storage lifecycle.

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant

from .const import DOMAIN, PLATFORMS
from .sensor import AccumulatorStoreManager


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a device role from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create shared store manager on first entry
    if "store_manager" not in hass.data[DOMAIN]:
        store_manager = AccumulatorStoreManager(hass)
        await store_manager.async_load()
        hass.data[DOMAIN]["store_manager"] = store_manager

        # Save accumulators on HA shutdown
        async def _save_on_shutdown(event: Event) -> None:
            await store_manager.async_save_now()

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _save_on_shutdown)

    hass.data[DOMAIN][entry.entry_id] = {}

    # Reload the entry when config data changes (e.g. options flow)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload the entry when configuration changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a device role config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

        # Save accumulator state for the unloaded entry
        store_manager = hass.data[DOMAIN].get("store_manager")
        if store_manager:
            await store_manager.async_save_now()

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up stored data when a config entry is permanently deleted."""
    store_manager = hass.data.get(DOMAIN, {}).get("store_manager")
    if store_manager:
        store_manager.remove_by_entry(entry.entry_id)
        await store_manager.async_save_now()
