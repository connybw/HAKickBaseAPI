"""Transfer market, scouted players, and league player deep-dive endpoints (read-only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..client import KickbaseApiClient


class MarketEndpoints:
    """Endpoints for transfer market, scouting watchlist, and player analytics."""

    def __init__(self, client: KickbaseApiClient) -> None:
        self._client = client

    async def get_market(self, league_id: str) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/market — active transfer market listings."""
        return await self._client.async_get(f"/v4/leagues/{league_id}/market")

    async def get_scouted_players(self, league_id: str) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/scoutedplayers — manager's scout watchlist."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/scoutedplayers", allow_404=True
        )

    async def get_player_details(self, league_id: str, player_id: str) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/players/{playerId}."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/players/{player_id}"
        )

    async def get_player_transfers(self, league_id: str, player_id: str) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/players/{playerId}/transfers — active offers & status."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/players/{player_id}/transfers", allow_404=True
        )

    async def get_player_transfer_history(
        self, league_id: str, player_id: str, *, start: int = 0
    ) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/players/{playerId}/transferHistory."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/players/{player_id}/transferHistory",
            params={"start": start},
            allow_404=True,
        )

    async def get_player_market_value(
        self, league_id: str, player_id: str, timeframe: int = 92
    ) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/players/{playerId}/marketvalue/{timeframe}."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/players/{player_id}/marketvalue/{timeframe}",
            allow_404=True,
        )

    async def get_player_performance(self, league_id: str, player_id: str) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/players/{playerId}/performance."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/players/{player_id}/performance",
            allow_404=True,
        )

    async def get_league_team_profile(self, league_id: str, team_id: str) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/teams/{teamId}/teamprofile/."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/teams/{team_id}/teamprofile/",
            allow_404=True,
        )
