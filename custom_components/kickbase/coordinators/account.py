"""Global account, config, competitions, and event types coordinator."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from ..api.exceptions import KickbaseAuthError, KickbaseError
from ..api.models import resolve_image_url
from .base import KickbaseBaseCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from ..api import KickbaseApi

_LOGGER = logging.getLogger(__name__)


class AccountCoordinator(KickbaseBaseCoordinator[dict[str, Any]]):
    """Coordinates global Kickbase account, metadata, competitions, and leagues list."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: KickbaseApi,
        update_seconds: int = 3600,
    ) -> None:
        super().__init__(
            hass,
            config_entry,
            api,
            name="kickbase_account",
            update_interval=timedelta(seconds=update_seconds),
            logger=_LOGGER,
        )
        self.event_types_map: dict[int, str] = {}
        self.event_templates: dict[str, str] = {}
        self.competitions_map: dict[str, dict[str, Any]] = {}

    async def _async_setup(self) -> None:
        """One-time startup initialization: login, image base path, competitions, event types."""
        try:
            await self.api.async_login()
            version_info = await self.api.auth.get_config_version()
            if isinstance(version_info, dict) and (ibp := version_info.get("ibp")):
                self.api.client.image_base_url = ibp

            comps_raw = await self.api.competitions.get_competitions()
            for comp in comps_raw.get("it", []) or []:
                cid = str(comp.get("i", ""))
                if cid:
                    self.competitions_map[cid] = {
                        "id": cid,
                        "name": comp.get("n", f"Competition {cid}"),
                        "image": resolve_image_url(comp.get("cpim"), self.api.client.image_base_url),
                        "banner": resolve_image_url(comp.get("fb"), self.api.client.image_base_url),
                    }

            events_raw = await self.api.competitions.get_live_event_types()
            for ev in events_raw.get("it", []) or []:
                ev_id = ev.get("i")
                ev_title = ev.get("ti")
                if ev_id is not None and ev_title:
                    self.event_types_map[int(ev_id)] = str(ev_title)
            if isinstance(events_raw.get("dds"), dict):
                self.event_templates = {
                    str(k): str(v) for k, v in events_raw["dds"].items()
                }
        except KickbaseAuthError as err:
            raise ConfigEntryAuthFailed(f"Kickbase login failed: {err}") from err
        except KickbaseError as err:
            raise UpdateFailed(f"Failed initial Kickbase setup: {err}") from err

    async def _async_fetch_data(self) -> dict[str, Any]:
        """Fetch account profile, user settings, subscription, and league selection."""
        ibp = self.api.client.image_base_url
        me_raw = await self.api.auth.get_me()
        user_obj = me_raw.get("u", me_raw) if isinstance(me_raw, dict) else {}

        selection_raw = await self.api.leagues.get_selection()
        leagues_raw = await self.api.leagues.get_leagues()
        sub_raw = await self.api.auth.get_subscription_status()
        refiner_raw = await self.api.auth.get_refiner_identify()
        config_raw = await self.api.auth.get_config()

        if isinstance(config_raw, dict) and config_raw.get("ibp"):
            self.api.client.image_base_url = config_raw["ibp"]
            ibp = self.api.client.image_base_url

        leagues_by_id: dict[str, dict[str, Any]] = {}
        for item in selection_raw.get("it", []) or []:
            lid = str(item.get("i", ""))
            if not lid:
                continue
            cpi = str(item.get("cpi", "1"))
            comp_info = self.competitions_map.get(cpi, {})
            leagues_by_id[lid] = {
                "id": lid,
                "name": item.get("n", f"Liga {lid}"),
                "competition_id": cpi,
                "competition_name": comp_info.get("name", f"Wettbewerb {cpi}"),
                "budget": item.get("b", 0),
                "team_value": item.get("tv", 0),
                "rank": item.get("pl", 0),
                "user_count": item.get("un", 0),
                "lineup_player_count": item.get("lpc", 0),
                "is_admin": bool(item.get("adm", False)),
                "game_mode": item.get("gpm"),
                "ranking_mode": item.get("rnkm"),
                "image": resolve_image_url(item.get("lim") or item.get("f"), ibp),
                "competition_image": resolve_image_url(item.get("cpim"), ibp) or comp_info.get("image"),
            }

        for item in leagues_raw.get("lins", []) or []:
            lid = str(item.get("i", ""))
            if lid and lid not in leagues_by_id:
                cpi = str(item.get("cpi", "1"))
                comp_info = self.competitions_map.get(cpi, {})
                leagues_by_id[lid] = {
                    "id": lid,
                    "name": item.get("n", f"Liga {lid}"),
                    "competition_id": cpi,
                    "competition_name": comp_info.get("name", f"Wettbewerb {cpi}"),
                    "budget": 0,
                    "team_value": 0,
                    "rank": 0,
                    "user_count": item.get("un", 0),
                    "lineup_player_count": 0,
                    "is_admin": False,
                    "game_mode": item.get("gpm"),
                    "ranking_mode": item.get("rnkm"),
                    "image": resolve_image_url(item.get("lim"), ibp),
                    "competition_image": comp_info.get("image"),
                }

        traits = (
            refiner_raw.get("userTraits", {})
            if isinstance(refiner_raw, dict)
            else {}
        )
        pro_expiry = user_obj.get("proExpiry")
        has_pro = bool(
            traits.get("currentActiveSubscription")
            or (isinstance(pro_expiry, str) and not pro_expiry.startswith("1970-"))
        )

        return {
            "user": {
                "id": str(user_obj.get("id") or user_obj.get("i") or ""),
                "name": user_obj.get("name") or user_obj.get("unm") or "Manager",
                "email": user_obj.get("email") or user_obj.get("vemail") or "",
                "notifications": user_obj.get("notifications", 0),
                "pro_expiry": None if str(pro_expiry or "").startswith("1970-") else pro_expiry,
                "has_pro": has_pro,
                "avatar": resolve_image_url(
                    user_obj.get("profile") or user_obj.get("uim"), ibp
                ),
                "cover": resolve_image_url(user_obj.get("cover"), ibp),
                "flags": user_obj.get("flags", 0),
                "traits": traits,
            },
            "subscription": sub_raw if isinstance(sub_raw, dict) else {},
            "leagues": leagues_by_id,
            "competitions": self.competitions_map,
            "event_types": self.event_types_map,
            "event_templates": self.event_templates,
            "image_base_url": ibp,
            "points_table_url": config_raw.get("pturl") if isinstance(config_raw, dict) else None,
        }
