"""Authentication, user profile, and global config endpoints (read-only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..client import KickbaseApiClient


class AuthEndpoints:
    """Endpoints under `/v4/user`, `/v4/config`, `/v4/settings`, `/v4/refiner`."""

    def __init__(self, client: KickbaseApiClient) -> None:
        self._client = client

    async def get_me(self) -> dict[str, Any]:
        """GET /v4/user/me — current user profile."""
        return await self._client.async_get("/v4/user/me")

    async def get_settings(self) -> dict[str, Any]:
        """GET /v4/user/settings — user settings."""
        return await self._client.async_get("/v4/user/settings")

    async def get_config(self) -> dict[str, Any]:
        """GET /v4/config — global platform and competition config."""
        return await self._client.async_get("/v4/config")

    async def get_config_version(self) -> dict[str, Any]:
        """GET /v4/config/version — image base path (ibp) and feature flags."""
        return await self._client.async_get("/v4/config/version")

    async def get_subscription_status(self) -> dict[str, Any]:
        """GET /v4/settings/subscriptionStatus — subscription info."""
        return await self._client.async_get("/v4/settings/subscriptionStatus", allow_404=True)

    async def get_refiner_identify(self) -> dict[str, Any]:
        """GET /v4/refiner/identify — user traits and summary stats."""
        return await self._client.async_get("/v4/refiner/identify", allow_404=True)
