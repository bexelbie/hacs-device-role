# Device Role — Home Assistant Custom Integration

## Overview

Separates physical device identity from logical function in Home Assistant.
A "role" is a logical entity (e.g., "Projector", "Balcony") backed by a physical
device. Reassigning the physical device doesn't change the role's entity IDs,
history, or energy accumulation.

See `analysis.md` for the full problem space and design rationale.

## Tech Stack

- **Language**: Python 3.12+
- **Platform**: Home Assistant custom integration
- **Target HA version**: 2025.x+
- **Testing**: pytest + pytest-homeassistant-custom-component

## Project Layout

```
custom_components/device_role/   # The integration
    __init__.py                  # Setup/teardown, platform forwarding
    manifest.json                # HA integration manifest
    config_flow.py               # Config flow + options flow
    const.py                     # Constants and defaults
    sensor.py                    # Measurement + energy role sensors
    switch.py                    # Switch role entities
    binary_sensor.py             # Binary sensor role entities
    accumulator.py               # Energy session accumulator
    strings.json                 # UI strings
    translations/en.json         # English translations

tests/                           # pytest test suite
    conftest.py                  # Shared fixtures
    test_*.py                    # Test modules
```

## Build / Test Commands

```bash
# Install test dependencies
pip install -r requirements_test.txt

# Run tests
pytest tests/ -v

# Run a specific test file
pytest tests/test_init.py -v
```

## Architecture

- **One config entry = one role**. Users add roles via Settings → Integrations → Add.
- **Slot-based entity mapping**: Each mirrored entity gets a slot (e.g., `sensor_temperature`).
  Slot names are stable across device replacements. Role entity unique_ids = `{entry_id}_{slot}`.
- **Energy accumulator**: Tracks deltas per session. Persisted via HA Store API.
  Energy role entities freeze (stay available) when inactive; other types go unavailable.
- **Physical entity references**: Stored by entity registry unique_id, not entity_id string.
