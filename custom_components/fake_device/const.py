# ABOUTME: Constants for the fake_device integration.
# ABOUTME: Domain name, platform list, service names, and entity specifications.

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)

DOMAIN = "fake_device"
PLATFORMS = ["sensor", "binary_sensor", "switch"]
SERVICE_SET_VALUE = "set_value"

# Each fake device creates all of these entities. One device, many domains.
ENTITY_SPECS = [
    {
        "domain": "sensor",
        "key": "temperature",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "initial": 20.0,
    },
    {
        "domain": "sensor",
        "key": "humidity",
        "device_class": SensorDeviceClass.HUMIDITY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "%",
        "initial": 50.0,
    },
    {
        "domain": "sensor",
        "key": "power",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "initial": 0.0,
    },
    {
        "domain": "sensor",
        "key": "energy",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "initial": 0.0,
    },
    {
        "domain": "binary_sensor",
        "key": "connectivity",
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
        "initial": True,
    },
    {
        "domain": "switch",
        "key": "outlet",
        "initial": False,
    },
]
