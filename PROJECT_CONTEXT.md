# Device Role — Developer Reference

## Tech Stack

- **Language**: Python 3.12+
- **Platform**: Home Assistant custom integration
- **Target HA version**: 2026.1.0+
- **Testing**: pytest + pytest-homeassistant-custom-component
- **CI**: GitHub Actions (unit tests on push, E2E on PR, release on tag)

## Build / Test Commands

```bash
# Install test dependencies
pip install -r requirements_test.txt

# Run unit tests (78 tests, excludes E2E)
pytest tests/ -v --ignore=tests/e2e

# Run E2E tests locally (requires Docker)
./scripts/run-e2e.sh

# Run a specific test file
pytest tests/test_accumulator.py -v
```

## Architecture

- **One config entry = one role**. Users add roles via Settings → Integrations → Add.
- **Slot-based entity mapping**: Each mirrored entity gets a slot (e.g., `sensor_temperature`).
  Slot names are stable across device replacements. Role entity unique_ids = `{entry_id}_{slot}`.
- **Energy accumulator**: Tracks deltas per session. Persisted via HA Store API.
  Energy role entities freeze (stay available) when inactive; other types go unavailable.
- **Physical entity references**: Stored by entity registry unique_id, not entity_id string.
  Resolved to current entity_id at runtime via `helpers.resolve_source_entity_id()`.

## Testing

**Unit tests** use `pytest-homeassistant-custom-component` which provides a
mock HA core but exercises real integration code. The `fake_device` test
fixture (in `tests/fixtures/`) creates virtual multi-entity devices with a
deterministic `set_value` service. It's symlinked into `custom_components/`
at test collection time.

**E2E tests** run against a real HA Docker container. They use pre-seeded
`.storage/` files + REST API (not WebSocket config flows or browser
automation) because config flows are already covered by unit tests. The E2E
gap is specifically persistence across real HA restarts.

## Releasing

GitHub Release notes are sourced from the tagged commit message.
Tags containing `-` (e.g. `v0.1.1-beta.1`) are automatically created as
GitHub pre-releases. HACS only shows stable releases to users by default.

### Beta / pre-release flow

```bash
# 1. Bump version in manifest.json to e.g. 0.1.1-beta.1
# 2. Commit with the code changes and a beta release note
git commit -m "v0.1.1-beta.1

- Searchable device picker
- via_device linking"

# 3. Tag and push
git tag v0.1.1-beta.1
git push origin main --tags
# → workflow creates a GitHub pre-release (HACS ignores it)

# 4. Test on your HA instance
# 5. When satisfied, bump manifest.json to 0.1.1
# 6. Commit with the polished release note
git commit -m "v0.1.1 Release

- Device picker is now a searchable dropdown
- Role devices link back to their physical device"

# 7. Tag and push
git tag v0.1.1
git push origin main --tags
# → workflow creates a stable GitHub Release (HACS notifies users)
```

### Stable-only flow (no beta)

```bash
# 1. Bump version in custom_components/device_role/manifest.json
# 2. Commit with release notes in the message body
git commit -m "v0.2.0

- Added device reassignment workflow
- Fixed energy accumulator restart persistence"

# 3. Tag and push
git tag v0.2.0
git push origin main --tags
```

The release workflow (`release.yml`) runs unit tests, validates that
`manifest.json` version matches the tag, then creates a GitHub Release.
Pre-release detection is automatic based on `-` in the tag name.

## Known Limitations

- **TOCTOU race in entity claim checks**: Concurrent config flows could both
  pass claim validation. Documented, not fixed (YAGNI — user-driven UI, same
  pattern as all HA flows).
- **Slot-name orphaning on reassignment**: If the new device has different
  entity types, old slot history is orphaned in storage. By design.
