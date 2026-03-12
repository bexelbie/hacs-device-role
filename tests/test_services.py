# ABOUTME: Tests for the device_role service API.
# ABOUTME: Covers role discovery, lifecycle updates, reassignment, and deletion.

from types import MappingProxyType

import pytest

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry, SOURCE_USER
from homeassistant.const import STATE_UNAVAILABLE, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

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


def _create_source_device(
    hass: HomeAssistant,
    *,
    name: str,
    identifiers: set[tuple[str, str]],
) -> dr.DeviceEntry:
    """Create a physical device backed by a mock source config entry."""
    source_entry = MockConfigEntry(domain="test", title=f"{name} source")
    source_entry.add_to_hass(hass)

    device_reg = dr.async_get(hass)
    return device_reg.async_get_or_create(
        config_entry_id=source_entry.entry_id,
        identifiers=identifiers,
        name=name,
    )


def _create_source_entity(
    hass: HomeAssistant,
    *,
    device_id: str,
    domain: str,
    unique_id: str,
    object_id: str,
    original_name: str,
    device_class: str | SensorDeviceClass | None = None,
    unit_of_measurement: str | None = None,
) -> er.RegistryEntry:
    """Create an entity on a physical device."""
    entity_reg = er.async_get(hass)
    return entity_reg.async_get_or_create(
        domain,
        "test",
        unique_id,
        suggested_object_id=object_id,
        device_id=device_id,
        original_device_class=device_class,
        original_name=original_name,
        unit_of_measurement=unit_of_measurement,
    )


def _make_role_entry(
    *,
    role_name: str,
    device_id: str,
    mappings: list[dict],
    active: bool = True,
) -> MockConfigEntry:
    """Create a role config entry with the provided mappings."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=role_name,
        data={
            CONF_ROLE_NAME: role_name,
            CONF_DEVICE_ID: device_id,
            CONF_ACTIVE: active,
            CONF_ENTITY_MAPPINGS: mappings,
        },
    )


def _make_mapping(
    *,
    slot: str,
    source_unique_id: str,
    source_entity_id: str,
    domain: str,
    device_class: str | None = None,
    state_class: str | None = None,
) -> dict:
    """Create an entity mapping for a role."""
    mapping = {
        CONF_SLOT: slot,
        CONF_SOURCE_UNIQUE_ID: source_unique_id,
        CONF_SOURCE_ENTITY_ID: source_entity_id,
        CONF_DOMAIN: domain,
        CONF_DEVICE_CLASS: device_class,
    }
    if state_class is not None:
        mapping["state_class"] = state_class
    return mapping


async def _create_runtime_role_entry(
    hass: HomeAssistant,
    *,
    role_name: str,
    device_id: str,
    mappings: list[dict],
    active: bool = True,
) -> ConfigEntry:
    """Add a live config entry through the runtime config entries API."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title=role_name,
        data={
            CONF_ROLE_NAME: role_name,
            CONF_DEVICE_ID: device_id,
            CONF_ACTIVE: active,
            CONF_ENTITY_MAPPINGS: mappings,
        },
        options={},
        pref_disable_new_entities=False,
        pref_disable_polling=False,
        source=SOURCE_USER,
        unique_id=None,
        discovery_keys=MappingProxyType({}),
        subentries_data=(),
    )
    await hass.config_entries.async_add(entry)
    await hass.async_block_till_done()
    return entry


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_list_roles_returns_canonical_role_objects(
    hass: HomeAssistant,
) -> None:
    """The list_roles service returns the expected canonical shape."""
    device = _create_source_device(
        hass,
        name="Balcony Sensor",
        identifiers={("test", "balcony_sensor")},
    )
    temp = _create_source_entity(
        hass,
        device_id=device.id,
        domain="sensor",
        unique_id="temp_1",
        object_id="balcony_sensor_temperature",
        original_name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
    )
    switch = _create_source_entity(
        hass,
        device_id=device.id,
        domain="switch",
        unique_id="switch_1",
        object_id="balcony_sensor_switch",
        original_name="Switch",
    )
    hass.states.async_set(temp.entity_id, "22.0")
    hass.states.async_set(switch.entity_id, "off")

    entry = _make_role_entry(
        role_name="Balcony",
        device_id=device.id,
        mappings=[
            _make_mapping(
                slot="sensor_temperature",
                source_unique_id=temp.unique_id,
                source_entity_id=temp.entity_id,
                domain="sensor",
                device_class="temperature",
            ),
            _make_mapping(
                slot="switch",
                source_unique_id=switch.unique_id,
                source_entity_id=switch.entity_id,
                domain="switch",
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    response = await hass.services.async_call(
        DOMAIN,
        "list_roles",
        blocking=True,
        return_response=True,
    )

    assert list(response) == ["roles"]
    assert len(response["roles"]) == 1
    role = response["roles"][0]
    assert role["config_entry_id"] == entry.entry_id
    assert role["name"] == "Balcony"
    assert role["active"] is True
    assert role["device_id"] == device.id
    assert role["mappings"] == [
        {
            "slot": "sensor_temperature",
            "role_entity_id": "sensor.balcony_temperature",
            "source_entity_id": temp.entity_id,
            "source_unique_id": temp.unique_id,
            "domain": "sensor",
            "device_class": "temperature",
        },
        {
            "slot": "switch",
            "role_entity_id": "switch.balcony_switch",
            "source_entity_id": switch.entity_id,
            "source_unique_id": switch.unique_id,
            "domain": "switch",
            "device_class": None,
        },
    ]


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_create_role_service_creates_active_role(
    hass: HomeAssistant,
) -> None:
    """The create_role service creates an active config entry and entities."""
    device = _create_source_device(
        hass,
        name="Office Sensor",
        identifiers={("test", "office_sensor")},
    )
    temp = _create_source_entity(
        hass,
        device_id=device.id,
        domain="sensor",
        unique_id="office_temp_1",
        object_id="office_sensor_temperature",
        original_name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
    )
    humidity = _create_source_entity(
        hass,
        device_id=device.id,
        domain="sensor",
        unique_id="office_humidity_1",
        object_id="office_sensor_humidity",
        original_name="Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
    )
    hass.states.async_set(temp.entity_id, "21.5")
    hass.states.async_set(humidity.entity_id, "55.0")
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    response = await hass.services.async_call(
        DOMAIN,
        "create_role",
        {
            "name": "Office",
            "device_id": device.id,
            "entity_ids": [temp.entity_id, humidity.entity_id],
        },
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()

    created = next(
        entry for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.entry_id == response["role"]["config_entry_id"]
    )
    assert created.data[CONF_ROLE_NAME] == "Office"
    assert created.data[CONF_ACTIVE] is True
    assert hass.states.get("sensor.office_temperature").state == "21.5"
    assert hass.states.get("sensor.office_humidity").state == "55.0"
    assert response["role"]["name"] == "Office"
    assert response["role"]["device_id"] == device.id
    assert {mapping["role_entity_id"] for mapping in response["role"]["mappings"]} == {
        "sensor.office_temperature",
        "sensor.office_humidity",
    }


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_set_active_service_toggles_role_state(
    hass: HomeAssistant,
) -> None:
    """The set_active service updates the config entry and reloads the role."""
    device = _create_source_device(
        hass,
        name="Balcony Sensor",
        identifiers={("test", "balcony_active_sensor")},
    )
    temp = _create_source_entity(
        hass,
        device_id=device.id,
        domain="sensor",
        unique_id="balcony_temp_active_1",
        object_id="balcony_active_temperature",
        original_name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
    )
    hass.states.async_set(temp.entity_id, "18.0")

    entry = _make_role_entry(
        role_name="Balcony",
        device_id=device.id,
        mappings=[
            _make_mapping(
                slot="sensor_temperature",
                source_unique_id=temp.unique_id,
                source_entity_id=temp.entity_id,
                domain="sensor",
                device_class="temperature",
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    response = await hass.services.async_call(
        DOMAIN,
        "set_active",
        {"config_entry_id": entry.entry_id, "active": False},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()

    assert entry.data[CONF_ACTIVE] is False
    assert hass.states.get("sensor.balcony_temperature").state == STATE_UNAVAILABLE
    assert response["role"]["active"] is False


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_configure_entities_service_preserves_existing_role_entities(
    hass: HomeAssistant,
) -> None:
    """configure_entities keeps retained logical entities stable and adds new ones."""
    device = _create_source_device(
        hass,
        name="Garden Sensor",
        identifiers={("test", "garden_sensor")},
    )
    temp = _create_source_entity(
        hass,
        device_id=device.id,
        domain="sensor",
        unique_id="garden_temp_1",
        object_id="garden_sensor_temperature",
        original_name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
    )
    humidity = _create_source_entity(
        hass,
        device_id=device.id,
        domain="sensor",
        unique_id="garden_humidity_1",
        object_id="garden_sensor_humidity",
        original_name="Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
    )
    hass.states.async_set(temp.entity_id, "20.0")
    hass.states.async_set(humidity.entity_id, "44.0")

    entry = _make_role_entry(
        role_name="Garden",
        device_id=device.id,
        mappings=[
            _make_mapping(
                slot="sensor_temperature",
                source_unique_id=temp.unique_id,
                source_entity_id=temp.entity_id,
                domain="sensor",
                device_class="temperature",
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    response = await hass.services.async_call(
        DOMAIN,
        "configure_entities",
        {
            "config_entry_id": entry.entry_id,
            "entity_ids": [temp.entity_id, humidity.entity_id],
        },
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()

    assert entry.data[CONF_DEVICE_ID] == device.id
    assert len(entry.data[CONF_ENTITY_MAPPINGS]) == 2
    assert hass.states.get("sensor.garden_temperature").state == "20.0"
    assert hass.states.get("sensor.garden_humidity").state == "44.0"
    assert {
        mapping["role_entity_id"] for mapping in response["role"]["mappings"]
    } == {"sensor.garden_temperature", "sensor.garden_humidity"}
    temp_mapping = next(
        mapping for mapping in response["role"]["mappings"]
        if mapping["source_entity_id"] == temp.entity_id
    )
    assert temp_mapping["slot"] == "sensor_temperature"
    assert temp_mapping["role_entity_id"] == "sensor.garden_temperature"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_reassign_service_preserves_accumulator_history(
    hass: HomeAssistant,
) -> None:
    """reassign preserves logical identity and accumulated totals."""
    device_a = _create_source_device(
        hass,
        name="Plug A",
        identifiers={("test", "plug_a")},
    )
    energy_a = _create_source_entity(
        hass,
        device_id=device_a.id,
        domain="sensor",
        unique_id="plug_a_energy",
        object_id="plug_a_energy",
        original_name="Energy",
        device_class=SensorDeviceClass.ENERGY,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )
    hass.states.async_set(
        energy_a.entity_id,
        "100.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )

    entry = await _create_runtime_role_entry(
        hass,
        role_name="Projector",
        device_id=device_a.id,
        mappings=[
            _make_mapping(
                slot="sensor_energy",
                source_unique_id=energy_a.unique_id,
                source_entity_id=energy_a.entity_id,
                domain="sensor",
                device_class="energy",
                state_class="total_increasing",
            )
        ],
    )
    hass.states.async_set(
        energy_a.entity_id,
        "110.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )
    await hass.async_block_till_done()

    device_b = _create_source_device(
        hass,
        name="Plug B",
        identifiers={("test", "plug_b")},
    )
    energy_b = _create_source_entity(
        hass,
        device_id=device_b.id,
        domain="sensor",
        unique_id="plug_b_energy",
        object_id="plug_b_energy",
        original_name="Energy",
        device_class=SensorDeviceClass.ENERGY,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )
    hass.states.async_set(
        energy_b.entity_id,
        "500.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )

    response = await hass.services.async_call(
        DOMAIN,
        "reassign",
        {
            "config_entry_id": entry.entry_id,
            "device_id": device_b.id,
            "assignments": [
                {
                    "role_entity_id": "sensor.projector_energy",
                    "entity_id": energy_b.entity_id,
                }
            ],
        },
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()

    assert entry.data[CONF_DEVICE_ID] == device_b.id
    assert response["role"]["mappings"] == [
        {
            "slot": "sensor_energy",
            "role_entity_id": "sensor.projector_energy",
            "source_entity_id": energy_b.entity_id,
            "source_unique_id": energy_b.unique_id,
            "domain": "sensor",
            "device_class": "energy",
        }
    ]

    role_state = hass.states.get("sensor.projector_energy")
    assert role_state is not None
    assert float(role_state.state) == 10.0

    hass.states.async_set(
        energy_b.entity_id,
        "503.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )
    await hass.async_block_till_done()

    assert float(hass.states.get("sensor.projector_energy").state) == 13.0


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_delete_role_service_removes_entry_and_accumulator_state(
    hass: HomeAssistant,
) -> None:
    """delete_role removes the entry, its entities, and stored accumulator data."""
    device = _create_source_device(
        hass,
        name="Projector Plug",
        identifiers={("test", "projector_plug")},
    )
    energy = _create_source_entity(
        hass,
        device_id=device.id,
        domain="sensor",
        unique_id="projector_energy",
        object_id="projector_plug_energy",
        original_name="Energy",
        device_class=SensorDeviceClass.ENERGY,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )
    hass.states.async_set(
        energy.entity_id,
        "100.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )

    entry = await _create_runtime_role_entry(
        hass,
        role_name="Projector",
        device_id=device.id,
        mappings=[
            _make_mapping(
                slot="sensor_energy",
                source_unique_id=energy.unique_id,
                source_entity_id=energy.entity_id,
                domain="sensor",
                device_class="energy",
                state_class="total_increasing",
            )
        ],
    )
    hass.states.async_set(
        energy.entity_id,
        "110.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )
    await hass.async_block_till_done()

    entity_reg = er.async_get(hass)
    role_entity_id = entity_reg.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_sensor_energy"
    )

    response = await hass.services.async_call(
        DOMAIN,
        "delete_role",
        {"config_entry_id": entry.entry_id},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()

    store_manager = hass.data[DOMAIN]["store_manager"]
    assert response == {
        "config_entry_id": entry.entry_id,
        "name": "Projector",
    }
    assert hass.config_entries.async_get_entry(entry.entry_id) is None
    assert hass.states.get(role_entity_id) is None
    assert f"{entry.entry_id}_sensor_energy" not in store_manager._accumulators


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_reassign_service_rejects_unit_mismatch(
    hass: HomeAssistant,
) -> None:
    """reassign rejects a new accumulating source with a different unit."""
    device_a = _create_source_device(
        hass,
        name="Plug A",
        identifiers={("test", "plug_unit_a")},
    )
    energy_a = _create_source_entity(
        hass,
        device_id=device_a.id,
        domain="sensor",
        unique_id="plug_unit_a_energy",
        object_id="plug_unit_a_energy",
        original_name="Energy",
        device_class=SensorDeviceClass.ENERGY,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )
    hass.states.async_set(
        energy_a.entity_id,
        "100.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )

    entry = await _create_runtime_role_entry(
        hass,
        role_name="Projector",
        device_id=device_a.id,
        mappings=[
            _make_mapping(
                slot="sensor_energy",
                source_unique_id=energy_a.unique_id,
                source_entity_id=energy_a.entity_id,
                domain="sensor",
                device_class="energy",
                state_class="total_increasing",
            )
        ],
    )
    hass.states.async_set(
        energy_a.entity_id,
        "110.0",
        {"unit_of_measurement": "kWh", "state_class": "total_increasing"},
    )
    await hass.async_block_till_done()

    device_b = _create_source_device(
        hass,
        name="Plug B",
        identifiers={("test", "plug_unit_b")},
    )
    energy_b = _create_source_entity(
        hass,
        device_id=device_b.id,
        domain="sensor",
        unique_id="plug_unit_b_energy",
        object_id="plug_unit_b_energy",
        original_name="Energy",
        device_class=SensorDeviceClass.ENERGY,
        unit_of_measurement="Wh",
    )
    hass.states.async_set(
        energy_b.entity_id,
        "50000.0",
        {"unit_of_measurement": "Wh", "state_class": "total_increasing"},
    )

    with pytest.raises(ServiceValidationError, match="unit"):
        await hass.services.async_call(
            DOMAIN,
            "reassign",
            {
                "config_entry_id": entry.entry_id,
                "device_id": device_b.id,
                "assignments": [
                    {
                        "role_entity_id": "sensor.projector_energy",
                        "entity_id": energy_b.entity_id,
                    }
                ],
            },
            blocking=True,
            return_response=True,
        )
