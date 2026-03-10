# ABOUTME: Session accumulator for total_increasing sensors in the device_role integration.
# ABOUTME: Tracks cumulative values per role across sessions, with persistent storage.

from __future__ import annotations

import logging

from .const import RESET_DROP_FRACTION

_LOGGER = logging.getLogger(__name__)


class SessionAccumulator:
    """Tracks a cumulative total_increasing value for a role across sessions.

    Each session records deltas from a physical sensor. Sessions are
    committed when a role is deactivated or its device is replaced.
    The accumulator's value only increases.
    """

    def __init__(self) -> None:
        """Initialize an empty accumulator."""
        self._historical_sum: float = 0.0
        self._session_start: float | None = None
        self._last_physical: float | None = None
        self._session_active: bool = False
        self._unit: str | None = None
        # When session starts with zero, defer start until first real reading
        self._awaiting_stable_start: bool = False

    @property
    def role_value(self) -> float:
        """The role's accumulated value."""
        if not self._session_active or self._last_physical is None or self._session_start is None:
            return self._historical_sum
        delta = self._last_physical - self._session_start
        return self._historical_sum + max(0.0, delta)

    @property
    def session_active(self) -> bool:
        """Whether the accumulator currently has an active session."""
        return self._session_active

    @property
    def unit(self) -> str | None:
        """The unit of measurement locked for this accumulator."""
        return self._unit

    def start_session(self, physical_reading: float, unit: str) -> bool:
        """Begin a new accumulation session from the current physical reading.

        Returns False and logs an error if the unit conflicts with a
        previously stored unit.
        """
        if self._unit is not None and unit != self._unit:
            _LOGGER.error(
                "Unit mismatch: accumulator has '%s' but source reports '%s'. "
                "Delete and recreate the role to change units",
                self._unit,
                unit,
            )
            return False

        self._unit = unit

        if physical_reading == 0.0:
            # Device may be reporting an unstable initial value
            self._session_active = True
            self._awaiting_stable_start = True
            self._session_start = None
            self._last_physical = None
            return True

        self._session_start = physical_reading
        self._last_physical = physical_reading
        self._session_active = True
        self._awaiting_stable_start = False
        return True

    def update(self, physical_reading: float | None) -> None:
        """Process a new reading from the physical sensor."""
        if not self._session_active:
            return

        if physical_reading is None:
            return

        # Handle deferred session start (initial zero instability)
        if self._awaiting_stable_start:
            if physical_reading == 0.0:
                return
            self._session_start = physical_reading
            self._last_physical = physical_reading
            self._awaiting_stable_start = False
            return

        # Reset detection: drop exceeding the threshold fraction
        if self._last_physical is not None and physical_reading < self._last_physical:
            drop_fraction = (
                (self._last_physical - physical_reading) / self._last_physical
                if self._last_physical > 0
                else 1.0
            )
            if drop_fraction > RESET_DROP_FRACTION:
                self._commit_current_delta()
                self._session_start = physical_reading
                self._last_physical = physical_reading
                return
            else:
                # Small jitter — ignore
                return

        self._last_physical = physical_reading

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
            "unit": self._unit,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SessionAccumulator:
        """Restore accumulator state from persistent storage."""
        acc = cls()
        acc._historical_sum = data.get("historical_sum", 0.0)
        acc._session_start = data.get("session_start")
        acc._last_physical = data.get("last_physical")
        acc._session_active = data.get("session_active", False)
        acc._awaiting_stable_start = data.get("awaiting_stable_start", False)
        acc._unit = data.get("unit")
        return acc
