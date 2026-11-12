"""Manager profiles and league activity feed endpoints (read-only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..client import KickbaseApiClient


class ManagerEndpoints:
    """Endpoints for manager dashboards/squads/transfers and activity feeds."""

    def __init__(self, client: KickbaseApiClient) -> None:
        self._client = client

    async def get_activities_feed(
        self,
        league_id: str,
        *,
        start: int = 0,
        max_items: int = 25,
        filter_type: str | None = None,
    ) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/activitiesFeed."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/activitiesFeed",
            params={"start": start, "max": max_items, "filter": filter_type},
            allow_404=True,
        )

    async def get_activity_detail(
        self, league_id: str, activity_id: str
    ) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/activitiesFeed/{activityId}."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/activitiesFeed/{activity_id}",
            allow_404=True,
        )

    async def get_activity_comments(
        self, league_id: str, activity_id: str, *, start: int = 0, max_items: int = 20
    ) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/activitiesFeed/{activityId}/comments."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/activitiesFeed/{activity_id}/comments",
            params={"start": start, "max": max_items},
            allow_404=True,
        )

    async def get_manager_dashboard(
        self, league_id: str, manager_id: str
    ) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/managers/{managerId}/dashboard."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/managers/{manager_id}/dashboard",
            allow_404=True,
        )

    async def get_manager_squad(
        self, league_id: str, manager_id: str
    ) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/managers/{manager_id}/squad."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/managers/{manager_id}/squad",
            allow_404=True,
        )

    async def get_manager_performance(
        self, league_id: str, manager_id: str
    ) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/managers/{managerId}/performance."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/managers/{manager_id}/performance",
            allow_404=True,
        )

    async def get_manager_transfers(
        self, league_id: str, manager_id: str, *, start: int = 0
    ) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/managers/{managerId}/transfer."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/managers/{manager_id}/transfer",
            params={"start": start},
            allow_404=True,
        )
