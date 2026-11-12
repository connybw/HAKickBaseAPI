"""Exceptions for the Kickbase API client."""

from __future__ import annotations


class KickbaseError(Exception):
    """Base exception for Kickbase API errors."""


class KickbaseAuthError(KickbaseError):
    """Authentication or authorization failure."""


class KickbaseRateLimitError(KickbaseError):
    """HTTP 429 rate limit exceeded."""


class KickbaseConnectionError(KickbaseError):
    """Network or server communication failure."""


class KickbaseNotFoundError(KickbaseError):
    """Requested resource does not exist (404)."""
