"""Base coordinator helpers for Kickbase."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ..api.exceptions import KickbaseAuthError, KickbaseError

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from ..api import KickbaseApi

T = TypeVar("T")


class KickbaseBaseCoordinator(DataUpdateCoordinator[T], Generic[T]):
    """Shared DataUpdateCoordinator base with standardized auth & error handling."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: KickbaseApi,
        *,
        name: str,
        update_interval: timedelta,
        logger: logging.Logger,
    ) -> None:
        self.api = api
        super().__init__(
            hass,
            logger,
            config_entry=config_entry,
            name=name,
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> T:
        """Execute subclass update with standardized auth/network error wrapping."""
        try:
            return await self._async_fetch_data()
        except KickbaseAuthError as err:
            raise ConfigEntryAuthFailed(f"Kickbase authentication failed: {err}") from err
        except KickbaseError as err:
            raise UpdateFailed(f"Kickbase API error ({self.name}): {err}") from err

    async def _async_fetch_data(self) -> T:
        """Fetch and normalize module data (implemented by subclasses)."""
        raise NotImplementedError
