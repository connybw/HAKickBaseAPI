"""Endpoint modules package."""

from .auth import AuthEndpoints
from .base_news import BaseNewsEndpoints
from .challenges import ChallengeEndpoints
from .competitions import CompetitionEndpoints
from .leagues import LeagueEndpoints
from .managers import ManagerEndpoints
from .market import MarketEndpoints
from .squad import SquadEndpoints

__all__ = [
    "AuthEndpoints",
    "BaseNewsEndpoints",
    "ChallengeEndpoints",
    "CompetitionEndpoints",
    "LeagueEndpoints",
    "ManagerEndpoints",
    "MarketEndpoints",
    "SquadEndpoints",
]
