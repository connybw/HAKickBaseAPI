"""Competition, matchday, match details, and live event types endpoints (read-only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..client import KickbaseApiClient


class CompetitionEndpoints:
    """Endpoints under `/v4/competitions`, `/v4/matches`, and `/v4/live`."""

    def __init__(self, client: KickbaseApiClient) -> None:
        self._client = client

    async def get_competitions(self) -> dict[str, Any]:
        """GET /v4/competitions."""
        return await self._client.async_get("/v4/competitions")

    async def get_matchdays(self, competition_id: str) -> dict[str, Any]:
        """GET /v4/competitions/{competitionId}/matchdays."""
        return await self._client.async_get(
            f"/v4/competitions/{competition_id}/matchdays"
        )

    async def get_table(self, competition_id: str) -> dict[str, Any]:
        """GET /v4/competitions/{competitionId}/table."""
        return await self._client.async_get(
            f"/v4/competitions/{competition_id}/table"
        )

    async def get_ranking(self, competition_id: str) -> dict[str, Any]:
        """GET /v4/competitions/{competitionId}/ranking."""
        return await self._client.async_get(
            f"/v4/competitions/{competition_id}/ranking"
        )

    async def get_players(
        self,
        competition_id: str,
        *,
        position: int | str | None = None,
        sorting: int | str | None = None,
    ) -> dict[str, Any]:
        """GET /v4/competitions/{competitionId}/players."""
        return await self._client.async_get(
            f"/v4/competitions/{competition_id}/players",
            params={"position": position, "sorting": sorting},
        )

    async def search_players(
        self,
        competition_id: str,
        *,
        query: str,
        league_id: str | None = None,
        start: int = 0,
        max_items: int = 25,
    ) -> dict[str, Any]:
        """GET /v4/competitions/{competitionId}/players/search."""
        return await self._client.async_get(
            f"/v4/competitions/{competition_id}/players/search",
            params={
                "leagueId": league_id,
                "query": query,
                "start": start,
                "max": max_items,
            },
        )

    async def get_player_details(
        self, competition_id: str, player_id: str
    ) -> dict[str, Any]:
        """GET /v4/competitions/{competitionId}/players/{playerId}."""
        return await self._client.async_get(
            f"/v4/competitions/{competition_id}/players/{player_id}"
        )

    async def get_player_center(
        self,
        competition_id: str,
        player_id: str,
        *,
        day_number: int | None = None,
        league_id: str | None = None,
    ) -> dict[str, Any]:
        """GET /v4/competitions/{competitionId}/playercenter/{playerId}."""
        return await self._client.async_get(
            f"/v4/competitions/{competition_id}/playercenter/{player_id}",
            params={"dayNumber": day_number, "leagueId": league_id},
            allow_404=True,
        )

    async def get_player_market_value(
        self, competition_id: str, player_id: str, timeframe: int = 92
    ) -> dict[str, Any]:
        """GET /v4/competitions/{competitionId}/players/{playerId}/marketvalue/{timeframe}."""
        return await self._client.async_get(
            f"/v4/competitions/{competition_id}/players/{player_id}/marketvalue/{timeframe}",
            allow_404=True,
        )

    async def get_player_performance(
        self, competition_id: str, player_id: str
    ) -> dict[str, Any]:
        """GET /v4/competitions/{competitionId}/players/{playerId}/performance."""
        return await self._client.async_get(
            f"/v4/competitions/{competition_id}/players/{player_id}/performance",
            allow_404=True,
        )

    async def get_team_center(
        self, competition_id: str, team_id: str, *, day_number: int | None = None
    ) -> dict[str, Any]:
        """GET /v4/competitions/{competitionId}/teams/{teamId}/teamcenter."""
        return await self._client.async_get(
            f"/v4/competitions/{competition_id}/teams/{team_id}/teamcenter",
            params={"dayNumber": day_number},
            allow_404=True,
        )

    async def get_team_profile(
        self, competition_id: str, team_id: str
    ) -> dict[str, Any]:
        """GET /v4/competitions/{competitionId}/teams/{teamId}/teamprofile."""
        return await self._client.async_get(
            f"/v4/competitions/{competition_id}/teams/{team_id}/teamprofile",
            allow_404=True,
        )

    async def get_match_details(self, match_id: str) -> dict[str, Any]:
        """GET /v4/matches/{matchId}/details."""
        return await self._client.async_get(f"/v4/matches/{match_id}/details")

    async def get_live_event_types(self) -> dict[str, Any]:
        """GET /v4/live/eventtypes — master lookup map for live match events."""
        return await self._client.async_get("/v4/live/eventtypes")
