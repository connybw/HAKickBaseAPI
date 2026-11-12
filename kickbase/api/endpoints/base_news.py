"""Base stage, news, and team predicted lineups endpoints (read-only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..client import KickbaseApiClient


class BaseNewsEndpoints:
    """Endpoints under `/v4/base`."""

    def __init__(self, client: KickbaseApiClient) -> None:
        self._client = client

    async def get_overview(self) -> dict[str, Any]:
        """GET /v4/base/overview — stage headlines and sectioned news."""
        return await self._client.async_get("/v4/base/overview", allow_404=True)

    async def get_stage(self) -> dict[str, Any]:
        """GET /v4/base/stage — featured stage items and competitions."""
        return await self._client.async_get("/v4/base/stage", allow_404=True)

    async def get_news(
        self, competition_id: str, *, start: int = 0, max_items: int = 25
    ) -> dict[str, Any]:
        """GET /v4/base/news/{competitionId} — competition news feed."""
        return await self._client.async_get(
            f"/v4/base/news/{competition_id}",
            params={"start": start, "max": max_items},
            allow_404=True,
        )

    async def get_permanent_news(self, competition_id: str) -> dict[str, Any]:
        """GET /v4/base/news/permanent/{competitionId}."""
        return await self._client.async_get(
            f"/v4/base/news/permanent/{competition_id}", allow_404=True
        )

    async def get_team_predictions(self, competition_id: str) -> dict[str, Any]:
        """GET /v4/base/predictions/teams/{competitionId} — predicted XI images/timestamps."""
        return await self._client.async_get(
            f"/v4/base/predictions/teams/{competition_id}", allow_404=True
        )

    async def get_item_detail(self, item_id: str) -> dict[str, Any]:
        """GET /v4/base/items/{itemId} — full HTML news article."""
        return await self._client.async_get(
            f"/v4/base/items/{item_id}", allow_404=True
        )
