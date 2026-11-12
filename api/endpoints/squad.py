"""Squad, lineup, and teamcenter endpoints (read-only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..client import KickbaseApiClient


class SquadEndpoints:
    """Endpoints for squad, lineup, myeleven, and teamcenter."""

    def __init__(self, client: KickbaseApiClient) -> None:
        self._client = client

    async def get_squad(self, league_id: str) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/squad — all owned players in league."""
        return await self._client.async_get(f"/v4/leagues/{league_id}/squad")

    async def get_lineup(self, league_id: str) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/lineup — current raw lineup."""
        return await self._client.async_get(f"/v4/leagues/{league_id}/lineup", allow_404=True)

    async def get_lineup_overview(self, league_id: str) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/lineup/overview — formation, deadline, players."""
        return await self._client.async_get(f"/v4/leagues/{league_id}/lineup/overview")

    async def get_lineup_teams(self, league_id: str) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/lineup/teams — club badge mapping (`tms`)."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/lineup/teams", allow_404=True
        )

    async def get_my_eleven(self, league_id: str) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/teamcenter/myeleven — live matchday eleven."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/teamcenter/myeleven", allow_404=True
        )

    async def get_user_teamcenter(
        self, league_id: str, user_id: str, *, day_number: int | None = None
    ) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/users/{userId}/teamcenter."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/users/{user_id}/teamcenter",
            params={"dayNumber": day_number},
            allow_404=True,
        )
