# ABOUTME: Energy session accumulator for device_role integration.
# ABOUTME: Tracks cumulative energy per role across sessions, with persistent storage.

from __future__ import annotations

from .const import ENERGY_INTERNAL_UNIT, ENERGY_RESET_THRESHOLD

# Conversion factors to kWh
_UNIT_TO_KWH: dict[str, float] = {
    "kWh": 1.0,
    "Wh": 0.001,
    "MWh": 1000.0,
}


def _to_kwh(value: float, unit: str) -> float:
    """Convert an energy value to kWh."""
    factor = _UNIT_TO_KWH.get(unit, 1.0)
    return value * factor


class EnergyAccumulator:
    """Tracks cumulative energy for a role across multiple sessions.

    Each session records deltas from a physical energy sensor. Sessions
    are committed when a role is deactivated or its device is replaced.
    The accumulator's value only increases.
    """

    def __init__(self) -> None:
        """Initialize an empty accumulator."""
        self._historical_sum: float = 0.0
        self._session_start: float | None = None
        self._last_physical: float | None = None
        self._session_active: bool = False
        # When session starts with zero, defer start until first real reading
        self._awaiting_stable_start: bool = False

    @property
    def role_value(self) -> float:
        """The role's accumulated energy value in kWh."""
        if not self._session_active or self._last_physical is None or self._session_start is None:
            return self._historical_sum
        delta = self._last_physical - self._session_start
        return self._historical_sum + max(0.0, delta)

    def start_session(self, physical_reading: float, unit: str = ENERGY_INTERNAL_UNIT) -> None:
        """Begin a new accumulation session from the current physical reading."""
        reading_kwh = _to_kwh(physical_reading, unit)

        if reading_kwh == 0.0:
            # Device may be reporting an unstable initial value
            self._session_active = True
            self._awaiting_stable_start = True
            self._session_start = None
            self._last_physical = None
            return

        self._session_start = reading_kwh
        self._last_physical = reading_kwh
        self._session_active = True
        self._awaiting_stable_start = False

    def update(self, physical_reading: float | None, unit: str = ENERGY_INTERNAL_UNIT) -> None:
        """Process a new reading from the physical energy sensor."""
        if not self._session_active:
            return

        if physical_reading is None:
            return

        reading_kwh = _to_kwh(physical_reading, unit)

        # Handle deferred session start (initial zero instability)
        if self._awaiting_stable_start:
            if reading_kwh == 0.0:
                return
            self._session_start = reading_kwh
            self._last_physical = reading_kwh
            self._awaiting_stable_start = False
            return

        # Reset detection: large drop indicates device reset
        if self._last_physical is not None and reading_kwh < self._last_physical:
            drop = self._last_physical - reading_kwh
            if drop > ENERGY_RESET_THRESHOLD:
                # Commit current session, start fresh from the reset value
                self._commit_current_delta()
                self._session_start = reading_kwh
                self._last_physical = reading_kwh
                return
            else:
                # Small jitter — ignore
                return

        self._last_physical = reading_kwh

    def commit_session(self) -> None:
        """Commit the current session's delta to the historical sum."""
        if not self._session_active:
            return
        self._commit_current_delta()
        self._session_active = False
        self._session_start = None
        self._last_physical = None
        self._awaiting_stable_start = False

    def _commit_current_delta(self) -> None:
        """Add the current session's delta to the historical sum."""
        if self._session_start is not None and self._last_physical is not None:
            delta = self._last_physical - self._session_start
            self._historical_sum += max(0.0, delta)

    def to_dict(self) -> dict:
        """Serialize accumulator state for persistent storage."""
        return {
            "historical_sum": self._historical_sum,
            "session_start": self._session_start,
            "last_physical": self._last_physical,
            "session_active": self._session_active,
            "awaiting_stable_start": self._awaiting_stable_start,
        }

    @classmethod
    def from_dict(cls, data: dict) -> EnergyAccumulator:
        """Restore accumulator state from persistent storage."""
        acc = cls()
        acc._historical_sum = data.get("historical_sum", 0.0)
        acc._session_start = data.get("session_start")
        acc._last_physical = data.get("last_physical")
        acc._session_active = data.get("session_active", False)
        acc._awaiting_stable_start = data.get("awaiting_stable_start", False)
        return acc
