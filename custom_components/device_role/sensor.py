# ABOUTME: Sensor platform for the device_role integration.
# ABOUTME: Creates role sensor entities that mirror measurement and accumulating sensors.

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .accumulator import SessionAccumulator
from .const import (
    CONF_ACTIVE,
    CONF_DEVICE_CLASS,
    CONF_DOMAIN,
    CONF_ENTITY_MAPPINGS,
    CONF_ROLE_NAME,
    CONF_SLOT,
    CONF_SOURCE_ENTITY_ID,
    CONF_STATE_CLASS,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_SAVE_INTERVAL,
    STORAGE_VERSION,
)
from .helpers import build_role_device_info, resolve_source_entity_id, resolve_via_device

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device role sensor entities from a config entry."""
    role_name = entry.data[CONF_ROLE_NAME]
    active = entry.data.get(CONF_ACTIVE, True)
    via = resolve_via_device(hass, entry.data.get("device_id", ""))

    # Use the shared store manager from __init__.py
    store_manager = hass.data[DOMAIN].get("store_manager")
    if store_manager is None:
        store_manager = AccumulatorStoreManager(hass)
        await store_manager.async_load()
        hass.data[DOMAIN]["store_manager"] = store_manager

    entity_reg = er.async_get(hass)

    entities = []
    for mapping in entry.data.get(CONF_ENTITY_MAPPINGS, []):
        if mapping[CONF_DOMAIN] != "sensor":
            continue

        device_class_str = mapping.get(CONF_DEVICE_CLASS)
        source_entity_id = resolve_source_entity_id(hass, mapping)

        # Use the source entity's original name for display
        source_reg = entity_reg.async_get(source_entity_id)
        source_name = source_reg.original_name if source_reg else None

        # Detect state_class from entity registry (persisted across reboots),
        # config mapping, or live state. This avoids a race where the source
        # entity's state isn't available yet at setup time.
        source_state_class = None
        if source_reg and source_reg.capabilities:
            source_state_class = source_reg.capabilities.get("state_class")
        if source_state_class is None:
            source_state_class = mapping.get(CONF_STATE_CLASS)
        source_uom = ""
        source_state = hass.states.get(source_entity_id)
        if source_state is not None:
            if source_state_class is None:
                source_state_class = source_state.attributes.get("state_class")
            source_uom = source_state.attributes.get("unit_of_measurement", "")

        use_accumulator = source_state_class == "total_increasing"

        if use_accumulator:
            acc_key = f"{entry.entry_id}_{mapping[CONF_SLOT]}"
            accumulator = store_manager.get_or_create(acc_key)

            entities.append(
                RoleAccumulatingSensor(
                    entry=entry,
                    role_name=role_name,
                    slot=mapping[CONF_SLOT],
                    source_entity_id=source_entity_id,
                    source_name=source_name,
                    device_class_str=device_class_str,
                    source_uom=source_uom,
                    active=active,
                    accumulator=accumulator,
                    store_manager=store_manager,
                    via_device_id=via,
                )
            )
        else:
            entities.append(
                RoleMeasurementSensor(
                    entry=entry,
                    role_name=role_name,
                    slot=mapping[CONF_SLOT],
                    source_entity_id=source_entity_id,
                    source_name=source_name,
                    device_class_str=device_class_str,
                    state_class_str=source_state_class,
                    active=active,
                    via_device_id=via,
                )
            )

    async_add_entities(entities)


class RoleMeasurementSensor(SensorEntity):
    """A role sensor that mirrors a physical measurement sensor."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        role_name: str,
        slot: str,
        source_entity_id: str,
        device_class_str: str | None,
        active: bool,
        source_name: str | None = None,
        state_class_str: str | None = None,
        via_device_id: tuple | None = None,
    ) -> None:
        """Initialize the role measurement sensor."""
        self._entry = entry
        self._role_name = role_name
        self._slot = slot
        self._source_entity_id = source_entity_id
        self._active = active
        self._unsub_listener = None
        self._device_info = build_role_device_info(entry.entry_id, role_name, via_device_id)

        self._attr_unique_id = f"{entry.entry_id}_{slot}"
        self._attr_name = source_name or slot.replace("_", " ").title()

        if device_class_str:
            try:
                self._attr_device_class = SensorDeviceClass(device_class_str)
            except ValueError:
                self._attr_device_class = None
        else:
            self._attr_device_class = None

        if state_class_str:
            try:
                self._attr_state_class = SensorStateClass(state_class_str)
            except ValueError:
                pass

    @property
    def device_info(self):
        """Return device info to group role entities under a role device."""
        return self._device_info

    @property
    def available(self) -> bool:
        """Return True if the role is active."""
        return self._active

    async def async_added_to_hass(self) -> None:
        """Subscribe to source entity state changes."""
        if not self._active:
            return

        # Copy display precision from the source entity
        entity_reg = er.async_get(self.hass)
        source_entry = entity_reg.async_get(self._source_entity_id)
        if source_entry:
            sensor_opts = source_entry.options.get("sensor", {})
            precision = sensor_opts.get(
                "display_precision",
                sensor_opts.get("suggested_display_precision"),
            )
            if precision is not None:
                self._attr_suggested_display_precision = precision

        # Set initial value from current source state
        self._update_from_source()

        self._unsub_listener = async_track_state_change_event(
            self.hass, [self._source_entity_id], self._handle_source_change
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up the state change listener."""
        if self._unsub_listener:
            self._unsub_listener()
            self._unsub_listener = None

    @callback
    def _handle_source_change(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle source entity state changes."""
        self._update_from_source()
        self.async_write_ha_state()

    @callback
    def _update_from_source(self) -> None:
        """Update role sensor value from the source entity's current state."""
        source_state = self.hass.states.get(self._source_entity_id)
        if source_state is None or source_state.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            self._attr_native_value = None
            return

        try:
            self._attr_native_value = float(source_state.state)
        except (ValueError, TypeError):
            self._attr_native_value = None

        # Copy unit of measurement from source
        if uom := source_state.attributes.get("unit_of_measurement"):
            self._attr_native_unit_of_measurement = uom


class AccumulatorStoreManager:
    """Manages persistent storage for accumulators across all roles."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the store manager."""
        self._hass = hass
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.json")
        self._accumulators: dict[str, SessionAccumulator] = {}
        self._loaded = False

    async def async_load(self) -> None:
        """Load accumulator state from persistent storage."""
        if self._loaded:
            return
        data = await self._store.async_load()
        if data and isinstance(data, dict):
            for key, acc_data in data.get("accumulators", {}).items():
                self._accumulators[key] = SessionAccumulator.from_dict(acc_data)
        self._loaded = True

    def get_or_create(self, key: str) -> SessionAccumulator:
        """Get an existing accumulator or create a new one."""
        if key not in self._accumulators:
            self._accumulators[key] = SessionAccumulator()
        return self._accumulators[key]

    def get_by_entry_slot(
        self, entry_id: str, slot: str
    ) -> SessionAccumulator | None:
        """Get an accumulator by entry ID and slot name."""
        return self._accumulators.get(f"{entry_id}_{slot}")

    def commit_entry_slots(self, entry_id: str, slots: list[str]) -> None:
        """Commit all active sessions for the provided entry slots."""
        for slot in slots:
            accumulator = self.get_by_entry_slot(entry_id, slot)
            if accumulator is not None:
                accumulator.commit_session()

    def remove_by_entry(self, entry_id: str) -> None:
        """Remove all accumulators belonging to a config entry."""
        prefix = f"{entry_id}_"
        keys = [k for k in self._accumulators if k.startswith(prefix)]
        for key in keys:
            del self._accumulators[key]

    def schedule_save(self) -> None:
        """Schedule a delayed save of all accumulator state."""
        self._store.async_delay_save(self._data_to_save, STORAGE_SAVE_INTERVAL)

    async def async_save_now(self) -> None:
        """Immediately save all accumulator state."""
        await self._store.async_save(self._data_to_save())

    def _data_to_save(self) -> dict:
        """Build the data structure for persistent storage."""
        return {
            "accumulators": {
                key: acc.to_dict()
                for key, acc in self._accumulators.items()
            }
        }

class RoleAccumulatingSensor(SensorEntity):
    """A role sensor backed by a session accumulator for total_increasing sources."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 3

    def __init__(
        self,
        entry: ConfigEntry,
        role_name: str,
        slot: str,
        source_entity_id: str,
        active: bool,
        accumulator: SessionAccumulator,
        store_manager: AccumulatorStoreManager,
        device_class_str: str | None = None,
        source_uom: str | None = None,
        source_name: str | None = None,
        via_device_id: tuple | None = None,
    ) -> None:
        """Initialize the role accumulating sensor."""
        self._entry = entry
        self._role_name = role_name
        self._slot = slot
        self._source_entity_id = source_entity_id
        self._active = active
        self._accumulator = accumulator
        self._store_manager = store_manager
        self._unsub_listener = None
        self._session_initialized = False
        self._device_info = build_role_device_info(entry.entry_id, role_name, via_device_id)

        self._attr_unique_id = f"{entry.entry_id}_{slot}"
        self._attr_name = source_name or slot.replace("_", " ").title()
        self._attr_native_value = accumulator.role_value

        # Copy device_class and unit from source
        if device_class_str:
            try:
                self._attr_device_class = SensorDeviceClass(device_class_str)
            except ValueError:
                pass
        if source_uom:
            self._attr_native_unit_of_measurement = source_uom

    @property
    def device_info(self):
        """Return device info to group role entities under a role device."""
        return self._device_info

    @property
    def available(self) -> bool:
        """Accumulating sensors stay available even when inactive (frozen value)."""
        return True

    async def async_added_to_hass(self) -> None:
        """Subscribe to source entity state changes and resume or start session."""
        if not self._active:
            return

        if self._accumulator.session_active:
            self._session_initialized = True
            self._update_from_current_source()
        else:
            self._try_start_session()

        self._unsub_listener = async_track_state_change_event(
            self.hass, [self._source_entity_id], self._handle_source_change
        )

    async def async_will_remove_from_hass(self) -> None:
        """Save accumulator state on removal; commit when deactivated or mapping removed."""
        if self._unsub_listener:
            self._unsub_listener()
            self._unsub_listener = None
        slot_still_mapped = any(
            m.get(CONF_SLOT) == self._slot
            for m in self._entry.data.get(CONF_ENTITY_MAPPINGS, [])
        )
        if not self._entry.data.get(CONF_ACTIVE, True) or not slot_still_mapped:
            self._accumulator.commit_session()
        self._store_manager.schedule_save()

    @callback
    def _handle_source_change(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle source entity state changes."""
        if not self._session_initialized:
            self._try_start_session()
            if self._session_initialized:
                self._attr_native_value = self._accumulator.role_value
                self.async_write_ha_state()
            return

        source_state = self.hass.states.get(self._source_entity_id)
        if source_state is None or source_state.state in (
            STATE_UNAVAILABLE, STATE_UNKNOWN,
        ):
            return

        try:
            reading = float(source_state.state)
        except (ValueError, TypeError):
            return

        # Reject updates where the source unit changed mid-session
        current_unit = source_state.attributes.get("unit_of_measurement", "")
        if self._accumulator.unit and current_unit != self._accumulator.unit:
            return

        self._accumulator.update(reading)
        self._attr_native_value = self._accumulator.role_value
        self._store_manager.schedule_save()
        self.async_write_ha_state()

    @callback
    def _try_start_session(self) -> None:
        """Try to start an accumulator session from the current source state."""
        source_state = self.hass.states.get(self._source_entity_id)
        if source_state is None or source_state.state in (
            STATE_UNAVAILABLE, STATE_UNKNOWN,
        ):
            return

        try:
            reading = float(source_state.state)
        except (ValueError, TypeError):
            return

        unit = source_state.attributes.get("unit_of_measurement", "")
        if not self._accumulator.start_session(reading, unit=unit):
            return
        self._session_initialized = True
        # Set unit now in case it wasn't available at init time
        if unit and not self._attr_native_unit_of_measurement:
            self._attr_native_unit_of_measurement = unit

    @callback
    def _update_from_current_source(self) -> None:
        """Feed the current source reading to the accumulator."""
        source_state = self.hass.states.get(self._source_entity_id)
        if source_state is None or source_state.state in (
            STATE_UNAVAILABLE, STATE_UNKNOWN,
        ):
            return

        try:
            reading = float(source_state.state)
        except (ValueError, TypeError):
            return

        # Reject updates where the source unit changed mid-session
        current_unit = source_state.attributes.get("unit_of_measurement", "")
        if self._accumulator.unit and current_unit != self._accumulator.unit:
            return

        self._accumulator.update(reading)
        self._attr_native_value = self._accumulator.role_value
