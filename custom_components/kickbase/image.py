"""Image platform for Kickbase user avatar and league badges."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import MODULE_LEAGUE_OVERVIEW
from .entity import build_account_device_info, build_league_device_info

if TYPE_CHECKING:
    from . import KickbaseConfigEntry
    from .coordinators import KickbaseRuntimeData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KickbaseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kickbase image entities."""
    runtime: KickbaseRuntimeData = entry.runtime_data
    account_data = runtime.account.data or {}
    user_info = account_data.get("user") or {}
    user_id = str(user_info.get("id") or entry.entry_id)
    user_name = str(user_info.get("name") or "Manager")

    entities: list[ImageEntity] = []

    if user_info.get("avatar"):
        entities.append(
            KickbaseUrlImageEntity(
                hass=hass,
                coordinator=runtime.account,
                unique_id=f"{entry.entry_id}_user_avatar",
                name="Profilbild",
                image_url_fn=lambda d: (d.get("user") or {}).get("avatar"),
                device_info=build_account_device_info(user_id, user_name),
            )
        )

    for lid, lset in runtime.leagues.items():
        league_info = (account_data.get("leagues") or {}).get(lid, {})
        if league_info.get("image"):
            entities.append(
                KickbaseUrlImageEntity(
                    hass=hass,
                    coordinator=lset.sync or runtime.account,
                    unique_id=f"{entry.entry_id}_{lid}_league_logo",
                    name="Liga-Logo",
                    image_url_fn=lambda d, lid=lid, fallback=league_info.get("image"): (
                        ((d.get(MODULE_LEAGUE_OVERVIEW) or {}).get("league") or {}).get("image")
                        or ((d.get("league") or {}).get("image") if "league" in d else None)
                        or ((d.get("leagues") or {}).get(lid) or {}).get("image")
                        or fallback
                    ),
                    device_info=build_league_device_info(
                        lid, lset.league_name, league_info.get("competition_name")
                    ),
                )
            )

    async_add_entities(entities)


class KickbaseUrlImageEntity(CoordinatorEntity, ImageEntity):
    """Image entity backed by a Kickbase CDN URL."""

    _attr_has_entity_name = True

    def __init__(
        self,
        *,
        hass: HomeAssistant,
        coordinator: Any,
        unique_id: str,
        name: str,
        image_url_fn: Any,
        device_info: Any,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        self._image_url_fn = image_url_fn
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._attr_device_info = device_info
        self._attr_image_last_updated = datetime.now(UTC)
        self._last_url: str | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        new_url = self.image_url
        if new_url != self._last_url:
            self._last_url = new_url
            self._attr_image_last_updated = datetime.now(UTC)
        super()._handle_coordinator_update()

    @property
    def image_url(self) -> str | None:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        return self._image_url_fn(data)
