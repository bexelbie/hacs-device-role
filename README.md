# Device Role — Home Assistant Custom Integration

Separate **physical device identity** from **logical function** in Home
Assistant.  Create named "roles" (like *Projector* or *Balcony*) backed by
physical devices.  When a device is replaced or moved, update the mapping —
entity IDs, history, automations, and energy dashboards stay intact.

## Problem

Home Assistant ties entity identity to the physical device that produces it.
This causes pain when:

| Scenario | What breaks |
|----------|-------------|
| A temperature sensor moves between rooms | History for both rooms is contaminated |
| A power-monitoring plug is reassigned to a different appliance | Energy dashboard shows a nonsensical sum |
| A device is replaced with a new unit | Entity IDs change; automations, dashboards, and scripts break |

**Device Role** solves this by interposing a stable logical layer between
physical devices and the rest of Home Assistant.

## How it works

```
Physical device  ──state changes──▶  Role entity  ──▶  Dashboards
  (sensor.ikea_plug_abc123_energy)     (sensor.projector_energy)   Automations
                                                                    History
```

1. **Create a role** — give it a name and select a physical device.
2. **Pick which entities to mirror** — temperature, power, energy, switch, etc.
3. Role entities appear with stable IDs derived from the role name.
4. When the physical device changes, **update the mapping** in the role's
   options.  Everything downstream keeps working.

### Energy accumulator

Energy sensors get special treatment.  A naive mirror would show the
lifetime kWh of whichever physical meter is currently attached.  Instead,
Device Role tracks a **session-based accumulator**:

```
role_energy = historical_sum + (current_reading − session_start)
```

- Activating a role starts a session and records the meter's current value.
- Only the *delta* from that point counts toward the role.
- Deactivating the role commits the delta and freezes the energy value
  (it stays available so HA statistics don't misinterpret a gap).
- Reactivating — with the same or a different device — starts a fresh session.

Reset detection handles device factory-resets (drops > 0.5 kWh) without
treating measurement jitter as a reset.

## Supported entity types

| Domain | Behavior | When role is inactive |
|--------|----------|-----------------------|
| `sensor` (measurement) | Mirrors state, device class, unit | Unavailable |
| `sensor` (energy) | Accumulates via session tracker | **Frozen** (stays available) |
| `binary_sensor` | Mirrors state and device class | Unavailable |
| `switch` | Mirrors state; forwards `turn_on`/`turn_off` | Unavailable |

## Installation

Copy `custom_components/device_role/` into your Home Assistant
`config/custom_components/` directory, then restart Home Assistant.

> **HACS support** is planned but not yet available.

## Configuration

Everything is done through the UI — no YAML.

1. **Settings → Devices & Services → Add Integration → Device Role**
2. Enter a role name (e.g. "Projector").
3. Select a physical device.
4. Choose which entities from that device to mirror.

### Options

After creation, open the integration entry to:

- **Toggle active/inactive** — deactivates mirroring and freezes energy.
- **Add or remove entities** — change which physical entities the role
  mirrors without losing accumulated energy or changing existing entity IDs.

## Requirements

- Home Assistant 2025.1 or later
- No external dependencies

## FAQ

### Does reassignment preserve energy history?

Energy history is tied to **slot names** (e.g. `sensor_energy`), which are
derived from the entity's domain and device class.  If you reassign a role
from one device to another and both devices have an energy sensor with the
same device class, the slot name stays the same and accumulated energy
carries forward seamlessly.

If the replacement device has a different set of entity types (e.g. the
old device had an energy sensor but the new one doesn't), the old slot's
energy history becomes orphaned — it's still in storage but no entity
references it.  This is by design: the role's entity IDs stay stable for
matching entities, and there's nothing meaningful to do with history from
an entity type the new device doesn't support.

### What energy units are supported?

The accumulator supports **kWh**, **Wh**, and **MWh**.  Readings in other
units are silently ignored to prevent data corruption.  If your device
reports in an unsupported unit, the energy sensor will not accumulate
until the unit is recognized.

## Development

```bash
# Create a virtualenv and install test dependencies
python -m venv venv
source venv/bin/activate
pip install -r requirements_test.txt

# Run the unit test suite (70 tests)
pytest tests/ -v --ignore=tests/e2e
```

### E2E Testing

The project includes E2E tests that run against a real Home Assistant Docker
container.  These focus on scenarios unit tests can't cover — primarily that
energy accumulator state survives HA restarts.

We evaluated three approaches:

| Approach | Verdict |
|----------|---------|
| WebSocket API (drive config flows) | ❌ Underdocumented internal protocol, fragile across HA versions |
| Playwright / headless browser | ❌ Shadow DOM selector hell, ~400MB browser dep, very flaky |
| **Pre-seed `.storage/` + REST API** | ✅ Simple, stable, tests exactly what unit tests can't |

**Why pre-seed?** Our 70 unit tests already cover config flows, options flows,
and all entity behavior via `pytest-homeassistant-custom-component`. The E2E
gap is persistence across real HA restarts — which doesn't require UI or config
flow driving.  Pre-seeding `.storage/` files is the same mechanism HA uses
internally, and REST API for states/services is stable and well-documented.

```bash
# Run E2E tests locally (requires Docker)
./scripts/run-e2e.sh
```

E2E tests run automatically on PRs via GitHub Actions.

See [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) for architecture details and
[analysis.md](analysis.md) for the original design rationale.

### Repository layout

```
custom_components/
├── device_role/           # The main integration
│   ├── __init__.py        # Setup, platform forwarding, store manager
│   ├── config_flow.py     # 3-step config flow + options flow
│   ├── sensor.py          # Measurement + energy sensors
│   ├── binary_sensor.py   # Binary sensor mirroring
│   ├── switch.py          # Switch mirroring + command forwarding
│   ├── accumulator.py     # Session-based energy accumulator (pure logic)
│   ├── helpers.py         # Runtime entity_id resolution
│   ├── const.py           # Constants and defaults
│   └── strings.json       # UI strings
│
├── fake_device/           # Test fixture integration (see its own README)

tests/                     # 70 unit tests + E2E tests
├── e2e/                   # E2E tests against real HA Docker container
│   ├── ha_client.py       # REST API client (onboard, auth, state, service)
│   └── seed.py            # .storage/ file pre-seeding helpers
├── test_*.py              # Unit tests

scripts/
  run-e2e.sh               # Local E2E runner

.github/workflows/
  unit-tests.yml            # Unit tests on push + PR
  e2e.yml                   # E2E tests on PR only
```

## License

TBD
