"""League overview, budget, ranking, battles, settings, and achievements endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..client import KickbaseApiClient


class LeagueEndpoints:
    """Endpoints under `/v4/leagues`."""

    def __init__(self, client: KickbaseApiClient) -> None:
        self._client = client

    async def get_leagues(self) -> dict[str, Any]:
        """GET /v4/leagues — list of user's leagues."""
        return await self._client.async_get("/v4/leagues")

    async def get_selection(self) -> dict[str, Any]:
        """GET /v4/leagues/selection — detailed league selection cards."""
        return await self._client.async_get("/v4/leagues/selection")

    async def get_recommended(self) -> dict[str, Any]:
        """GET /v4/leagues/recommended — recommended public leagues."""
        return await self._client.async_get("/v4/leagues/recommended", allow_404=True)

    async def get_overview(
        self, league_id: str, *, include_managers_and_battles: bool = True
    ) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/overview."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/overview",
            params={"includeManagersAndBattles": include_managers_and_battles},
        )

    async def get_me(self, league_id: str) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/me — user status, team player counts, budget."""
        return await self._client.async_get(f"/v4/leagues/{league_id}/me")

    async def get_my_budget(self, league_id: str) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/me/budget — available budget & max negative (`pbas`)."""
        return await self._client.async_get(f"/v4/leagues/{league_id}/me/budget")

    async def get_ranking(
        self, league_id: str, *, day_number: int | None = None
    ) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/ranking — overall or matchday standings."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/ranking",
            params={"dayNumber": day_number},
        )

    async def get_settings(self, league_id: str) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/settings."""
        return await self._client.async_get(f"/v4/leagues/{league_id}/settings", allow_404=True)

    async def get_settings_managers(self, league_id: str) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/settings/managers."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/settings/managers", allow_404=True
        )

    async def get_battle_users(self, league_id: str, battle_type: int | str) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/battles/{type}/users."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/battles/{battle_type}/users", allow_404=True
        )

    async def get_achievements(self, league_id: str) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/user/achievements."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/user/achievements", allow_404=True
        )

    async def get_achievement_detail(
        self, league_id: str, achievement_type: int | str
    ) -> dict[str, Any]:
        """GET /v4/leagues/{leagueId}/user/achievements/{type}."""
        return await self._client.async_get(
            f"/v4/leagues/{league_id}/user/achievements/{achievement_type}", allow_404=True
        )
