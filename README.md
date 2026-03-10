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

### HACS (recommended)

1. Open HACS in your Home Assistant instance.
2. Go to the three-dot menu → **Custom repositories**.
3. Paste `https://github.com/bexelbie/hacs-device-role` and select category **Integration**.
4. Click **Add**, then find "Device Role" in the HACS integration list and install it.
5. Restart Home Assistant.

HACS will notify you when new releases are available.

### Manual

Copy `custom_components/device_role/` into your Home Assistant
`config/custom_components/` directory, then restart Home Assistant.

## Configuration

Everything is done through the UI — no YAML.

1. **Settings → Devices & Services → Add Integration → Device Role**
2. Enter a role name (e.g. "Projector").
3. Select a physical device.
4. Choose which entities from that device to mirror.

### Options

After creation, open **Settings → Devices & Services → Device Role**, click
the **⋮** menu on your role entry, and choose **Configure** to:

- **Toggle active/inactive** — deactivates mirroring and freezes energy.
- **Add or remove entities** — change which physical entities the role
  mirrors without losing accumulated energy or changing existing entity IDs.
- **Reassign to a different device** — swap the physical device backing the
  role while preserving slot-based energy history.

### Deleting a role

From the same **⋮** menu, choose **Delete**. This removes the role device,
all its entities, and purges any stored energy accumulator data.

## Requirements

- Home Assistant 2026.1.0 or later
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

## Contributing

See [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) for build commands, architecture,
testing, and release process.  See [analysis.md](analysis.md) for the original
design rationale.

## License

MIT
