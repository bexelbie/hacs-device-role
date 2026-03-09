# Fake Device — Home Assistant Test Fixture Integration

A standalone Home Assistant custom integration that creates **virtual
multi-entity devices** with deterministic, programmatic control.  Built for
integration testing but also useful for demos and UI development.

## What it creates

Each config entry produces one device with six entities:

| Entity | Domain | Device Class | Unit | Initial value |
|--------|--------|-------------|------|---------------|
| Temperature | `sensor` | `temperature` | °C | 20.0 |
| Humidity | `sensor` | `humidity` | % | 50.0 |
| Power | `sensor` | `power` | W | 0.0 |
| Energy | `sensor` | `energy` (total_increasing) | kWh | 0.0 |
| Connectivity | `binary_sensor` | `connectivity` | — | on |
| Outlet | `switch` | — | — | off |

Entity IDs follow the pattern `{domain}.{device_name}_{key}` — for example,
`sensor.my_plug_temperature` and `switch.my_plug_outlet`.

## Installation

Copy `custom_components/fake_device/` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

**Settings → Devices & Services → Add Integration → Fake Device**, then
enter a name.  That's it — all six entities appear immediately.

Create multiple entries for multiple independent devices.

## The `set_value` service

The integration registers a `fake_device.set_value` service for
deterministic control of any entity it manages:

```yaml
# Set a sensor to an exact value
service: fake_device.set_value
data:
  entity_id: sensor.my_plug_energy
  value: 42.5

# Make an entity unavailable
service: fake_device.set_value
data:
  entity_id: sensor.my_plug_temperature
  value: "unavailable"

# Set an entity to unknown state
service: fake_device.set_value
data:
  entity_id: sensor.my_plug_power
  value: "unknown"

# Control a binary sensor
service: fake_device.set_value
data:
  entity_id: binary_sensor.my_plug_connectivity
  value: false

# Control a switch (also responds to switch.turn_on / switch.turn_off)
service: fake_device.set_value
data:
  entity_id: switch.my_plug_outlet
  value: true
```

## Testing energy sequences

The `set_value` service makes it straightforward to simulate real-world
energy meter behavior, including resets:

```yaml
# Normal accumulation
- service: fake_device.set_value
  data: { entity_id: sensor.plug_energy, value: 1.0 }
- service: fake_device.set_value
  data: { entity_id: sensor.plug_energy, value: 2.5 }
- service: fake_device.set_value
  data: { entity_id: sensor.plug_energy, value: 5.0 }

# Simulate a device factory reset (counter drops to zero)
- service: fake_device.set_value
  data: { entity_id: sensor.plug_energy, value: 0.0 }

# Accumulation resumes from zero
- service: fake_device.set_value
  data: { entity_id: sensor.plug_energy, value: 0.3 }
```

## Design notes

- **No persistence** — state is lost on restart.  This is intentional;
  it's a test fixture, not a production device.
- **No external dependencies** — uses only built-in Home Assistant APIs.
- **Extractable** — this integration has no imports from `device_role` or
  any other custom component.  It can be moved to its own repository as-is.

## Development

```bash
pytest tests/test_fake_device.py -v   # 9 tests
```
