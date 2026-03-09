# ABOUTME: Thin async REST client for talking to a real Home Assistant instance.
# ABOUTME: Handles onboarding, authentication, state reads, and service calls.

from __future__ import annotations

import asyncio
import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)

_ONBOARDING_NAME = "E2E Test"
_ONBOARDING_USERNAME = "e2e"
_ONBOARDING_PASSWORD = "e2e-test-password"
_ONBOARDING_LANGUAGE = "en"
_CLIENT_ID = "http://localhost:8123/"


class HAClient:
    """REST client for a running Home Assistant instance."""

    def __init__(self, base_url: str = "http://localhost:8123") -> None:
        self._base_url = base_url.rstrip("/")
        self._token: str | None = None
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> HAClient:
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *exc) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def wait_for_ready(self, timeout: float = 120, poll_interval: float = 2) -> None:
        """Poll GET /api/ until HA responds or timeout expires."""
        deadline = asyncio.get_event_loop().time() + timeout
        assert self._session is not None
        while asyncio.get_event_loop().time() < deadline:
            try:
                async with self._session.get(
                    f"{self._base_url}/api/",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        _LOGGER.info("HA is ready")
                        return
                    # 401 means HA is up but we're not authenticated yet — still ready
                    if resp.status == 401:
                        _LOGGER.info("HA is ready (needs auth)")
                        return
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass
            await asyncio.sleep(poll_interval)
        raise TimeoutError(f"HA did not become ready within {timeout}s")

    async def onboard_and_authenticate(self) -> None:
        """Complete onboarding (if needed) and obtain an access token."""
        assert self._session is not None

        # Check if onboarding is needed
        async with self._session.get(
            f"{self._base_url}/api/onboarding",
            headers=self._headers(),
        ) as resp:
            onboarding_steps = await resp.json()

        needs_user = any(
            step.get("step") == "user" and not step.get("done")
            for step in onboarding_steps
        )

        if needs_user:
            async with self._session.post(
                f"{self._base_url}/api/onboarding/users",
                json={
                    "name": _ONBOARDING_NAME,
                    "username": _ONBOARDING_USERNAME,
                    "password": _ONBOARDING_PASSWORD,
                    "language": _ONBOARDING_LANGUAGE,
                    "client_id": _CLIENT_ID,
                },
                headers={"Content-Type": "application/json"},
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                auth_code = data["auth_code"]

            # Exchange auth code for token
            async with self._session.post(
                f"{self._base_url}/auth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "client_id": _CLIENT_ID,
                },
            ) as resp:
                resp.raise_for_status()
                token_data = await resp.json()
                self._token = token_data["access_token"]
        else:
            # Already onboarded — authenticate with existing credentials
            async with self._session.post(
                f"{self._base_url}/auth/login_flow",
                json={"client_id": _CLIENT_ID, "handler": ["homeassistant", None], "redirect_uri": _CLIENT_ID},
                headers={"Content-Type": "application/json"},
            ) as resp:
                resp.raise_for_status()
                flow = await resp.json()

            async with self._session.post(
                f"{self._base_url}/auth/login_flow/{flow['flow_id']}",
                json={"username": _ONBOARDING_USERNAME, "password": _ONBOARDING_PASSWORD, "client_id": _CLIENT_ID},
                headers={"Content-Type": "application/json"},
            ) as resp:
                resp.raise_for_status()
                result = await resp.json()
                auth_code = result.get("result")

            if auth_code:
                async with self._session.post(
                    f"{self._base_url}/auth/token",
                    data={
                        "grant_type": "authorization_code",
                        "code": auth_code,
                        "client_id": _CLIENT_ID,
                    },
                ) as resp:
                    resp.raise_for_status()
                    token_data = await resp.json()
                    self._token = token_data["access_token"]

        if not self._token:
            raise RuntimeError("Failed to obtain access token")
        _LOGGER.info("Authenticated with HA")

    async def get_state(self, entity_id: str) -> dict | None:
        """Get the state object for an entity. Returns None if not found."""
        assert self._session is not None
        async with self._session.get(
            f"{self._base_url}/api/states/{entity_id}",
            headers=self._headers(),
        ) as resp:
            if resp.status == 404:
                return None
            resp.raise_for_status()
            return await resp.json()

    async def get_states(self) -> list[dict]:
        """Get all entity states."""
        assert self._session is not None
        async with self._session.get(
            f"{self._base_url}/api/states",
            headers=self._headers(),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def call_service(
        self, domain: str, service: str, data: dict | None = None
    ) -> None:
        """Call a HA service."""
        assert self._session is not None
        async with self._session.post(
            f"{self._base_url}/api/services/{domain}/{service}",
            json=data or {},
            headers=self._headers(),
        ) as resp:
            resp.raise_for_status()

    async def wait_for_state(
        self,
        entity_id: str,
        expected_state: str,
        timeout: float = 30,
        poll_interval: float = 1,
    ) -> dict:
        """Poll an entity state until it matches expected value or times out."""
        deadline = asyncio.get_event_loop().time() + timeout
        last_state = None
        while asyncio.get_event_loop().time() < deadline:
            state = await self.get_state(entity_id)
            if state and state.get("state") == expected_state:
                return state
            last_state = state
            await asyncio.sleep(poll_interval)
        actual = last_state.get("state") if last_state else "not found"
        raise TimeoutError(
            f"{entity_id}: expected '{expected_state}', got '{actual}' after {timeout}s"
        )
