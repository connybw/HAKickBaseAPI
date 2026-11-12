"""Runtime data registry and on-demand caching for Kickbase coordinators."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Awaitable, Callable

from ..api import KickbaseApi
from ..const import ALL_MODULES
from .account import AccountCoordinator
from .global_modules import ChallengesCoordinator, NewsPredictionsCoordinator
from .league import (
    FeedAchievementsCoordinator,
    LeagueOverviewCoordinator,
    LiveMatchdayCoordinator,
    MarketTransfersCoordinator,
    SquadLineupCoordinator,
)


class OnDemandCache:
    """Short-lived TTL cache for on-demand deep-dive API queries from cards/panel."""

    def __init__(self, default_ttl: int = 300) -> None:
        self._default_ttl = default_ttl
        self._store: dict[str, tuple[float, Any]] = {}

    async def get_or_fetch(
        self,
        key: str,
        fetcher: Callable[[], Awaitable[Any]],
        *,
        ttl: int | None = None,
        force: bool = False,
    ) -> Any:
        now = time.monotonic()
        effective_ttl = ttl if ttl is not None else self._default_ttl
        if not force and key in self._store:
            expires_at, value = self._store[key]
            if now < expires_at:
                return value
        value = await fetcher()
        self._store[key] = (now + effective_ttl, value)
        return value

    def clear(self) -> None:
        """Clear all cached items."""
        self._store.clear()


@dataclass
class LeagueCoordinatorSet:
    """Modular coordinators belonging to a single Kickbase league."""

    league_id: str
    league_name: str
    competition_id: str
    overview: LeagueOverviewCoordinator | None = None
    squad_lineup: SquadLineupCoordinator | None = None
    market_transfers: MarketTransfersCoordinator | None = None
    live_matchday: LiveMatchdayCoordinator | None = None
    feed_achievements: FeedAchievementsCoordinator | None = None

    def active_coordinators(self) -> list[Any]:
        """Return list of instantiated coordinators for this league."""
        return [
            c
            for c in (
                self.overview,
                self.squad_lineup,
                self.market_transfers,
                self.live_matchday,
                self.feed_achievements,
            )
            if c is not None
        ]


@dataclass
class KickbaseRuntimeData:
    """Top-level runtime data stored on `ConfigEntry.runtime_data`."""

    api: KickbaseApi
    account: AccountCoordinator
    enabled_modules: set[str]
    league_ids: list[str]
    primary_league_id: str
    market_value_timeframe: int
    leagues: dict[str, LeagueCoordinatorSet] = field(default_factory=dict)
    news_predictions: NewsPredictionsCoordinator | None = None
    challenges: ChallengesCoordinator | None = None
    cache: OnDemandCache = field(default_factory=OnDemandCache)

    def all_coordinators(self) -> list[Any]:
        """Return every active coordinator across account, leagues, and global modules."""
        items: list[Any] = [self.account]
        for lset in self.leagues.values():
            items.extend(lset.active_coordinators())
        if self.news_predictions is not None:
            items.append(self.news_predictions)
        if self.challenges is not None:
            items.append(self.challenges)
        return items

    def is_module_enabled(self, module: str) -> bool:
        """Check whether a module is enabled."""
        return module in ALL_MODULES and module in self.enabled_modules
