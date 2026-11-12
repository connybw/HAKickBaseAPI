"""Challenges, lobby, divisions, and socialhub endpoints (read-only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..client import KickbaseApiClient


class ChallengeEndpoints:
    """Endpoints under `/v4/challenges`."""

    def __init__(self, client: KickbaseApiClient) -> None:
        self._client = client

    async def get_lobby_overview(self) -> dict[str, Any]:
        """GET /v4/challenges/lobby/overview."""
        return await self._client.async_get("/v4/challenges/lobby/overview", allow_404=True)

    async def get_lobby_live(self) -> dict[str, Any]:
        """GET /v4/challenges/lobby/overview/live."""
        return await self._client.async_get(
            "/v4/challenges/lobby/overview/live", allow_404=True
        )

    async def get_lobby_profile(self) -> dict[str, Any]:
        """GET /v4/challenges/lobby/profile."""
        return await self._client.async_get("/v4/challenges/lobby/profile", allow_404=True)

    async def get_division_ladder(self) -> dict[str, Any]:
        """GET /v4/challenges/lobby/divisionLadder."""
        return await self._client.async_get(
            "/v4/challenges/lobby/divisionLadder", allow_404=True
        )

    async def get_skill_points_summary(self) -> dict[str, Any]:
        """GET /v4/challenges/lobby/skillPoints/summary."""
        return await self._client.async_get(
            "/v4/challenges/lobby/skillPoints/summary", allow_404=True
        )

    async def get_lobby_explore(self) -> dict[str, Any]:
        """GET /v4/challenges/lobby/explore."""
        return await self._client.async_get("/v4/challenges/lobby/explore", allow_404=True)

    async def get_lobby_archive(self) -> dict[str, Any]:
        """GET /v4/challenges/lobby/archive."""
        return await self._client.async_get("/v4/challenges/lobby/archive", allow_404=True)

    async def get_overview(self) -> dict[str, Any]:
        """GET /v4/challenges/overview."""
        return await self._client.async_get("/v4/challenges/overview", allow_404=True)

    async def get_selection(self) -> dict[str, Any]:
        """GET /v4/challenges/selection."""
        return await self._client.async_get("/v4/challenges/selection", allow_404=True)

    async def get_recommended(self) -> dict[str, Any]:
        """GET /v4/challenges/recommended."""
        return await self._client.async_get("/v4/challenges/recommended", allow_404=True)

    async def get_archive(self) -> dict[str, Any]:
        """GET /v4/challenges/archive."""
        return await self._client.async_get("/v4/challenges/archive", allow_404=True)

    async def get_socialhub(self, *, start: int = 0, max_items: int = 20) -> dict[str, Any]:
        """GET /v4/challenges/socialhub."""
        return await self._client.async_get(
            "/v4/challenges/socialhub",
            params={"start": start, "max": max_items},
            allow_404=True,
        )

    async def get_challenge_profile(self, challenge_id: str) -> dict[str, Any]:
        """GET /v4/challenges/{challengeId}/profile."""
        return await self._client.async_get(
            f"/v4/challenges/{challenge_id}/profile", allow_404=True
        )

    async def get_challenge_lineup_overview(self, challenge_id: str) -> dict[str, Any]:
        """GET /v4/challenges/{challengeId}/lineup/overview."""
        return await self._client.async_get(
            f"/v4/challenges/{challenge_id}/lineup/overview", allow_404=True
        )

    async def get_challenge_livepitch(self, challenge_id: str) -> dict[str, Any]:
        """GET /v4/challenges/{challengeId}/lineup/livepitch."""
        return await self._client.async_get(
            f"/v4/challenges/{challenge_id}/lineup/livepitch", allow_404=True
        )

    async def get_challenge_table(self, challenge_id: str) -> dict[str, Any]:
        """GET /v4/challenges/{challengeId}/table."""
        return await self._client.async_get(
            f"/v4/challenges/{challenge_id}/table", allow_404=True
        )

    async def get_challenge_ranking(
        self, challenge_id: str, *, day_number: int | None = None
    ) -> dict[str, Any]:
        """GET /v4/challenges/{challengeId}/ranking."""
        return await self._client.async_get(
            f"/v4/challenges/{challenge_id}/ranking",
            params={"dayNumber": day_number},
            allow_404=True,
        )

    async def get_challenge_top10(
        self, challenge_id: str, *, scope: str | None = None, max_items: int = 10
    ) -> dict[str, Any]:
        """GET /v4/challenges/{challengeId}/top10."""
        return await self._client.async_get(
            f"/v4/challenges/{challenge_id}/top10",
            params={"scope": scope, "max": max_items},
            allow_404=True,
        )
