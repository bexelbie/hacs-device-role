# Device Role — Home Assistant Custom Integration

Device Role lets you separate **physical device identity** from **what that device is currently doing** in Home Assistant.
You create named roles like `Projector` or `Balcony`, back them with real devices, and get stable entities that keep their IDs and history even when you move or replace the underlying hardware.

## Why you might want this

Home Assistant ties entity identity to the physical device. That hurts when you:

- **Move a sensor between locations**  
  A “Balcony Temperature” sensor spends a week in your freezer for debugging. Your balcony history now shows −18 °C in July.

- **Reuse a power-monitoring plug**  
  A smart plug moves from “Projector” to “Christmas Lights” and back. The energy dashboard thinks the projector burned power for both.

- **Replace a dead device**  
  You pair a new unit and get new entity IDs. Renaming the new entities in the wrong order can orphan history and break automations.

Device Role gives you a stable logical layer on top of those physical devices, so automations and dashboards point at what you care about, not at whatever MAC address happens to be there today.

## What Device Role does

At a high level:

- You create a **role** (for example, `Projector` or `Balcony`).
- You assign it to a **physical device** that already exists in Home Assistant.
- You pick which entities from that device to expose through the role.
- Device Role creates new “role entities” (like `sensor.projector_energy`) that your dashboards, automations, and the energy dashboard use.
- When you move or replace hardware, you update the role’s backing device. The role entities keep their IDs and, where it makes sense, their history.

Visually:

```
Physical device (Zigbee plug, sensor, etc)
  │
  │ state changes
  ▼
Role entities (sensor.projector_power, sensor.projector_energy, ...)
  │
  ▼
Dashboards / Automations / History / Energy
```

### Entity behavior

Each role can be **active** or **inactive**:

- When a role is active, its entities track the underlying physical device.
- When a role is inactive, its entities stop updating; how that looks in HA depends on the domain.

Supported domains and behavior:

| Domain | Behavior when role is active | Behavior when role is inactive |
|--------|------------------------------|--------------------------------|
| `sensor` (measurement) | Mirrors state, device class, and unit | Becomes unavailable |
| `sensor` (total_increasing) | Tracks cumulative value using a role-local accumulator | Stays available at a frozen value |
| `binary_sensor` | Mirrors state and device class | Becomes unavailable |
| `switch` | Mirrors state; forwards `turn_on` / `turn_off` | Becomes unavailable |

Accumulating sensors (any sensor with `state_class: total_increasing`) are the one special case:

- When a role is active, its accumulating sensor tracks consumption into a role-local total.
- When you deactivate the role, the sensor holds its last value and stays available, even if the physical device keeps running.
- When you reactivate the role (with the same or a different compatible device), the sensor resumes from that held value and ignores whatever the device did in between.
- This works for energy (kWh), water (m³), gas (ft³), and any other cumulative sensor.

## Installation

### HACS (recommended)

1. In Home Assistant, open **HACS**.
2. Three-dot menu → **Custom repositories**.
3. Add `https://github.com/bexelbie/hacs-device-role` with category **Integration**.
4. After it appears in HACS, install **Device Role**.
5. Restart Home Assistant.

HACS will let you know when updates are available.

### Manual installation

1. Copy the `custom_components/device_role/` directory from this repository.
2. Place it into your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.

## Setup and configuration

Everything is done through the UI. No YAML required.

1. Go to **Settings → Devices & Services → Add integration**.
2. Search for **Device Role**.
3. Enter a **role name** (for example, `Projector` or `Balcony`).
4. Pick the **physical device** to back the role.
5. Select which entities from that device you want the role to expose.

This creates a “role device” with its own entities. Use those role entities everywhere you previously used the physical ones.

### Changing a role later

From **Settings → Devices & Services → Device Role**:

1. Find the role.
2. Click the **⋮** menu.
3. Choose **Configure**.

From there you can:

- **Toggle active / inactive**  
  - Active: role entities track the physical device.  
  - Inactive: measurement and binary sensors become unavailable; accumulating sensors stay available at a frozen value.

- **Change which entities are mirrored**  
  - Add or remove individual entities from the backing device.  
  - Changing the set of mirrored entities does not change existing role entity IDs.

- **Reassign the role to a different device**  
  - Point the same role at a new physical device that has compatible entities (for example, a replacement smart plug).  
  - For compatible accumulating entities, the role’s accumulated history is preserved.

### Deleting a role

From the role’s **⋮** menu, choose **Delete**.

This removes:

- The role device
- All role entities
- Any stored accumulator state for that role

Automations and dashboards that reference those role entities will need to be updated or removed, just like removing any other integration.

## Usage examples

### Reusing a power plug (Projector ↔ Christmas Lights)

- Create a role called `Projector` and assign it to your smart plug.
- Mirror the switch, power, and energy entities.
- Point your projector automations and energy dashboard at the role entities.

In December:

- Deactivate `Projector`.
- Create a `Christmas Lights` role assigned to the same physical plug, with its own entities.
- Point any holiday automations at `Christmas Lights`.

In January:

- Deactivate `Christmas Lights`.
- Reactivate `Projector`.

Result:

- Projector energy history is clean and continuous across seasons.
- Christmas lights get their own separate history.
- No entity renaming. No dashboard surgery.

### Moving a temperature sensor (Balcony ↔ Basement)

- Create a `Balcony` role for your temperature/humidity sensor and use it in dashboards and automations.
- When you move the physical sensor to the basement:
  - Deactivate `Balcony`.
  - Create a `Basement` role assigned to the same device.

Result:

- Balcony history stops cleanly when you moved the sensor.
- Basement history starts fresh.

### Replacing a dead device

- Your projector plug dies. You pair a new one and keep its physical name separate from any roles.
- Open the `Projector` role, go to **Configure**, and reassign it to the new device.
- Role entity IDs stay the same; history and automations keep working.

## Limitations and caveats

- **Supported domains**  
  - Only `sensor`, `binary_sensor`, and `switch` are supported today.  
  - Lights, covers, climate, and more complex domains are not mirrored yet.

- **One active role per physical device entity**  
  - A physical entity can only be assigned to a single active role at a time.

- **Unit compatibility on reassignment**  
  - The options flow will reject reassignment to a device that reports a different unit for an accumulating sensor (e.g., kWh → Wh, or kWh → gal). To change units, delete and recreate the role.

- **No pre-seeding of accumulator values**  
  - New roles always start their accumulators at zero.

- **Recorder and storage**  
  - By default both the physical entity and the role entity are recorded.  
  - If you want to save space, you can exclude the physical entities from the recorder in Home Assistant’s settings.

## Requirements

- Home Assistant 2026.1.0 or later
- No external dependencies

## FAQ

### Does reassignment preserve accumulator history?

Yes, as long as the new device reports the same unit of measurement for the matching sensor slot. The options flow will prevent reassignment if the units don’t match.

If the new device doesn’t expose a matching accumulating entity, the old history is kept in storage but no longer attached to an active role entity.

### What sensors use the accumulator?

Any sensor with `state_class: total_increasing` gets a role-local accumulator. This includes energy (kWh), water (m³), gas (ft³), and any other cumulative sensor. The accumulator stores values in whatever unit the source entity reports — no conversion is applied.

### What happens if I uninstall the integration?

If you remove the integration:

- All role devices and entities disappear.
- Any automations, dashboards, or energy dashboard configuration that reference role entities will break in the same way they would if you removed any other integration.

You can always reinstall Device Role later, but the role entities will be recreated fresh.

## License

MIT
