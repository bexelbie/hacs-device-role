# ABOUTME: Thin synchronous REST client for talking to a real Home Assistant instance.
# ABOUTME: Handles onboarding, authentication, state reads, and service calls.

from __future__ import annotations

import logging
import time

import requests

_LOGGER = logging.getLogger(__name__)

_ONBOARDING_NAME = "E2E Test"
_ONBOARDING_USERNAME = "e2e"
_ONBOARDING_PASSWORD = "e2e-test-password"
_ONBOARDING_LANGUAGE = "en"
_CLIENT_ID = "http://127.0.0.1:8123/"


class HAClient:
    """Synchronous REST client for a running Home Assistant instance."""

    def __init__(self, base_url: str = "http://127.0.0.1:8123") -> None:
        self._base_url = base_url.rstrip("/")
        self._token: str | None = None
        self._session = requests.Session()

    def close(self) -> None:
        self._session.close()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def wait_for_ready(self, timeout: float = 120, poll_interval: float = 2) -> None:
        """Poll GET /api/ until HA responds or timeout expires."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                resp = self._session.get(
                    f"{self._base_url}/api/",
                    timeout=5,
                )
                if resp.status_code in (200, 401):
                    _LOGGER.info("HA is ready (status %d)", resp.status_code)
                    return
            except requests.ConnectionError:
                pass
            time.sleep(poll_interval)
        raise TimeoutError(f"HA did not become ready within {timeout}s")

    def onboard_and_authenticate(self) -> None:
        """Complete onboarding (if needed) and obtain an access token."""
        # Check if onboarding is needed
        resp = self._session.get(
            f"{self._base_url}/api/onboarding",
            headers=self._headers(),
        )
        onboarding_steps = resp.json()

        needs_user = any(
            step.get("step") == "user" and not step.get("done")
            for step in onboarding_steps
        )

        if needs_user:
            resp = self._session.post(
                f"{self._base_url}/api/onboarding/users",
                json={
                    "name": _ONBOARDING_NAME,
                    "username": _ONBOARDING_USERNAME,
                    "password": _ONBOARDING_PASSWORD,
                    "language": _ONBOARDING_LANGUAGE,
                    "client_id": _CLIENT_ID,
                },
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            auth_code = resp.json()["auth_code"]

            # Exchange auth code for token
            resp = self._session.post(
                f"{self._base_url}/auth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "client_id": _CLIENT_ID,
                },
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
        else:
            # Already onboarded — authenticate with existing credentials
            resp = self._session.post(
                f"{self._base_url}/auth/login_flow",
                json={
                    "client_id": _CLIENT_ID,
                    "handler": ["homeassistant", None],
                    "redirect_uri": _CLIENT_ID,
                },
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            flow = resp.json()

            resp = self._session.post(
                f"{self._base_url}/auth/login_flow/{flow['flow_id']}",
                json={
                    "username": _ONBOARDING_USERNAME,
                    "password": _ONBOARDING_PASSWORD,
                    "client_id": _CLIENT_ID,
                },
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            auth_code = resp.json().get("result")

            if auth_code:
                resp = self._session.post(
                    f"{self._base_url}/auth/token",
                    data={
                        "grant_type": "authorization_code",
                        "code": auth_code,
                        "client_id": _CLIENT_ID,
                    },
                )
                resp.raise_for_status()
                self._token = resp.json()["access_token"]

        if not self._token:
            raise RuntimeError("Failed to obtain access token")
        _LOGGER.info("Authenticated with HA")

    def get_state(self, entity_id: str) -> dict | None:
        """Get the state object for an entity. Returns None if not found."""
        resp = self._session.get(
            f"{self._base_url}/api/states/{entity_id}",
            headers=self._headers(),
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_states(self) -> list[dict]:
        """Get all entity states."""
        resp = self._session.get(
            f"{self._base_url}/api/states",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def call_service(
        self, domain: str, service: str, data: dict | None = None
    ) -> None:
        """Call a HA service."""
        resp = self._session.post(
            f"{self._base_url}/api/services/{domain}/{service}",
            json=data or {},
            headers=self._headers(),
        )
        resp.raise_for_status()

    def wait_for_state(
        self,
        entity_id: str,
        expected_state: str,
        timeout: float = 30,
        poll_interval: float = 1,
    ) -> dict:
        """Poll an entity state until it matches expected value or times out."""
        deadline = time.monotonic() + timeout
        last_state = None
        while time.monotonic() < deadline:
            state = self.get_state(entity_id)
            if state and state.get("state") == expected_state:
                return state
            last_state = state
            time.sleep(poll_interval)
        actual = last_state.get("state") if last_state else "not found"
        raise TimeoutError(
            f"{entity_id}: expected '{expected_state}', got '{actual}' after {timeout}s"
        )
