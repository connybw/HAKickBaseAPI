"""Modular per-league DataUpdateCoordinators for Kickbase."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from ..api.models import (
    decode_activity_type,
    decode_match_status,
    normalize_player,
    resolve_image_url,
)
from ..const import (
    EVENT_LIVE_PLAYER_EVENT,
    EVENT_NEGATIVE_BUDGET,
    EVENT_NEW_ACTIVITY,
    EVENT_SCOUTED_ON_MARKET,
    LIVE_MATCHDAY_ACTIVE_INTERVAL,
)
from .base import KickbaseBaseCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from ..api import KickbaseApi

_LOGGER = logging.getLogger(__name__)


class LeagueOverviewCoordinator(KickbaseBaseCoordinator[dict[str, Any]]):
    """Module: league_overview — Standings, budget, battles, and league metadata."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: KickbaseApi,
        league_id: str,
        user_id: str,
        update_seconds: int = 300,
    ) -> None:
        self.league_id = league_id
        self.user_id = user_id
        self._was_negative: bool | None = None
        super().__init__(
            hass,
            config_entry,
            api,
            name=f"kickbase_league_{league_id}_overview",
            update_interval=timedelta(seconds=update_seconds),
            logger=_LOGGER,
        )

    async def _async_fetch_data(self) -> dict[str, Any]:
        ibp = self.api.client.image_base_url
        overview_raw, me_raw, budget_raw, ranking_raw, settings_raw = await asyncio.gather(
            self.api.leagues.get_overview(self.league_id, include_managers_and_battles=True),
            self.api.leagues.get_me(self.league_id),
            self.api.leagues.get_my_budget(self.league_id),
            self.api.leagues.get_ranking(self.league_id),
            self.api.leagues.get_settings(self.league_id),
        )

        budget = budget_raw.get("b", me_raw.get("b", 0))
        max_bid = budget_raw.get("pbas", budget)
        is_negative = budget < 0
        if self._was_negative is False and is_negative:
            self.hass.bus.async_fire(
                EVENT_NEGATIVE_BUDGET,
                {
                    "league_id": self.league_id,
                    "league_name": overview_raw.get("lnm") or me_raw.get("lnm"),
                    "budget": budget,
                    "max_bid": max_bid,
                },
            )
        self._was_negative = is_negative

        managers_list: list[dict[str, Any]] = []
        my_standing: dict[str, Any] = {}
        for user in ranking_raw.get("us", []) or []:
            uid = str(user.get("i", ""))
            entry = {
                "id": uid,
                "name": user.get("n", "Manager"),
                "is_admin": bool(user.get("adm", False)),
                "season_points": user.get("sp", 0),
                "matchday_points": user.get("mdp", 0),
                "team_value": user.get("tv", 0),
                "rank": user.get("spl", 0),
                "matchday_rank": user.get("mdpl", 0),
                "points_avg": user.get("shp", 0),
                "lineup_ids": [pid for pid in (user.get("lp") or []) if pid is not None],
                "points_active": bool(user.get("pa", False)),
                "avatar": resolve_image_url(user.get("uim"), ibp),
                "is_me": uid == self.user_id,
            }
            managers_list.append(entry)
            if uid == self.user_id:
                my_standing = entry

        managers_list.sort(key=lambda m: (m["rank"] or 9999, -m["season_points"]))

        battles = []
        for battle in overview_raw.get("btls", []) or []:
            leader = battle.get("u") or {}
            battles.append(
                {
                    "type": battle.get("t"),
                    "name": battle.get("n"),
                    "description": battle.get("d"),
                    "leader_id": str(leader.get("i", "")),
                    "leader_name": leader.get("n"),
                    "leader_avatar": resolve_image_url(leader.get("uim"), ibp),
                }
            )

        team_player_counts = [
            {
                "team_id": str(item.get("tid", "")),
                "count": item.get("npt", 0),
                "image": resolve_image_url(item.get("tim"), ibp),
            }
            for item in (me_raw.get("tpc") or [])
        ]

        return {
            "league": {
                "id": self.league_id,
                "name": overview_raw.get("lnm") or me_raw.get("lnm") or f"Liga {self.league_id}",
                "competition_id": str(overview_raw.get("cpi") or me_raw.get("cpi") or ranking_raw.get("cpi") or "1"),
                "competition_name": overview_raw.get("cpn", "Bundesliga"),
                "image": resolve_image_url(overview_raw.get("lim") or me_raw.get("lim"), ibp),
                "manager_count": overview_raw.get("mgc") or len(managers_list),
                "max_managers": overview_raw.get("mgm"),
                "max_players_per_user": overview_raw.get("mppu") or me_raw.get("mppu"),
                "max_players_same_team": overview_raw.get("mpst") or me_raw.get("mpst"),
                "game_mode": overview_raw.get("gpm") or me_raw.get("gpm"),
                "ranking_mode": overview_raw.get("rnkm") or me_raw.get("rnkm"),
                "season": ranking_raw.get("sn"),
                "matchday": ranking_raw.get("day"),
                "total_matchdays": ranking_raw.get("nd"),
                "is_live": bool(ranking_raw.get("il", False)),
                "description": settings_raw.get("d", "") if isinstance(settings_raw, dict) else "",
                "is_admin": bool(overview_raw.get("adm") or me_raw.get("adm")),
            },
            "me": {
                "budget": budget,
                "max_bid": max_bid,
                "budget_scale": budget_raw.get("bs", me_raw.get("bs", 1)),
                "is_negative_budget": is_negative,
                "rank": my_standing.get("rank", 0),
                "matchday_rank": my_standing.get("matchday_rank", 0),
                "season_points": my_standing.get("season_points", 0),
                "matchday_points": my_standing.get("matchday_points", 0),
                "team_value": my_standing.get("team_value", 0),
                "team_player_counts": team_player_counts,
            },
            "standings": managers_list,
            "battles": battles,
        }


class SquadLineupCoordinator(KickbaseBaseCoordinator[dict[str, Any]]):
    """Module: squad_lineup — Full owned squad, starting 11, formation, lock countdown."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: KickbaseApi,
        league_id: str,
        update_seconds: int = 300,
    ) -> None:
        self.league_id = league_id
        super().__init__(
            hass,
            config_entry,
            api,
            name=f"kickbase_league_{league_id}_squad",
            update_interval=timedelta(seconds=update_seconds),
            logger=_LOGGER,
        )

    async def _async_fetch_data(self) -> dict[str, Any]:
        ibp = self.api.client.image_base_url
        squad_raw, lineup_ov_raw, teams_raw, myeleven_raw = await asyncio.gather(
            self.api.squad.get_squad(self.league_id),
            self.api.squad.get_lineup_overview(self.league_id),
            self.api.squad.get_lineup_teams(self.league_id),
            self.api.squad.get_my_eleven(self.league_id),
        )

        team_images: dict[str, str] = {}
        for tm in (teams_raw.get("tms") or []) if isinstance(teams_raw, dict) else []:
            tid = str(tm.get("tid", ""))
            if tid and tm.get("tim"):
                if url := resolve_image_url(tm["tim"], ibp):
                    team_images[tid] = url

        myeleven_by_id: dict[str, dict[str, Any]] = {}
        for p in (myeleven_raw.get("lp") or []) if isinstance(myeleven_raw, dict) else []:
            pid = str(p.get("i", ""))
            if pid:
                myeleven_by_id[pid] = p

        lineup_by_id: dict[str, dict[str, Any]] = {}
        lineup_players: list[dict[str, Any]] = []
        for raw_p in (lineup_ov_raw.get("lp") or []) if isinstance(lineup_ov_raw, dict) else []:
            norm = normalize_player(raw_p, ibp)
            tid = norm.get("team_id")
            if tid and tid in team_images:
                norm["team_image"] = team_images[tid]
            if norm["id"] in myeleven_by_id:
                m_info = myeleven_by_id[norm["id"]]
                norm["match_date"] = norm["match_date"] or m_info.get("md")
                norm["match_id"] = norm["match_id"] or (
                    str(m_info["mi"]) if m_info.get("mi") is not None else None
                )
                if not norm.get("opponent") and m_info.get("ot"):
                    norm["opponent"] = {
                        "id": str(m_info["ot"].get("i", "")),
                        "image": resolve_image_url(m_info["ot"].get("tim"), ibp),
                    }
            lineup_players.append(norm)
            lineup_by_id[norm["id"]] = norm

        squad_players: list[dict[str, Any]] = []
        total_mv = 0
        total_24h = 0
        total_season_diff = 0
        total_profit = 0
        rising_count = 0
        falling_count = 0
        injured_or_suspended_count = 0
        avg_points_sum = 0.0

        for raw_p in (squad_raw.get("it") or []) if isinstance(squad_raw, dict) else []:
            norm = normalize_player(raw_p, ibp)
            tid = norm.get("team_id")
            if tid and tid in team_images:
                norm["team_image"] = team_images[tid]
            # Check lineup_overview membership (`lo` / `lp`)
            if norm["id"] in lineup_by_id:
                lp_entry = lineup_by_id[norm["id"]]
                norm["is_captain"] = lp_entry.get("is_captain", False)
                norm["home_team_image"] = lp_entry.get("home_team_image")
                norm["away_team_image"] = lp_entry.get("away_team_image")
                norm["in_starting_eleven"] = (lp_entry.get("matchday_status", 0) != 8)
            else:
                norm["in_starting_eleven"] = False

            mv = norm.get("market_value") or 0
            chg_24h = norm.get("market_value_24h_change") or 0
            total_mv += mv
            total_24h += chg_24h
            total_season_diff += norm.get("market_value_season_diff") or 0
            total_profit += norm.get("market_value_since_buy") or 0
            avg_points_sum += float(norm.get("average_points") or 0)

            if norm["market_value_trend"] == "rising" or chg_24h > 0:
                rising_count += 1
            elif norm["market_value_trend"] == "falling" or chg_24h < 0:
                falling_count += 1

            if norm["status"]["severity"] in ("danger", "warning"):
                injured_or_suspended_count += 1

            squad_players.append(norm)

        squad_players.sort(key=lambda p: (p.get("position_code") or 9, -(p.get("market_value") or 0)))

        lineup_issues = [
            p
            for p in lineup_players
            if p["status"]["severity"] == "danger" or p.get("matchday_status") == 8
        ]
        captain = next((p for p in lineup_players if p.get("is_captain")), None)

        return {
            "squad": squad_players,
            "summary": {
                "count": len(squad_players),
                "total_market_value": total_mv,
                "total_24h_change": total_24h,
                "total_season_diff": total_season_diff,
                "total_profit_loss": total_profit,
                "average_player_points": round(avg_points_sum / len(squad_players), 1)
                if squad_players
                else 0.0,
                "rising_count": rising_count,
                "falling_count": falling_count,
                "injured_or_suspended_count": injured_or_suspended_count,
            },
            "lineup": {
                "formation": lineup_ov_raw.get("t", "4-4-2") if isinstance(lineup_ov_raw, dict) else "4-4-2",
                "matchday": lineup_ov_raw.get("mdln") if isinstance(lineup_ov_raw, dict) else None,
                "lock_at": lineup_ov_raw.get("lis") if isinstance(lineup_ov_raw, dict) else None,
                "player_count": lineup_ov_raw.get("lpc", len(lineup_players))
                if isinstance(lineup_ov_raw, dict)
                else len(lineup_players),
                "confirmed_count": lineup_ov_raw.get("clpc", 0)
                if isinstance(lineup_ov_raw, dict)
                else 0,
                "has_captain": bool(lineup_ov_raw.get("cpte", False))
                if isinstance(lineup_ov_raw, dict)
                else False,
                "captain_name": captain["name"] if captain else None,
                "captain_id": captain["id"] if captain else None,
                "players": lineup_players,
                "issue_count": len(lineup_issues),
                "issues": [p["name"] for p in lineup_issues],
            },
            "team_images": team_images,
        }


class MarketTransfersCoordinator(KickbaseBaseCoordinator[dict[str, Any]]):
    """Module: market_transfers — Transfer market listings & scouted player watchlist."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: KickbaseApi,
        league_id: str,
        update_seconds: int = 180,
    ) -> None:
        self.league_id = league_id
        self._known_scouted_on_market: set[str] | None = None
        super().__init__(
            hass,
            config_entry,
            api,
            name=f"kickbase_league_{league_id}_market",
            update_interval=timedelta(seconds=update_seconds),
            logger=_LOGGER,
        )

    async def _async_fetch_data(self) -> dict[str, Any]:
        ibp = self.api.client.image_base_url
        market_raw, scouted_raw = await asyncio.gather(
            self.api.market.get_market(self.league_id),
            self.api.market.get_scouted_players(self.league_id),
        )

        scouted_players: list[dict[str, Any]] = []
        scouted_ids: set[str] = set()
        if isinstance(scouted_raw, dict):
            for raw_p in scouted_raw.get("it") or scouted_raw.get("sps") or []:
                norm = normalize_player(raw_p, ibp)
                if norm["id"]:
                    scouted_ids.add(norm["id"])
                    scouted_players.append(norm)

        market_players: list[dict[str, Any]] = []
        expiring_soon_count = 0
        scouted_matches: list[dict[str, Any]] = []

        if isinstance(market_raw, dict):
            for raw_p in market_raw.get("it") or []:
                norm = normalize_player(raw_p, ibp)
                exs = norm.get("expiry_seconds")
                if isinstance(exs, (int, float)) and exs <= 3600:
                    expiring_soon_count += 1
                is_scouted = norm["id"] in scouted_ids
                norm["is_scouted"] = is_scouted
                norm["is_kickbase_seller"] = (
                    not norm.get("owner_user_id")
                    or norm.get("owner_user_id") == "0"
                    or str(norm.get("owner_name") or "").lower() == "kickbase"
                )
                mv = norm.get("market_value") or 0
                prc = norm.get("price") or mv
                norm["price_diff"] = prc - mv
                market_players.append(norm)
                if is_scouted:
                    scouted_matches.append(norm)

        market_players.sort(
            key=lambda p: (
                p["expiry_seconds"] if isinstance(p.get("expiry_seconds"), (int, float)) else 9999999,
                -(p.get("market_value") or 0),
            )
        )

        current_scouted_ids = {p["id"] for p in scouted_matches}
        if self._known_scouted_on_market is not None:
            newly_listed = current_scouted_ids - self._known_scouted_on_market
            for p in scouted_matches:
                if p["id"] in newly_listed:
                    self.hass.bus.async_fire(
                        EVENT_SCOUTED_ON_MARKET,
                        {
                            "league_id": self.league_id,
                            "player_id": p["id"],
                            "player_name": p["full_name"] or p["name"],
                            "market_value": p["market_value"],
                            "price": p["price"],
                            "expiry_seconds": p["expiry_seconds"],
                        },
                    )
        self._known_scouted_on_market = current_scouted_ids

        cheapest = min(market_players, key=lambda p: p.get("price") or p.get("market_value") or 0) if market_players else None
        most_valuable = max(market_players, key=lambda p: p.get("market_value") or 0) if market_players else None

        return {
            "market": market_players,
            "market_count": len(market_players),
            "expiring_soon_count": expiring_soon_count,
            "market_value_update_at": market_raw.get("mvud") if isinstance(market_raw, dict) else None,
            "next_matchday_at": market_raw.get("dt") if isinstance(market_raw, dict) else None,
            "matchday": market_raw.get("day") if isinstance(market_raw, dict) else None,
            "cheapest_player": cheapest,
            "most_valuable_player": most_valuable,
            "scouted": scouted_players,
            "scouted_count": len(scouted_players),
            "scouted_on_market": scouted_matches,
            "scouted_on_market_count": len(scouted_matches),
        }


class LiveMatchdayCoordinator(KickbaseBaseCoordinator[dict[str, Any]]):
    """Module: live_matchday — Competition fixtures, table, ranking, live myeleven & events."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: KickbaseApi,
        league_id: str,
        user_id: str,
        competition_id: str,
        idle_seconds: int = 900,
    ) -> None:
        self.league_id = league_id
        self.user_id = user_id
        self.competition_id = competition_id
        self._idle_interval = timedelta(seconds=idle_seconds)
        self._seen_event_keys: set[str] | None = None
        super().__init__(
            hass,
            config_entry,
            api,
            name=f"kickbase_league_{league_id}_live",
            update_interval=self._idle_interval,
            logger=_LOGGER,
        )

    async def _async_fetch_data(self) -> dict[str, Any]:
        ibp = self.api.client.image_base_url
        matchdays_raw, table_raw, comp_ranking_raw, myeleven_raw = await asyncio.gather(
            self.api.competitions.get_matchdays(self.competition_id),
            self.api.competitions.get_table(self.competition_id),
            self.api.competitions.get_ranking(self.competition_id),
            self.api.squad.get_my_eleven(self.league_id),
        )

        current_day = matchdays_raw.get("day") if isinstance(matchdays_raw, dict) else None
        teamcenter_raw: dict[str, Any] = {}
        if self.user_id and current_day is not None:
            tc = await self.api.squad.get_user_teamcenter(
                self.league_id, self.user_id, day_number=int(current_day)
            )
            if isinstance(tc, dict):
                teamcenter_raw = tc

        # Extract fixtures for current matchday and all matchdays
        current_matches: list[dict[str, Any]] = []
        all_matchdays: list[dict[str, Any]] = []
        live_match_ids: list[str] = []

        # Build team name map from table
        team_names: dict[str, str] = {}
        table_rows: list[dict[str, Any]] = []
        for row in (table_raw.get("it") or []) if isinstance(table_raw, dict) else []:
            tid = str(row.get("tid", ""))
            tn = row.get("tn", tid)
            if tid:
                team_names[tid] = tn
            table_rows.append(
                {
                    "team_id": tid,
                    "team_name": tn,
                    "rank": row.get("cpl", 0),
                    "prev_rank": row.get("pcpl", 0),
                    "points": row.get("cp", 0),
                    "matches_played": row.get("mc", 0),
                    "goal_diff": row.get("gd", 0),
                    "kickbase_matchday_points": row.get("mdp", 0),
                    "kickbase_season_points": row.get("sp", 0),
                    "is_live": bool(row.get("il", False)),
                    "match_id": str(row.get("mi")) if row.get("mi") is not None else None,
                    "image": resolve_image_url(row.get("tim"), ibp),
                }
            )
        table_rows.sort(key=lambda r: r["rank"] or 99)

        for md_block in (matchdays_raw.get("it") or []) if isinstance(matchdays_raw, dict) else []:
            day_num = md_block.get("day")
            matches = []
            for m in md_block.get("it") or []:
                mi = str(m.get("mi", ""))
                t1 = str(m.get("t1", ""))
                t2 = str(m.get("t2", ""))
                is_live = bool(m.get("il", False))
                match_obj = {
                    "id": mi,
                    "day": day_num,
                    "date": m.get("dt"),
                    "team1_id": t1,
                    "team2_id": t2,
                    "team1_name": team_names.get(t1, m.get("t1sy") or t1),
                    "team2_name": team_names.get(t2, m.get("t2sy") or t2),
                    "team1_short": m.get("t1sy") or t1,
                    "team2_short": m.get("t2sy") or t2,
                    "team1_goals": m.get("t1g", 0),
                    "team2_goals": m.get("t2g", 0),
                    "minute": m.get("mtd") or "",
                    "status_code": m.get("st"),
                    "status": decode_match_status(m.get("st")),
                    "is_live": is_live,
                    "team1_image": resolve_image_url(m.get("t1im"), ibp),
                    "team2_image": resolve_image_url(m.get("t2im"), ibp),
                }
                matches.append(match_obj)
                if day_num == current_day and is_live and mi:
                    live_match_ids.append(mi)
            all_matchdays.append({"day": day_num, "matches": matches})
            if day_num == current_day:
                current_matches = matches

        # Adaptive polling!
        is_any_live = bool(live_match_ids) or any(
            m.get("is_live") for m in current_matches
        )
        desired_interval = LIVE_MATCHDAY_ACTIVE_INTERVAL if is_any_live else self._idle_interval
        if self.update_interval != desired_interval:
            _LOGGER.debug(
                "Adjusting live matchday poll interval for league %s to %s",
                self.league_id,
                desired_interval,
            )
            self.update_interval = desired_interval

        # Fetch live match details for active live matches (capped at 9 concurrent)
        live_match_details: dict[str, Any] = {}
        if live_match_ids:
            details_results = await asyncio.gather(
                *(self.api.competitions.get_match_details(mid) for mid in live_match_ids[:9]),
                return_exceptions=True,
            )
            for mid, res in zip(live_match_ids[:9], details_results):
                if isinstance(res, dict) and res:
                    live_match_details[mid] = res

        my_eleven_players = [
            normalize_player(p, ibp)
            for p in ((myeleven_raw.get("lp") or []) if isinstance(myeleven_raw, dict) else [])
        ]
        my_eleven_ids = {p["id"] for p in my_eleven_players}
        bench_players = [
            normalize_player(p, ibp)
            for p in ((myeleven_raw.get("nlp") or []) if isinstance(myeleven_raw, dict) else [])
        ]

        # Fire live events for squad players if live details show new key events
        current_event_keys: set[str] = set()
        for mid, detail in live_match_details.items():
            for ev in detail.get("events") or []:
                pi = str(ev.get("pi", ""))
                ke = ev.get("ke")
                mt = ev.get("mt")
                key = f"{mid}:{pi}:{ke}:{mt}"
                current_event_keys.add(key)
                if (
                    self._seen_event_keys is not None
                    and key not in self._seen_event_keys
                    and pi in my_eleven_ids
                ):
                    self.hass.bus.async_fire(
                        EVENT_LIVE_PLAYER_EVENT,
                        {
                            "league_id": self.league_id,
                            "match_id": mid,
                            "player_id": pi,
                            "player_name": ev.get("pn"),
                            "event_type_id": ke,
                            "minute": mt,
                        },
                    )
        self._seen_event_keys = current_event_keys

        # Extract my rank from teamcenter if available
        my_tc_rank = None
        my_tc_points = myeleven_raw.get("p", 0) if isinstance(myeleven_raw, dict) else 0
        teamcenter_users = []
        for u in (teamcenter_raw.get("us") or []):
            uid = str(u.get("i", ""))
            u_entry = {
                "id": uid,
                "name": u.get("unm", "Manager"),
                "matchday_points": u.get("mdp", 0),
                "rank": u.get("pl", 0),
                "avatar": resolve_image_url(u.get("uim"), ibp),
                "is_me": uid == self.user_id,
            }
            teamcenter_users.append(u_entry)
            if uid == self.user_id:
                my_tc_rank = u.get("pl")
                my_tc_points = u.get("mdp", my_tc_points)

        comp_ranking = [
            {
                "team_id": str(r.get("tid", "")),
                "team_name": r.get("tn"),
                "matchday_rank": r.get("mdpl"),
                "season_rank": r.get("spl"),
                "matchday_points": r.get("mdp", 0),
                "season_points": r.get("sp", 0),
                "is_live": bool(r.get("il", False)),
                "image": resolve_image_url(r.get("tim"), ibp),
            }
            for r in ((comp_ranking_raw.get("it") or []) if isinstance(comp_ranking_raw, dict) else [])
        ]

        return {
            "competition_id": self.competition_id,
            "current_matchday": current_day,
            "is_live": is_any_live,
            "live_match_count": len(live_match_ids),
            "live_points": my_tc_points,
            "live_rank": my_tc_rank,
            "my_eleven": my_eleven_players,
            "bench": bench_players,
            "current_matches": current_matches,
            "all_matchdays": all_matchdays,
            "live_match_details": live_match_details,
            "teamcenter_standings": teamcenter_users,
            "competition_table": table_rows,
            "competition_ranking": comp_ranking,
        }


class FeedAchievementsCoordinator(KickbaseBaseCoordinator[dict[str, Any]]):
    """Module: feed_achievements — League activity feed & user achievements."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: KickbaseApi,
        league_id: str,
        update_seconds: int = 300,
    ) -> None:
        self.league_id = league_id
        self._seen_activity_ids: set[str] | None = None
        super().__init__(
            hass,
            config_entry,
            api,
            name=f"kickbase_league_{league_id}_feed",
            update_interval=timedelta(seconds=update_seconds),
            logger=_LOGGER,
        )

    async def _async_fetch_data(self) -> dict[str, Any]:
        feed_raw, ach_raw = await asyncio.gather(
            self.api.managers.get_activities_feed(self.league_id, start=0, max_items=30),
            self.api.leagues.get_achievements(self.league_id),
        )

        activities: list[dict[str, Any]] = []
        current_ids: set[str] = set()
        for item in (feed_raw.get("af") or []) if isinstance(feed_raw, dict) else []:
            aid = str(item.get("i", ""))
            atype = decode_activity_type(item.get("t"))
            data = item.get("data") or {}
            entry = {
                "id": aid,
                "type_code": item.get("t"),
                "type": atype,
                "date": item.get("dt"),
                "comment_count": item.get("coc", 0),
                "data": data,
            }
            activities.append(entry)
            if aid:
                current_ids.add(aid)

        if self._seen_activity_ids is not None:
            for item in activities:
                if item["id"] and item["id"] not in self._seen_activity_ids:
                    self.hass.bus.async_fire(
                        EVENT_NEW_ACTIVITY,
                        {
                            "league_id": self.league_id,
                            "activity_id": item["id"],
                            "type_code": item["type_code"],
                            "type_label": item["type"]["label_de"],
                            "date": item["date"],
                            "data": item["data"],
                        },
                    )
        self._seen_activity_ids = current_ids

        achievements: list[dict[str, Any]] = []
        earned_count = 0
        for ach in (ach_raw.get("it") or []) if isinstance(ach_raw, dict) else []:
            is_earned = bool(ach.get("ise", False))
            if is_earned:
                earned_count += 1
            achievements.append(
                {
                    "type": ach.get("t"),
                    "name": ach.get("n"),
                    "count": ach.get("ac", 0),
                    "is_earned": is_earned,
                }
            )

        return {
            "activities": activities,
            "latest_activity": activities[0] if activities else None,
            "achievements": achievements,
            "earned_achievements_count": earned_count,
            "total_achievements_count": len(achievements),
        }
