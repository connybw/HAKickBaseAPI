"""Global optional module coordinators: news/predictions and challenges."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging
import re
from typing import TYPE_CHECKING, Any

from ..api.exceptions import KickbaseError
from ..api.models import normalize_player, parse_iso_datetime, resolve_image_url
from ..storage import asset_photo_key
from .base import KickbaseBaseCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from ..api import KickbaseApi
    from ..storage import KickbaseLocalStore

_LOGGER = logging.getLogger(__name__)
_SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)


class NewsPredictionsCoordinator(KickbaseBaseCoordinator[dict[str, Any]]):
    """Module: news_predictions — Kickbase stage, news per competition, and predicted lineups."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: KickbaseApi,
        competition_ids: list[str],
        update_seconds: int = 1800,
        *,
        store: KickbaseLocalStore | None = None,
        cache_photos: bool = True,
    ) -> None:
        self.competition_ids = competition_ids or ["1"]
        self.store = store
        self._cache_photos = cache_photos
        self._force_sync = False
        super().__init__(
            hass,
            config_entry,
            api,
            name="kickbase_news_predictions",
            update_interval=timedelta(seconds=update_seconds),
            logger=_LOGGER,
        )

    async def async_trigger_sync(self) -> None:
        """Force immediate server sync bypassing startup DB cache."""
        self._force_sync = True
        try:
            await self.async_request_refresh()
        finally:
            self._force_sync = False

    def _is_snapshot_fresh(self, updated_at: str | None) -> bool:
        dt = parse_iso_datetime(updated_at)
        if dt is None or self.update_interval is None:
            return False
        return (datetime.now(UTC) - dt) < self.update_interval

    async def _async_fetch_data(self) -> dict[str, Any]:
        if self.store is not None and self.data is None and not self._force_sync:
            snap, updated_at = await self.store.async_get_snapshot("news_predictions")
            if isinstance(snap, dict) and self._is_snapshot_fresh(updated_at):
                return snap

        ibp = self.api.client.image_base_url
        overview_raw, stage_raw = await asyncio.gather(
            self.api.base_news.get_overview(),
            self.api.base_news.get_stage(),
        )

        news_by_comp: dict[str, list[dict[str, Any]]] = {}
        predictions_by_comp: dict[str, list[dict[str, Any]]] = {}

        for cid in self.competition_ids:
            news_raw, preds_raw = await asyncio.gather(
                self.api.base_news.get_news(cid, start=0, max_items=30),
                self.api.base_news.get_team_predictions(cid),
            )
            news_list = []
            for item in (news_raw.get("it") or []) if isinstance(news_raw, dict) else []:
                news_list.append(
                    {
                        "id": str(item.get("i", "")),
                        "title": item.get("ti", ""),
                        "label": item.get("rl", ""),
                        "type": item.get("t"),
                        "date": item.get("dt"),
                        "description": item.get("d", ""),
                        "image": resolve_image_url(item.get("ci"), ibp),
                    }
                )
            news_by_comp[cid] = news_list

            preds_list = []
            for tm in (preds_raw.get("tms") or []) if isinstance(preds_raw, dict) else []:
                preds_list.append(
                    {
                        "team_id": str(tm.get("tid", "")),
                        "team_name": tm.get("tn", ""),
                        "team_image": resolve_image_url(tm.get("tim"), ibp),
                        "prediction_image": resolve_image_url(tm.get("plpim"), ibp),
                        "updated_at": tm.get("ts"),
                    }
                )
            predictions_by_comp[cid] = preds_list

        stage_items = [
            {
                "id": str(s.get("i", "")),
                "title": s.get("ti", ""),
                "date": s.get("dt"),
                "image": resolve_image_url(s.get("ci"), ibp),
            }
            for s in ((stage_raw.get("stg") or []) if isinstance(stage_raw, dict) else [])
        ]

        sections = []
        for sec in (overview_raw.get("sect") or []) if isinstance(overview_raw, dict) else []:
            sections.append(
                {
                    "id": str(sec.get("i", "")),
                    "title": sec.get("ti", ""),
                    "items": [
                        {
                            "id": str(it.get("i", "")),
                            "title": it.get("ti", ""),
                            "label": it.get("rl", ""),
                            "date": it.get("dt"),
                            "description": it.get("d", ""),
                            "image": resolve_image_url(it.get("ci"), ibp),
                        }
                        for it in (sec.get("it") or [])[:10]
                    ],
                }
            )

        if self.store is not None:
            photo_targets: dict[str, str] = {}
            for s in stage_items:
                if s.get("image"):
                    photo_targets[asset_photo_key("news", s.get("id"), s["image"])] = s["image"]
            for sec in sections:
                for it in sec.get("items") or []:
                    if it.get("image"):
                        photo_targets[asset_photo_key("news", it.get("id"), it["image"])] = it["image"]
            for items in news_by_comp.values():
                for it in items:
                    if it.get("image"):
                        photo_targets[asset_photo_key("news", it.get("id"), it["image"])] = it["image"]
            for cid, preds in predictions_by_comp.items():
                for tm in preds:
                    if tm.get("team_image"):
                        photo_targets[asset_photo_key("team", tm.get("team_id"), tm["team_image"])] = tm["team_image"]
                    if tm.get("prediction_image"):
                        pk = asset_photo_key("pred", f"{cid}_{tm.get('team_id')}", tm["prediction_image"])
                        photo_targets[pk] = tm["prediction_image"]

            cached_map, _ = await self.store.async_cache_image_urls(
                self.api.client, photo_targets, enabled=self._cache_photos
            )

            for s in stage_items:
                if loc := cached_map.get(asset_photo_key("news", s.get("id"), s.get("image"))):
                    s["local_image"] = loc
                    s["image"] = loc
            for sec in sections:
                for it in sec.get("items") or []:
                    if loc := cached_map.get(asset_photo_key("news", it.get("id"), it.get("image"))):
                        it["local_image"] = loc
                        it["image"] = loc
            for items in news_by_comp.values():
                for it in items:
                    if loc := cached_map.get(asset_photo_key("news", it.get("id"), it.get("image"))):
                        it["local_image"] = loc
                        it["image"] = loc
            for cid, preds in predictions_by_comp.items():
                for tm in preds:
                    if loc := cached_map.get(asset_photo_key("team", tm.get("team_id"), tm.get("team_image"))):
                        tm["local_team_image"] = loc
                        tm["team_image"] = loc
                    pk = asset_photo_key("pred", f"{cid}_{tm.get('team_id')}", tm.get("prediction_image"))
                    if loc := cached_map.get(pk):
                        tm["local_prediction_image"] = loc
                        tm["prediction_image"] = loc

        primary_cid = self.competition_ids[0]
        primary_news = news_by_comp.get(primary_cid, [])
        payload = {
            "stage": stage_items,
            "sections": sections,
            "news_by_competition": news_by_comp,
            "predictions_by_competition": predictions_by_comp,
            "latest_headline": primary_news[0]["title"] if primary_news else None,
        }

        if self.store is not None:
            snap_batch: dict[str, dict[str, Any]] = {"news_predictions": payload}
            # Pre-cache recent full news articles missing from SQLite so GUI reads 100% locally
            seen_news_ids: list[dict[str, Any]] = []
            seen_set: set[str] = set()
            for it in primary_news[:12]:
                nid = it.get("id")
                if nid and nid not in seen_set:
                    seen_set.add(nid)
                    seen_news_ids.append(it)
            for it in seen_news_ids:
                nid = it["id"]
                existing, _ = await self.store.async_get_snapshot(f"news_item:{nid}")
                if existing is not None:
                    continue
                try:
                    raw = await self.api.base_news.get_item_detail(nid)
                except KickbaseError:
                    continue
                if isinstance(raw, dict):
                    html_content = raw.get("cnt", "") or ""
                    safe_html = _SCRIPT_TAG_RE.sub("", html_content)
                    remote_ci = resolve_image_url(raw.get("ci"), ibp)
                    loc_ci = it.get("local_image")
                    if not loc_ci and remote_ci and self._cache_photos:
                        c_map, _ = await self.store.async_cache_image_urls(
                            self.api.client,
                            {asset_photo_key("news", nid, remote_ci): remote_ci},
                            enabled=True,
                        )
                        loc_ci = c_map.get(asset_photo_key("news", nid, remote_ci))
                    snap_batch[f"news_item:{nid}"] = {
                        "from_local_db": True,
                        "id": nid,
                        "title": raw.get("ti") or it.get("title", ""),
                        "label": raw.get("rl") or it.get("label", ""),
                        "date": raw.get("dt") or it.get("date"),
                        "image": loc_ci or it.get("image"),
                        "local_image": loc_ci or it.get("local_image"),
                        "html": safe_html,
                    }
            await self.store.async_save_snapshots_batch(snap_batch)

        return payload


class ChallengesCoordinator(KickbaseBaseCoordinator[dict[str, Any]]):
    """Module: challenges — Challenges lobby, division ladder, skill points & active challenges."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: KickbaseApi,
        update_seconds: int = 900,
        *,
        store: KickbaseLocalStore | None = None,
        cache_photos: bool = True,
    ) -> None:
        self.store = store
        self._cache_photos = cache_photos
        self._force_sync = False
        super().__init__(
            hass,
            config_entry,
            api,
            name="kickbase_challenges",
            update_interval=timedelta(seconds=update_seconds),
            logger=_LOGGER,
        )

    async def async_trigger_sync(self) -> None:
        """Force immediate server sync bypassing startup DB cache."""
        self._force_sync = True
        try:
            await self.async_request_refresh()
        finally:
            self._force_sync = False

    def _is_snapshot_fresh(self, updated_at: str | None) -> bool:
        dt = parse_iso_datetime(updated_at)
        if dt is None or self.update_interval is None:
            return False
        return (datetime.now(UTC) - dt) < self.update_interval

    async def _async_fetch_data(self) -> dict[str, Any]:
        if self.store is not None and self.data is None and not self._force_sync:
            snap, updated_at = await self.store.async_get_snapshot("challenges")
            if isinstance(snap, dict) and self._is_snapshot_fresh(updated_at):
                return snap

        ibp = self.api.client.image_base_url
        lobby_ov, lobby_live, lobby_prof, ladder, skill_summary, selection = await asyncio.gather(
            self.api.challenges.get_lobby_overview(),
            self.api.challenges.get_lobby_live(),
            self.api.challenges.get_lobby_profile(),
            self.api.challenges.get_division_ladder(),
            self.api.challenges.get_skill_points_summary(),
            self.api.challenges.get_selection(),
        )

        active_challenges: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for src in (
            (lobby_ov.get("my") if isinstance(lobby_ov, dict) else None) or [],
            (lobby_live.get("it") if isinstance(lobby_live, dict) else None) or [],
            (selection.get("it") if isinstance(selection, dict) else None) or [],
        ):
            for ch in src:
                cid = str(ch.get("ch", ""))
                if not cid or cid in seen_ids:
                    continue
                seen_ids.add(cid)
                active_challenges.append(
                    {
                        "id": cid,
                        "name": ch.get("n") or f"Challenge #{cid}",
                        "competition_id": str(ch.get("cpi", "1")),
                        "type": ch.get("cht"),
                        "budget": ch.get("b", 0),
                        "start_date": ch.get("sd"),
                        "is_live": bool(ch.get("il", False)),
                        "color": ch.get("col"),
                        "user_count": ch.get("uc", 0),
                        "lineup_player_count": ch.get("lpc", 0),
                        "confirmed_player_count": ch.get("clpc", 0),
                        "image": resolve_image_url(ch.get("chim") or ch.get("f"), ibp),
                    }
                )

        # Fetch lineup overview + livepitch + table + top10 for up to 3 active challenges
        challenge_details: dict[str, dict[str, Any]] = {}
        challenge_detail_snapshots: dict[str, dict[str, Any]] = {}
        for ch in active_challenges[:3]:
            cid = ch["id"]
            prof, lineup_ov, livepitch, table, top10 = await asyncio.gather(
                self.api.challenges.get_challenge_profile(cid),
                self.api.challenges.get_challenge_lineup_overview(cid),
                self.api.challenges.get_challenge_livepitch(cid),
                self.api.challenges.get_challenge_table(cid),
                self.api.challenges.get_challenge_top10(cid),
            )
            lp_source = (
                (livepitch.get("lp") if isinstance(livepitch, dict) and livepitch.get("lp") else None)
                or (lineup_ov.get("lp") if isinstance(lineup_ov, dict) else [])
                or []
            )
            norm_lp = [normalize_player(p, ibp) for p in lp_source]
            live_pts = livepitch.get("p", 0) if isinstance(livepitch, dict) else 0
            challenge_details[cid] = {
                "profile": prof if isinstance(prof, dict) else {},
                "formation": lineup_ov.get("t") if isinstance(lineup_ov, dict) else None,
                "lock_at": lineup_ov.get("lis") if isinstance(lineup_ov, dict) else None,
                "live_points": live_pts,
                "lineup": norm_lp,
            }
            challenge_detail_snapshots[f"challenge_detail:{cid}"] = {
                "from_local_db": True,
                "id": cid,
                "profile": prof if isinstance(prof, dict) else {},
                "table": table if isinstance(table, dict) else {},
                "top10": top10 if isinstance(top10, dict) else {},
                "live_points": live_pts,
                "lineup": norm_lp,
            }

        dv_info = lobby_prof.get("dv", {}) if isinstance(lobby_prof, dict) else {}
        divisions = [
            {
                "id": str(d.get("dvi", "")),
                "name": d.get("dvn"),
                "image": resolve_image_url(d.get("dvim"), ibp),
                "border_points": d.get("bod", 0),
                "user_count": d.get("uc", 0),
            }
            for d in ((ladder.get("dvs") or []) if isinstance(ladder, dict) else [])
        ]

        profile_payload = {
            "season_name": lobby_prof.get("n") if isinstance(lobby_prof, dict) else None,
            "division_id": str(dv_info.get("dvi", "")),
            "division_name": dv_info.get("dvn") or dv_info.get("hdvn"),
            "division_image": resolve_image_url(dv_info.get("dvim"), ibp),
            "skill_points": lobby_prof.get("skp", 0) if isinstance(lobby_prof, dict) else 0,
            "available_skill_points": lobby_prof.get("avskp", 0) if isinstance(lobby_prof, dict) else 0,
            "average_points": lobby_prof.get("ap", 0) if isinstance(lobby_prof, dict) else 0,
            "challenge_count": lobby_prof.get("chc", len(active_challenges))
            if isinstance(lobby_prof, dict)
            else len(active_challenges),
        }

        if self.store is not None:
            photo_targets: dict[str, str] = {}
            for ch in active_challenges:
                if ch.get("image"):
                    photo_targets[asset_photo_key("challenge", ch.get("id"), ch["image"])] = ch["image"]
            for dv in divisions:
                if dv.get("image"):
                    photo_targets[asset_photo_key("division", dv.get("id"), dv["image"])] = dv["image"]
            if profile_payload.get("division_image"):
                photo_targets[
                    asset_photo_key("division", profile_payload.get("division_id"), profile_payload["division_image"])
                ] = profile_payload["division_image"]
            for det in challenge_details.values():
                for pl in det.get("lineup") or []:
                    if pl.get("image"):
                        photo_targets[asset_photo_key("player", pl.get("id"), pl["image"])] = pl["image"]
                    if pl.get("team_image"):
                        photo_targets[asset_photo_key("team", pl.get("team_id"), pl["team_image"])] = pl["team_image"]

            cached_map, _ = await self.store.async_cache_image_urls(
                self.api.client, photo_targets, enabled=self._cache_photos
            )

            for ch in active_challenges:
                if loc := cached_map.get(asset_photo_key("challenge", ch.get("id"), ch.get("image"))):
                    ch["local_image"] = loc
                    ch["image"] = loc
            for dv in divisions:
                if loc := cached_map.get(asset_photo_key("division", dv.get("id"), dv.get("image"))):
                    dv["local_image"] = loc
                    dv["image"] = loc
            if loc := cached_map.get(
                asset_photo_key("division", profile_payload.get("division_id"), profile_payload.get("division_image"))
            ):
                profile_payload["local_division_image"] = loc
                profile_payload["division_image"] = loc
            for det in challenge_details.values():
                for pl in det.get("lineup") or []:
                    if loc := cached_map.get(asset_photo_key("player", pl.get("id"), pl.get("image"))):
                        pl["local_image"] = loc
                    if loc := cached_map.get(asset_photo_key("team", pl.get("team_id"), pl.get("team_image"))):
                        pl["local_team_image"] = loc

        payload = {
            "profile": profile_payload,
            "divisions": divisions,
            "active_challenges": active_challenges,
            "challenge_details": challenge_details,
            "skill_history": (skill_summary.get("chs") or []) if isinstance(skill_summary, dict) else [],
        }
        if self.store is not None:
            challenge_detail_snapshots["challenges"] = payload
            await self.store.async_save_snapshots_batch(challenge_detail_snapshots)

        return payload
