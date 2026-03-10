# ABOUTME: Tests for the session accumulator logic.
# ABOUTME: Covers delta tracking, session commit/resume, reset detection, and persistence.

import pytest

from custom_components.device_role.accumulator import SessionAccumulator


class TestSessionAccumulator:
    """Tests for SessionAccumulator math and session management."""

    def test_initial_state_is_zero(self) -> None:
        """A fresh accumulator starts at zero."""
        acc = SessionAccumulator()
        assert acc.role_value == 0.0

    def test_accumulates_delta_from_session_start(self) -> None:
        """Accumulator tracks deltas from the session start reading."""
        acc = SessionAccumulator()
        acc.start_session(physical_reading=100.0, unit="kWh")
        assert acc.role_value == 0.0

        acc.update(110.0)
        assert acc.role_value == 10.0

        acc.update(115.0)
        assert acc.role_value == 15.0

    def test_commit_session_preserves_accumulated_value(self) -> None:
        """Committing a session freezes the accumulated value."""
        acc = SessionAccumulator()
        acc.start_session(physical_reading=50.0, unit="kWh")
        acc.update(60.0)
        assert acc.role_value == 10.0

        acc.commit_session()
        assert acc.role_value == 10.0

    def test_new_session_resumes_from_committed_value(self) -> None:
        """A new session resumes accumulation from the committed total."""
        acc = SessionAccumulator()
        acc.start_session(physical_reading=50.0, unit="kWh")
        acc.update(60.0)
        acc.commit_session()

        # New session (possibly different device) at reading 200
        acc.start_session(physical_reading=200.0, unit="kWh")
        assert acc.role_value == 10.0  # Still the committed value

        acc.update(205.0)
        assert acc.role_value == 15.0  # 10 committed + 5 new

    def test_multiple_sessions(self) -> None:
        """Test the scenario from the analysis: projector → christmas lights → projector."""
        acc = SessionAccumulator()

        # Projector session: plug at 50 kWh, uses 10
        acc.start_session(physical_reading=50.0, unit="kWh")
        acc.update(60.0)
        assert acc.role_value == 10.0
        acc.commit_session()

        # Christmas lights happen on the same plug (60 → 80 kWh)
        # but projector role is disabled. No updates to this accumulator.

        # Projector resumes when plug is at 80 kWh
        acc.start_session(physical_reading=80.0, unit="kWh")
        assert acc.role_value == 10.0  # Frozen at committed

        # Projector uses 5 more kWh
        acc.update(85.0)
        assert acc.role_value == 15.0

    def test_ignores_non_numeric_updates(self) -> None:
        """Non-numeric values (None) are ignored, value holds steady."""
        acc = SessionAccumulator()
        acc.start_session(physical_reading=100.0, unit="kWh")
        acc.update(110.0)
        assert acc.role_value == 10.0

        acc.update(None)
        assert acc.role_value == 10.0

    def test_small_jitter_ignored(self) -> None:
        """Small negative changes (jitter) are ignored, not treated as resets."""
        acc = SessionAccumulator()
        acc.start_session(physical_reading=100.0, unit="kWh")
        acc.update(110.0)
        assert acc.role_value == 10.0

        # Small jitter: value drops by 0.1 (< 10% of 110)
        acc.update(109.9)
        assert acc.role_value == 10.0  # Holds at last good value

    def test_real_reset_detected(self) -> None:
        """A large drop (> 10% of last reading) is treated as a device reset."""
        acc = SessionAccumulator()
        acc.start_session(physical_reading=100.0, unit="kWh")
        acc.update(110.0)
        assert acc.role_value == 10.0

        # Device reset: counter goes back to near zero (> 10% drop)
        acc.update(0.1)
        # The 10 kWh should be committed, and a new session started at 0.1
        assert acc.role_value == 10.0  # Committed value preserved

        acc.update(5.1)
        assert acc.role_value == 15.0  # 10 committed + 5 new

    def test_update_without_active_session_is_noop(self) -> None:
        """Updating without an active session does nothing."""
        acc = SessionAccumulator()
        acc.update(100.0)
        assert acc.role_value == 0.0

    def test_commit_without_active_session_is_noop(self) -> None:
        """Committing without an active session does nothing."""
        acc = SessionAccumulator()
        acc.commit_session()
        assert acc.role_value == 0.0

    def test_serialization_roundtrip(self) -> None:
        """Accumulator state survives serialization and deserialization."""
        acc = SessionAccumulator()
        acc.start_session(physical_reading=100.0, unit="kWh")
        acc.update(115.0)
        acc.commit_session()
        acc.start_session(physical_reading=200.0, unit="kWh")
        acc.update(210.0)

        state = acc.to_dict()
        restored = SessionAccumulator.from_dict(state)

        assert restored.role_value == acc.role_value
        assert restored.role_value == 25.0  # 15 committed + 10 current

    def test_serialization_empty_accumulator(self) -> None:
        """An empty accumulator serializes and deserializes to zero."""
        acc = SessionAccumulator()
        state = acc.to_dict()
        restored = SessionAccumulator.from_dict(state)
        assert restored.role_value == 0.0

    def test_stores_values_in_native_unit(self) -> None:
        """Values are stored in the source's native unit — no conversion."""
        acc = SessionAccumulator()
        acc.start_session(physical_reading=1000.0, unit="gal")
        acc.update(1050.0)
        assert acc.role_value == 50.0  # 50 gallons

    def test_session_start_skips_unstable_zero(self) -> None:
        """Session start ignores a zero reading (device initial instability)."""
        acc = SessionAccumulator()
        acc.start_session(physical_reading=0.0, unit="kWh")

        # Session should not be started from an unstable zero
        # The next non-zero update should establish the session start
        acc.update(100.0)
        assert acc.role_value == 0.0  # Session started at 100, no delta yet

        acc.update(110.0)
        assert acc.role_value == 10.0

    def test_unit_mismatch_rejects_session(self) -> None:
        """Starting a session with a different unit than previously stored is rejected."""
        acc = SessionAccumulator()
        acc.start_session(physical_reading=100.0, unit="kWh")
        acc.update(110.0)
        acc.commit_session()
        assert acc.role_value == 10.0

        result = acc.start_session(physical_reading=5000.0, unit="Wh")
        assert result is False
        assert acc.session_active is False

    def test_unit_persisted_in_serialization(self) -> None:
        """The unit is stored and restored across serialization."""
        acc = SessionAccumulator()
        acc.start_session(physical_reading=100.0, unit="L")
        acc.update(150.0)

        state = acc.to_dict()
        restored = SessionAccumulator.from_dict(state)

        assert restored.unit == "L"
        assert restored.role_value == 50.0

    def test_unit_property(self) -> None:
        """The unit property returns None before first session, then the locked unit."""
        acc = SessionAccumulator()
        assert acc.unit is None

        acc.start_session(physical_reading=10.0, unit="m³")
        assert acc.unit == "m³"
