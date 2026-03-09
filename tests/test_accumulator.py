# ABOUTME: Tests for the energy session accumulator logic.
# ABOUTME: Covers delta tracking, session commit/resume, reset detection, and persistence.

import pytest

from custom_components.device_role.accumulator import EnergyAccumulator


class TestEnergyAccumulator:
    """Tests for EnergyAccumulator math and session management."""

    def test_initial_state_is_zero(self) -> None:
        """A fresh accumulator starts at zero."""
        acc = EnergyAccumulator()
        assert acc.role_value == 0.0

    def test_accumulates_delta_from_session_start(self) -> None:
        """Accumulator tracks deltas from the session start reading."""
        acc = EnergyAccumulator()
        acc.start_session(physical_reading=100.0)
        assert acc.role_value == 0.0

        acc.update(110.0)
        assert acc.role_value == 10.0

        acc.update(115.0)
        assert acc.role_value == 15.0

    def test_commit_session_preserves_accumulated_value(self) -> None:
        """Committing a session freezes the accumulated value."""
        acc = EnergyAccumulator()
        acc.start_session(physical_reading=50.0)
        acc.update(60.0)
        assert acc.role_value == 10.0

        acc.commit_session()
        assert acc.role_value == 10.0

    def test_new_session_resumes_from_committed_value(self) -> None:
        """A new session resumes accumulation from the committed total."""
        acc = EnergyAccumulator()
        acc.start_session(physical_reading=50.0)
        acc.update(60.0)
        acc.commit_session()

        # New session (possibly different device) at reading 200
        acc.start_session(physical_reading=200.0)
        assert acc.role_value == 10.0  # Still the committed value

        acc.update(205.0)
        assert acc.role_value == 15.0  # 10 committed + 5 new

    def test_multiple_sessions(self) -> None:
        """Test the scenario from the analysis: projector → christmas lights → projector."""
        acc = EnergyAccumulator()

        # Projector session: plug at 50 kWh, uses 10
        acc.start_session(physical_reading=50.0)
        acc.update(60.0)
        assert acc.role_value == 10.0
        acc.commit_session()

        # Christmas lights happen on the same plug (60 → 80 kWh)
        # but projector role is disabled. No updates to this accumulator.

        # Projector resumes when plug is at 80 kWh
        acc.start_session(physical_reading=80.0)
        assert acc.role_value == 10.0  # Frozen at committed

        # Projector uses 5 more kWh
        acc.update(85.0)
        assert acc.role_value == 15.0

    def test_ignores_non_numeric_updates(self) -> None:
        """Non-numeric values (None) are ignored, value holds steady."""
        acc = EnergyAccumulator()
        acc.start_session(physical_reading=100.0)
        acc.update(110.0)
        assert acc.role_value == 10.0

        acc.update(None)
        assert acc.role_value == 10.0

    def test_small_jitter_ignored(self) -> None:
        """Small negative changes (jitter) are ignored, not treated as resets."""
        acc = EnergyAccumulator()
        acc.start_session(physical_reading=100.0)
        acc.update(110.0)
        assert acc.role_value == 10.0

        # Small jitter: value drops by 0.1 kWh
        acc.update(109.9)
        assert acc.role_value == 10.0  # Holds at last good value

    def test_real_reset_detected(self) -> None:
        """A large drop (near zero) is treated as a device reset."""
        acc = EnergyAccumulator()
        acc.start_session(physical_reading=100.0)
        acc.update(110.0)
        assert acc.role_value == 10.0

        # Device reset: counter goes back to near zero
        acc.update(0.1)
        # The 10 kWh should be committed, and a new session started at 0.1
        assert acc.role_value == 10.0  # Committed value preserved

        acc.update(5.1)
        assert acc.role_value == 15.0  # 10 committed + 5 new

    def test_update_without_active_session_is_noop(self) -> None:
        """Updating without an active session does nothing."""
        acc = EnergyAccumulator()
        acc.update(100.0)
        assert acc.role_value == 0.0

    def test_commit_without_active_session_is_noop(self) -> None:
        """Committing without an active session does nothing."""
        acc = EnergyAccumulator()
        acc.commit_session()
        assert acc.role_value == 0.0

    def test_serialization_roundtrip(self) -> None:
        """Accumulator state survives serialization and deserialization."""
        acc = EnergyAccumulator()
        acc.start_session(physical_reading=100.0)
        acc.update(115.0)
        acc.commit_session()
        acc.start_session(physical_reading=200.0)
        acc.update(210.0)

        state = acc.to_dict()
        restored = EnergyAccumulator.from_dict(state)

        assert restored.role_value == acc.role_value
        assert restored.role_value == 25.0  # 15 committed + 10 current

    def test_serialization_empty_accumulator(self) -> None:
        """An empty accumulator serializes and deserializes to zero."""
        acc = EnergyAccumulator()
        state = acc.to_dict()
        restored = EnergyAccumulator.from_dict(state)
        assert restored.role_value == 0.0

    def test_wh_to_kwh_conversion(self) -> None:
        """Energy values in Wh are converted to kWh."""
        acc = EnergyAccumulator()
        acc.start_session(physical_reading=100000.0, unit="Wh")
        acc.update(110000.0, unit="Wh")
        assert acc.role_value == pytest.approx(10.0)  # 10 kWh

    def test_kwh_no_conversion(self) -> None:
        """Energy values in kWh pass through without conversion."""
        acc = EnergyAccumulator()
        acc.start_session(physical_reading=100.0, unit="kWh")
        acc.update(110.0, unit="kWh")
        assert acc.role_value == 10.0

    def test_session_start_skips_unstable_zero(self) -> None:
        """Session start ignores a zero reading (device initial instability)."""
        acc = EnergyAccumulator()
        acc.start_session(physical_reading=0.0)

        # Session should not be started from an unstable zero
        # The next non-zero update should establish the session start
        acc.update(100.0)
        assert acc.role_value == 0.0  # Session started at 100, no delta yet

        acc.update(110.0)
        assert acc.role_value == 10.0

    def test_unknown_unit_ignored_on_update(self) -> None:
        """Updates with unrecognized energy units are silently skipped."""
        acc = EnergyAccumulator()
        acc.start_session(physical_reading=100.0, unit="kWh")
        acc.update(110.0, unit="kWh")
        assert acc.role_value == 10.0

        # An update in an unknown unit should be ignored, not treated as kWh
        acc.update(99999.0, unit="J")
        assert acc.role_value == 10.0

    def test_unknown_unit_ignored_on_start_session(self) -> None:
        """Starting a session with an unrecognized unit is a no-op."""
        acc = EnergyAccumulator()
        acc.start_session(physical_reading=100.0, unit="BTU")
        assert acc.session_active is False
