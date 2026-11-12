"""Modular Kickbase API v4 client facade."""

from __future__ import annotations

import aiohttp

from ..const import API_BASE_URL
from .client import KickbaseApiClient
from .endpoints import (
    AuthEndpoints,
    BaseNewsEndpoints,
    ChallengeEndpoints,
    CompetitionEndpoints,
    LeagueEndpoints,
    ManagerEndpoints,
    MarketEndpoints,
    SquadEndpoints,
)
from .exceptions import (
    KickbaseAuthError,
    KickbaseConnectionError,
    KickbaseError,
    KickbaseNotFoundError,
    KickbaseRateLimitError,
)


class KickbaseApi:
    """High-level modular API facade exposing domain-specific endpoint groups."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        *,
        base_url: str = API_BASE_URL,
    ) -> None:
        self.client = KickbaseApiClient(
            session=session,
            email=email,
            password=password,
            base_url=base_url,
        )
        self.auth = AuthEndpoints(self.client)
        self.leagues = LeagueEndpoints(self.client)
        self.squad = SquadEndpoints(self.client)
        self.market = MarketEndpoints(self.client)
        self.managers = ManagerEndpoints(self.client)
        self.competitions = CompetitionEndpoints(self.client)
        self.base_news = BaseNewsEndpoints(self.client)
        self.challenges = ChallengeEndpoints(self.client)

    async def async_login(self, force: bool = False):
        """Authenticate and load initial image base path if available."""
        return await self.client.async_login(force=force)


__all__ = [
    "KickbaseApi",
    "KickbaseApiClient",
    "KickbaseAuthError",
    "KickbaseConnectionError",
    "KickbaseError",
    "KickbaseNotFoundError",
    "KickbaseRateLimitError",
]
