# Device Roles for Home Assistant: Problem Analysis and Proposed Solution

## The Problem

Home Assistant users who own multiple identical physical devices — particularly temperature/humidity sensors and power-monitoring smart plugs — face a naming and identity problem that Home Assistant does not currently solve well.

Consider a household with three identical Zigbee temperature sensors. They are physically indistinguishable. To tell them apart, the owner puts stickers on them: one gets a picture of a cartoon dog, one gets a reindeer sticker, one gets a snowman. These stickers become the physical identity of each sensor. The sensors get paired to Home Assistant with names reflecting those stickers.

But the sticker name is not what the user actually cares about in their dashboards, automations, or voice assistants. The sensor with the cartoon dog lives on the balcony. The user wants to see "Balcony Temperature," not "Cartoon Dog Temperature." Today, the user renames the entities.

This works fine until something changes. Change comes for many reasons, but it could just be a cyclical adjustment.  In the summer, the user monitors their balcony temperature to know whether they want to extend their awning or not. But in the winter, they might move that same temperature sensor to another location, such as their basement, to determine if they should run auxiliary heating. They don't want to have to own two things each used six months of the year.

### The Renaming Tax

A temperature sensor has two entities (temperature and humidity). Renaming those is annoying but manageable. A power-monitoring smart plug, however, can have four or more entities: switch, power, summation delivered, voltage, current, and others. Renaming all of them every time the plug moves to a different appliance is tedious and error-prone.

### History Contamination

If a temperature sensor named "Balcony" gets temporarily moved into a freezer to diagnose a problem, the balcony's temperature history now shows a period of -18°C in July. There is no clean way to separate "this was actually the balcony" from "this was temporarily the freezer." The history is contaminated, and it stays contaminated.

### Energy Dashboard Corruption

This is the most consequential problem. A power-monitoring smart plug on a projector tracks cumulative energy consumption. If the plug gets moved to Christmas lights for six weeks, those kilowatt-hours accrue against the projector in the energy dashboard. When the plug returns to the projector in January, the projector's energy history now includes a block of Christmas light usage. Home Assistant's energy dashboard has no concept of "this entity was measuring a different thing for a while."

### Device Replacement Pain

When a physical device dies and gets replaced with an identical unit, the new device gets new entity IDs. The user must carefully delete the old entity, pair the new device, and rename the new entity to exactly match the old one — in that specific order. Getting the order wrong orphans the history. There are [ongoing conversations](https://community.home-assistant.io/t/add-a-method-of-replacing-devices/249462) about this problem in the Home Assistant community.

---

## Proposed Solution: A Role Abstraction Layer

The core idea is to separate physical device identity from logical function.

A **physical device** keeps a permanent name reflecting how you identify it in the real world — its sticker, its number, its color. It is paired once and never renamed. It is managed by whatever integration handles the hardware (ZHA, Z-Wave, etc.).

A **role** is a logical entity that represents what the device is currently doing: "Projector," "Balcony," "Christmas Lights." The role has its own entities — its own sensor, its own switch. Automations, dashboards, the energy dashboard, and voice assistants all reference the role, never the physical device directly.

A custom integration manages the mapping between physical devices and roles. When a physical device changes purpose, the user updates the mapping. The role entities' IDs never change, so nothing else breaks.

### What This Looks Like in Practice

1. A smart plug is paired via ZHA. The user has put an orange heart sticker on it, so it is named "Smart Plug Orange Heart." This name never changes.

2. The user creates a role called "Projector" and assigns the orange heart plug to it. The integration inspects the physical device and shows all its entities. The user selects which ones matter for this role — perhaps just the switch, the power reading, and the energy total. The integration creates role entities: `switch.projector`, `sensor.projector_power`, `sensor.projector_energy`.

3. Automations and dashboards reference the role entities.

4. In December, the user moves the plug to Christmas lights. They disable the "Projector" role and create a "Christmas Lights" role assigned to the same physical device. The projector's history stops cleanly. Christmas lights get fresh entities with fresh history.

5. In January, the user disables "Christmas Lights" and re-enables "Projector." The projector role resumes from where it left off. No history contamination. No energy dashboard corruption.

6. If the physical plug dies, the user pairs a new one and reassigns the "Projector" role to it. The role's entity IDs did not change. Nothing else in Home Assistant notices the swap.

---

## How Different Entity Types Are Handled

Not all entities behave the same way when mirrored through a role.

### Measurement Sensors

Temperature, humidity, power (watts), voltage, air quality — these report the current state of something. A role entity for a measurement sensor simply mirrors the physical sensor's current value. When the role is disabled, the role entity becomes unavailable. When re-enabled, it starts reporting again. History shows a clean gap during the disabled period.

### Cumulative Sensors

Sensors with `state_class: total_increasing` are fundamentally different from measurement sensors. They report a cumulative total that only increases (energy in kWh, water in m³, gas in ft³, etc.). The energy dashboard calculates consumption by looking at the difference between readings over time.

A role entity for energy cannot simply mirror the physical sensor's value. If a plug reads 100 kWh lifetime when assigned to "Projector," the projector role should show 0, not 100. If the plug later reads 110 kWh, the projector role should show 10. If the plug moves away and comes back when the physical counter reads 150 kWh, the projector role should resume at 10 — not jump to 50.

This requires what we are calling a **session accumulator**: the role entity maintains its own running total by tracking deltas from the physical sensor only during periods when the role is active. The math is:

```
role_energy = sum_of_previous_sessions + (current_physical_reading − reading_when_this_session_started)
```

When a role is disabled, the current session's delta gets added to the historical sum, and the role entity freezes at that value. When re-enabled (possibly with a different physical device), a new session starts from the new device's current reading, and the role entity resumes incrementing from where it left off.

Consider the following scenario:

| Event | Physical Sensor | Projector Role | Christmas Lights Role |
|---|---|---|---|
| Plug paired (lifetime 50 kWh) | 50 | — | — |
| Create "Projector" role | 50 | 0 | — |
| Projector uses 10 kWh | 60 | 10 | — |
| Disable Projector, create Christmas Lights | 60 | 10 (frozen) | 0 |
| Christmas lights use 20 kWh | 80 | 10 (frozen) | 20 |
| Disable Christmas Lights, re-enable Projector | 80 | 10 (resumes) | 20 (frozen) |
| Projector uses 5 more kWh | 85 | 15 | 20 (frozen) |

The accumulator state must be persisted to survive Home Assistant restarts. Writes are throttled to protect SD cards (periodic saves plus saves on role changes and HA shutdown), not on every state update.

### Actionable Entities (Switches)

A role's switch entity mirrors the physical switch's state and forwards commands to it. Turning on `switch.projector` turns on the physical plug. Turning off the role turns off the physical plug. This is straightforward for switches.

Lights, covers, and climate devices are significantly more complex — a light needs brightness, color temperature, RGB values, effects, and transitions forwarded correctly. This complexity is addressed in the "Deferred and Possibly Never Handled" section below.

---

## Edge Cases and How They Are Addressed

### Energy Sensor Reset Detection

Physical energy sensors sometimes report a slightly lower value than the previous reading due to rounding, firmware quirks, or reporting jitter. A naive approach of treating any decrease as a device reset (counter returning to zero) would cause the accumulator to overcount energy by prematurely committing and restarting sessions.

Reset detection needs a tolerance threshold: only treat a decrease as a true reset when the drop is material — for example, when the new value is near zero or the decrease exceeds a configurable threshold. Small negative jitter should be ignored.

### Unit Mismatches When Replacing Devices

If a user replaces a device that reports energy in kWh with one that reports in Wh, the accumulator's historical sum becomes incompatible with the new device's readings. The integration prevents reassignment when units do not match. The options flow rejects the change and instructs the user to delete and recreate the role.

### Non-Numeric and Unavailable States

Physical sensors can temporarily report "unknown" or "unavailable" during network issues, re-pairing, or restarts. The accumulator must never update its tracking values based on non-numeric states. The role entity should hold its last known value during these transient interruptions.

### Race Conditions During Role Changes

If a physical sensor state change arrives between the moment a role is committed and the moment a new session starts, the delta could be double-counted or lost. Role change operations (commit, reassign, start new session) must be atomic with respect to incoming state changes.

### New Device Initial Value Instability

Some devices briefly report zero or unknown values immediately after pairing before settling to their actual reading. Starting a session from a transient zero would cause the accumulator to overcount. Session start should be delayed until the physical sensor has reported stable numeric values.

### Energy Entity Behavior While Role Is Inactive

For measurement sensors, becoming "unavailable" while the role is disabled is correct — it creates a clean gap in history. For energy sensors, this is problematic: Home Assistant's statistics processing may interpret the transition from unavailable back to a value as consumption during the gap. Energy role entities should instead remain available but frozen at their last value while the role is inactive.

### Simultaneous Role Claims

A single physical entity should back at most one active role at a time. If two roles could claim the same physical energy sensor simultaneously, both would accumulate the same deltas, double-counting consumption. This is prevented by validation.

### Physical Consumption While No Role Is Active

If a plug is physically on and consuming power but no role is active for it, that energy is not attributed to any role. This is by design — the role represents intentional tracking of a specific use. But it may surprise users who expect all energy to be accounted for somewhere.

---

## Deferred and Possibly Never Handled

### Light, Cover, and Climate Entity Forwarding

Forwarding commands for a switch (on/off) is simple. Forwarding for a light requires handling brightness, color temperature, RGB/HS color spaces, effects, and transitions. Covers need position and tilt. Climate devices need HVAC modes, target temperature ranges, and fan modes. Each domain has its own set of supported features that must be detected and forwarded correctly.

This is a long tail of work that does not block the core value proposition. Sensors and switches cover the majority of the use cases that motivate this integration (temperature sensors that move, power-monitoring plugs that get reassigned). Light, cover, and climate forwarding can be added later if demand justifies the effort, or may never be needed — these devices tend to be permanently installed and rarely change roles.

### Integration Removal

If this integration is uninstalled, all role entities disappear. Any automation, dashboard, energy dashboard configuration, or voice assistant exposure referencing a role entity will break. This is the same behavior as removing any other Home Assistant integration. The integration could warn on uninstall or offer to export role definitions as standalone YAML template sensors, but this is a convenience feature, not a requirement.

### Forgetting to Update Roles

If a user physically moves a sensor but forgets to update the role assignment, the role will report data from the wrong location. This is a human process problem, not a software problem. The integration's contribution is making the swap fast enough that people are more likely to actually do it. Anomaly detection ("this sensor's readings changed drastically, did you move it?") is a possible future feature but is not part of the core design.

### Recorder Double-Counting

Both the physical entity and the role entity are recorded by Home Assistant's recorder, storing overlapping data. For most use cases this is acceptable — the overhead is minimal compared to the benefits. Users who want to optimize can exclude physical entities from the recorder. This is a documentation topic, not an architectural concern.

### Meter Wraparound

Some physical meters roll over at a maximum value (e.g., 65535 Wh). The accumulator's reset detection handles this similarly to a true reset — it commits the current session and starts a new one. There may be a small over- or under-count depending on where in the cycle the wrap occurs, but this is a rare edge case with minimal impact.

---

## Technical Feasibility

The following Home Assistant APIs and patterns support this integration:

- **Entity registry introspection** (`entity_registry.async_entries_for_device`) allows discovering all entities belonging to a physical device, including their domain, device class, state class, and unit of measurement.

- **Custom integration entity creation** allows creating sensor, switch, and other entity types with correct metadata (device_class, state_class, unit_of_measurement) that Home Assistant's energy dashboard and long-term statistics accept.

- **State change listeners** allow subscribing to physical entity updates and computing role entity values in response.

- **HA storage API** (`.storage` with `async_delay_save`) provides persistent storage that survives restarts while throttling writes for SD card longevity.

- **Device registry** allows creating logical devices (one per role) that appear in the UI with area assignment and entity grouping.

Role entity IDs use standard Home Assistant domains (`sensor.projector_energy`, `switch.projector`) rather than a custom domain, ensuring compatibility with all parts of Home Assistant that expect standard entity ID formats.

Internal references to physical devices are stored by entity registry unique ID rather than entity ID string, so that user renames of physical entities do not break role mappings.
