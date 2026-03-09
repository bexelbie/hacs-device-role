# ABOUTME: Sensor platform for the device_role integration.
# ABOUTME: Creates role sensor entities that mirror physical measurement and energy sensors.

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfEnergy
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .accumulator import EnergyAccumulator
from .const import (
    CONF_ACTIVE,
    CONF_DEVICE_CLASS,
    CONF_DOMAIN,
    CONF_ENTITY_MAPPINGS,
    CONF_ROLE_NAME,
    CONF_SLOT,
    CONF_SOURCE_ENTITY_ID,
    DOMAIN,
    ENERGY_INTERNAL_UNIT,
    STORAGE_KEY,
    STORAGE_SAVE_INTERVAL,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

# Measurement device classes that should use SensorStateClass.MEASUREMENT
MEASUREMENT_DEVICE_CLASSES = {
    SensorDeviceClass.TEMPERATURE,
    SensorDeviceClass.HUMIDITY,
    SensorDeviceClass.POWER,
    SensorDeviceClass.VOLTAGE,
    SensorDeviceClass.CURRENT,
    SensorDeviceClass.PRESSURE,
    SensorDeviceClass.ILLUMINANCE,
    SensorDeviceClass.SIGNAL_STRENGTH,
    SensorDeviceClass.PM25,
    SensorDeviceClass.PM10,
    SensorDeviceClass.CO2,
    SensorDeviceClass.CO,
    SensorDeviceClass.NITROGEN_DIOXIDE,
    SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
    SensorDeviceClass.FREQUENCY,
    SensorDeviceClass.SPEED,
    SensorDeviceClass.WIND_SPEED,
}

# Energy device classes handled by the accumulator (Phase 6/7)
ENERGY_DEVICE_CLASSES = {
    SensorDeviceClass.ENERGY,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device role sensor entities from a config entry."""
    role_name = entry.data[CONF_ROLE_NAME]
    active = entry.data.get(CONF_ACTIVE, True)

    # Use the shared store manager from __init__.py
    store_manager = hass.data[DOMAIN].get("store_manager")
    if store_manager is None:
        store_manager = AccumulatorStoreManager(hass)
        await store_manager.async_load()
        hass.data[DOMAIN]["store_manager"] = store_manager

    entities = []
    for mapping in entry.data.get(CONF_ENTITY_MAPPINGS, []):
        if mapping[CONF_DOMAIN] != "sensor":
            continue

        device_class_str = mapping.get(CONF_DEVICE_CLASS)

        if device_class_str and device_class_str == SensorDeviceClass.ENERGY:
            # Energy sensor with accumulator
            acc_key = f"{entry.entry_id}_{mapping[CONF_SLOT]}"
            accumulator = store_manager.get_or_create(acc_key)

            entities.append(
                RoleEnergySensor(
                    entry=entry,
                    role_name=role_name,
                    slot=mapping[CONF_SLOT],
                    source_entity_id=mapping[CONF_SOURCE_ENTITY_ID],
                    active=active,
                    accumulator=accumulator,
                    store_manager=store_manager,
                )
            )
        else:
            entities.append(
                RoleMeasurementSensor(
                    entry=entry,
                    role_name=role_name,
                    slot=mapping[CONF_SLOT],
                    source_entity_id=mapping[CONF_SOURCE_ENTITY_ID],
                    device_class_str=device_class_str,
                    active=active,
                )
            )

    async_add_entities(entities)


class RoleMeasurementSensor(SensorEntity):
    """A role sensor that mirrors a physical measurement sensor."""

    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(
        self,
        entry: ConfigEntry,
        role_name: str,
        slot: str,
        source_entity_id: str,
        device_class_str: str | None,
        active: bool,
    ) -> None:
        """Initialize the role measurement sensor."""
        self._entry = entry
        self._role_name = role_name
        self._slot = slot
        self._source_entity_id = source_entity_id
        self._active = active
        self._unsub_listener = None

        self._attr_unique_id = f"{entry.entry_id}_{slot}"
        self._attr_name = f"{role_name} {slot}".replace("_", " ").title()

        if device_class_str:
            try:
                self._attr_device_class = SensorDeviceClass(device_class_str)
            except ValueError:
                self._attr_device_class = None
        else:
            self._attr_device_class = None

        # Measurement sensors use MEASUREMENT state class
        if self._attr_device_class in MEASUREMENT_DEVICE_CLASSES:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def device_info(self):
        """Return device info to group role entities under a role device."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._role_name,
            "manufacturer": "Device Role",
        }

    @property
    def available(self) -> bool:
        """Return True if the role is active."""
        return self._active

    async def async_added_to_hass(self) -> None:
        """Subscribe to source entity state changes."""
        if not self._active:
            return

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
    """Manages persistent storage for energy accumulators across all roles."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the store manager."""
        self._hass = hass
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.json")
        self._accumulators: dict[str, EnergyAccumulator] = {}
        self._loaded = False

    async def async_load(self) -> None:
        """Load accumulator state from persistent storage."""
        if self._loaded:
            return
        data = await self._store.async_load()
        if data and isinstance(data, dict):
            for key, acc_data in data.get("accumulators", {}).items():
                self._accumulators[key] = EnergyAccumulator.from_dict(acc_data)
        self._loaded = True

    def get_or_create(self, key: str) -> EnergyAccumulator:
        """Get an existing accumulator or create a new one."""
        if key not in self._accumulators:
            self._accumulators[key] = EnergyAccumulator()
        return self._accumulators[key]

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


# Map from source unit strings to the unit parameter for the accumulator
_ENERGY_UNIT_MAP = {
    "kWh": "kWh",
    "Wh": "Wh",
    "MWh": "MWh",
}


class RoleEnergySensor(SensorEntity):
    """A role energy sensor backed by a session accumulator."""

    _attr_should_poll = False
    _attr_has_entity_name = False
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(
        self,
        entry: ConfigEntry,
        role_name: str,
        slot: str,
        source_entity_id: str,
        active: bool,
        accumulator: EnergyAccumulator,
        store_manager: AccumulatorStoreManager,
    ) -> None:
        """Initialize the role energy sensor."""
        self._entry = entry
        self._role_name = role_name
        self._slot = slot
        self._source_entity_id = source_entity_id
        self._active = active
        self._accumulator = accumulator
        self._store_manager = store_manager
        self._unsub_listener = None
        self._session_initialized = False

        self._attr_unique_id = f"{entry.entry_id}_{slot}"
        self._attr_name = f"{role_name} {slot}".replace("_", " ").title()
        self._attr_native_value = accumulator.role_value

    @property
    def device_info(self):
        """Return device info to group role entities under a role device."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._role_name,
            "manufacturer": "Device Role",
        }

    @property
    def available(self) -> bool:
        """Energy sensors stay available even when inactive (frozen value)."""
        return True

    async def async_added_to_hass(self) -> None:
        """Subscribe to source entity state changes and start session."""
        if not self._active:
            return

        # Try to start a session from the current source reading
        self._try_start_session()

        self._unsub_listener = async_track_state_change_event(
            self.hass, [self._source_entity_id], self._handle_source_change
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up listener and save accumulator state."""
        if self._unsub_listener:
            self._unsub_listener()
            self._unsub_listener = None
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

        unit = _ENERGY_UNIT_MAP.get(
            source_state.attributes.get("unit_of_measurement", "kWh"),
            ENERGY_INTERNAL_UNIT,
        )
        self._accumulator.update(reading, unit=unit)
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

        unit = _ENERGY_UNIT_MAP.get(
            source_state.attributes.get("unit_of_measurement", "kWh"),
            ENERGY_INTERNAL_UNIT,
        )
        self._accumulator.start_session(reading, unit=unit)
        self._session_initialized = True
