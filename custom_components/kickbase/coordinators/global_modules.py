"""Global optional module coordinators: news/predictions and challenges."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from ..api.models import normalize_player, resolve_image_url
from .base import KickbaseBaseCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from ..api import KickbaseApi

_LOGGER = logging.getLogger(__name__)


class NewsPredictionsCoordinator(KickbaseBaseCoordinator[dict[str, Any]]):
    """Module: news_predictions — Kickbase stage, news per competition, and predicted lineups."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: KickbaseApi,
        competition_ids: list[str],
        update_seconds: int = 1800,
    ) -> None:
        self.competition_ids = competition_ids or ["1"]
        super().__init__(
            hass,
            config_entry,
            api,
            name="kickbase_news_predictions",
            update_interval=timedelta(seconds=update_seconds),
            logger=_LOGGER,
        )

    async def _async_fetch_data(self) -> dict[str, Any]:
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

        primary_cid = self.competition_ids[0]
        primary_news = news_by_comp.get(primary_cid, [])
        return {
            "stage": stage_items,
            "sections": sections,
            "news_by_competition": news_by_comp,
            "predictions_by_competition": predictions_by_comp,
            "latest_headline": primary_news[0]["title"] if primary_news else None,
        }


class ChallengesCoordinator(KickbaseBaseCoordinator[dict[str, Any]]):
    """Module: challenges — Challenges lobby, division ladder, skill points & active challenges."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: KickbaseApi,
        update_seconds: int = 900,
    ) -> None:
        super().__init__(
            hass,
            config_entry,
            api,
            name="kickbase_challenges",
            update_interval=timedelta(seconds=update_seconds),
            logger=_LOGGER,
        )

    async def _async_fetch_data(self) -> dict[str, Any]:
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

        # Fetch lineup overview + livepitch for up to 3 active challenges
        challenge_details: dict[str, dict[str, Any]] = {}
        for ch in active_challenges[:3]:
            cid = ch["id"]
            prof, lineup_ov, livepitch = await asyncio.gather(
                self.api.challenges.get_challenge_profile(cid),
                self.api.challenges.get_challenge_lineup_overview(cid),
                self.api.challenges.get_challenge_livepitch(cid),
            )
            lp_source = (
                (livepitch.get("lp") if isinstance(livepitch, dict) and livepitch.get("lp") else None)
                or (lineup_ov.get("lp") if isinstance(lineup_ov, dict) else [])
                or []
            )
            challenge_details[cid] = {
                "profile": prof if isinstance(prof, dict) else {},
                "formation": lineup_ov.get("t") if isinstance(lineup_ov, dict) else None,
                "lock_at": lineup_ov.get("lis") if isinstance(lineup_ov, dict) else None,
                "live_points": livepitch.get("p", 0) if isinstance(livepitch, dict) else 0,
                "lineup": [normalize_player(p, ibp) for p in lp_source],
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

        return {
            "profile": {
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
            },
            "divisions": divisions,
            "active_challenges": active_challenges,
            "challenge_details": challenge_details,
            "skill_history": (skill_summary.get("chs") or []) if isinstance(skill_summary, dict) else [],
        }
