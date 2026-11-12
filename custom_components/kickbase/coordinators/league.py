"""Consolidated hourly per-league coordinator with local SQLite & photo caching."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from ..api.exceptions import KickbaseAuthError, KickbaseError
from ..api.models import (
    decode_activity_type,
    decode_match_status,
    normalize_market_value_series,
    normalize_player,
    parse_iso_datetime,
    resolve_image_url,
)
from ..const import (
    DEFAULT_DETAILS_REFRESH_HOURS,
    DEFAULT_SYNC_INTERVAL_SECONDS,
    EVENT_LIVE_PLAYER_EVENT,
    EVENT_NEGATIVE_BUDGET,
    EVENT_NEW_ACTIVITY,
    EVENT_PLAYER_STATUS_CHANGED,
    EVENT_SCOUTED_ON_MARKET,
    LIVE_MATCHDAY_ACTIVE_INTERVAL,
    MODULE_FEED_ACHIEVEMENTS,
    MODULE_LEAGUE_OVERVIEW,
    MODULE_LIVE_MATCHDAY,
    MODULE_MARKET_TRANSFERS,
    MODULE_SQUAD_LINEUP,
)
from .base import KickbaseBaseCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from ..api import KickbaseApi
    from ..storage import KickbaseLocalStore

_LOGGER = logging.getLogger(__name__)


def _merge_player(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge heterogeneous player dicts without overwriting non-empty fields with empty ones."""
    merged = dict(existing)
    for key, val in incoming.items():
        if key == "status" and isinstance(val, dict):
            if val.get("key") != "unknown" or not merged.get("status"):
                merged[key] = val
        elif key == "position" and isinstance(val, dict):
            if val.get("key") != "unknown" or not merged.get("position"):
                merged[key] = val
        elif val is not None and val != "" and val != [] and (val != 0 or key not in merged or not merged[key]):
            merged[key] = val
        elif key not in merged:
            merged[key] = val
    return merged


class LeagueSyncCoordinator(KickbaseBaseCoordinator[dict[str, Any]]):
    """Single consolidated coordinator per league (default: once per hour).

    Fetches league overview, user squad/lineup, transfer market + scouted players,
    and all rival managers' squads in one coordinated pass, persists every unique
    player + historical market value + status transitions into local SQLite, and
    caches player photos / club crests locally.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: KickbaseApi,
        store: KickbaseLocalStore,
        *,
        league_id: str,
        user_id: str,
        competition_id: str,
        enabled_modules: set[str],
        market_value_timeframe: int = 92,
        sync_seconds: int = DEFAULT_SYNC_INTERVAL_SECONDS,
        cache_photos: bool = True,
        fetch_player_details: bool = True,
        adaptive_live_polling: bool = False,
    ) -> None:
        self.league_id = league_id
        self.user_id = user_id
        self.competition_id = competition_id
        self.store = store
        self.enabled_modules = set(enabled_modules)
        self.market_value_timeframe = market_value_timeframe
        self._base_interval = timedelta(seconds=sync_seconds)
        self._cache_photos = cache_photos
        self._fetch_player_details = fetch_player_details
        self._adaptive_live_polling = adaptive_live_polling
        self._force_full_details = False

        self._was_negative: bool | None = None
        self._known_scouted_on_market: set[str] | None = None
        self._seen_event_keys: set[str] | None = None
        self._seen_activity_ids: set[str] | None = None

        super().__init__(
            hass,
            config_entry,
            api,
            name=f"kickbase_league_{league_id}_hourly_sync",
            update_interval=self._base_interval,
            logger=_LOGGER,
        )

    async def async_trigger_sync(self, *, force_full_details: bool = False) -> None:
        """Trigger an immediate consolidated sync (optionally forcing full backfill)."""
        self._force_full_details = force_full_details
        try:
            await self.async_request_refresh()
        finally:
            self._force_full_details = False

    async def _async_fetch_data(self) -> dict[str, Any]:
        started_at = datetime.now(UTC).isoformat()
        start_req_count = self.api.client.request_count
        ibp = self.api.client.image_base_url
        force_full = self._force_full_details

        # ------------------------------------------------------------------
        # Phase 1: Core league overview, ranking, budget, my squad, market
        # ------------------------------------------------------------------
        need_overview = MODULE_LEAGUE_OVERVIEW in self.enabled_modules
        need_squad = MODULE_SQUAD_LINEUP in self.enabled_modules
        need_market = MODULE_MARKET_TRANSFERS in self.enabled_modules
        need_live = MODULE_LIVE_MATCHDAY in self.enabled_modules
        need_feed = MODULE_FEED_ACHIEVEMENTS in self.enabled_modules

        # Always fetch ranking so we know all managers in the league for DB sync
        overview_raw: dict[str, Any] = {}
        me_raw: dict[str, Any] = {}
        budget_raw: dict[str, Any] = {}
        settings_raw: dict[str, Any] = {}
        ranking_raw: dict[str, Any] = {}

        if need_overview:
            overview_raw, me_raw, budget_raw, ranking_raw, settings_raw = await asyncio.gather(
                self.api.leagues.get_overview(self.league_id, include_managers_and_battles=True),
                self.api.leagues.get_me(self.league_id),
                self.api.leagues.get_my_budget(self.league_id),
                self.api.leagues.get_ranking(self.league_id),
                self.api.leagues.get_settings(self.league_id),
            )
        else:
            ranking_raw = await self.api.leagues.get_ranking(self.league_id)

        # Always fetch my squad & market whenever local player sync or respective module is active
        squad_raw: dict[str, Any] = {}
        lineup_ov_raw: dict[str, Any] = {}
        teams_raw: dict[str, Any] = {}
        myeleven_raw: dict[str, Any] = {}
        if need_squad or need_overview or need_market:
            squad_raw, lineup_ov_raw, teams_raw, myeleven_raw = await asyncio.gather(
                self.api.squad.get_squad(self.league_id),
                self.api.squad.get_lineup_overview(self.league_id),
                self.api.squad.get_lineup_teams(self.league_id),
                self.api.squad.get_my_eleven(self.league_id),
            )

        market_raw: dict[str, Any] = {}
        scouted_raw: dict[str, Any] = {}
        if need_market or need_overview or need_squad:
            market_raw, scouted_raw = await asyncio.gather(
                self.api.market.get_market(self.league_id),
                self.api.market.get_scouted_players(self.league_id),
            )

        # ------------------------------------------------------------------
        # Phase 2: Build overview, standings & battles
        # ------------------------------------------------------------------
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

        overview_data: dict[str, Any] | None = None
        if need_overview:
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

            comp_id = str(
                overview_raw.get("cpi")
                or me_raw.get("cpi")
                or ranking_raw.get("cpi")
                or self.competition_id
                or "1"
            )
            self.competition_id = comp_id

            overview_data = {
                "league": {
                    "id": self.league_id,
                    "name": overview_raw.get("lnm") or me_raw.get("lnm") or f"Liga {self.league_id}",
                    "competition_id": comp_id,
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

        # ------------------------------------------------------------------
        # Phase 3: Team crests, my squad, market, scouted & rival manager squads
        # ------------------------------------------------------------------
        team_images: dict[str, str] = {}
        for tm in (teams_raw.get("tms") or []) if isinstance(teams_raw, dict) else []:
            tid = str(tm.get("tid", ""))
            if tid and tm.get("tim"):
                if url := resolve_image_url(tm["tim"], ibp):
                    team_images[tid] = url

        # Accumulate unique players across all 3 scopes:
        # 1) my_squad, 2) market (+scouted), 3) rival_squad
        player_pool: dict[str, dict[str, Any]] = {}
        player_scopes: dict[str, set[str]] = {}
        scouted_ids: set[str] = set()

        def _register_player(norm_p: dict[str, Any], scope: str) -> None:
            pid = norm_p.get("id")
            if not pid:
                return
            tid = norm_p.get("team_id")
            if tid and tid in team_images and not norm_p.get("team_image"):
                norm_p["team_image"] = team_images[tid]
            player_scopes.setdefault(pid, set()).add(scope)
            if pid in player_pool:
                player_pool[pid] = _merge_player(player_pool[pid], norm_p)
            else:
                player_pool[pid] = norm_p

        # 3a) Scouted players
        scouted_players: list[dict[str, Any]] = []
        for raw_p in (scouted_raw.get("it") or scouted_raw.get("sps") or []) if isinstance(scouted_raw, dict) else []:
            norm = normalize_player(raw_p, ibp)
            if norm["id"]:
                scouted_ids.add(norm["id"])
                scouted_players.append(norm)
                _register_player(norm, "scouted")

        # 3b) Transfer market players
        market_players: list[dict[str, Any]] = []
        expiring_soon_count = 0
        scouted_matches: list[dict[str, Any]] = []
        for raw_p in (market_raw.get("it") or []) if isinstance(market_raw, dict) else []:
            norm = normalize_player(raw_p, ibp)
            norm["is_on_market"] = True
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
            _register_player(norm, "market")

        # 3c) My squad + lineup overview
        myeleven_by_id: dict[str, dict[str, Any]] = {}
        for p in (myeleven_raw.get("lp") or []) if isinstance(myeleven_raw, dict) else []:
            pid = str(p.get("i", ""))
            if pid:
                myeleven_by_id[pid] = p

        lineup_by_id: dict[str, dict[str, Any]] = {}
        lineup_players: list[dict[str, Any]] = []
        for raw_p in (lineup_ov_raw.get("lp") or []) if isinstance(lineup_ov_raw, dict) else []:
            norm = normalize_player(raw_p, ibp)
            if tid := norm.get("team_id"):
                if tid in team_images:
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

        my_name = my_standing.get("name")
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
            if self.user_id:
                norm["owner_user_id"] = norm.get("owner_user_id") or self.user_id
            if my_name:
                norm["owner_name"] = norm.get("owner_name") or my_name
            if tid := norm.get("team_id"):
                if tid in team_images:
                    norm["team_image"] = team_images[tid]
            if norm["id"] in lineup_by_id:
                lp_entry = lineup_by_id[norm["id"]]
                norm["is_captain"] = lp_entry.get("is_captain", False)
                norm["home_team_image"] = lp_entry.get("home_team_image")
                norm["away_team_image"] = lp_entry.get("away_team_image")
                norm["in_starting_eleven"] = lp_entry.get("matchday_status", 0) != 8
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
            _register_player(norm, "my_squad")

        # 3d) Fetch ALL managers' squads, dashboards & transfers for local DB
        managers_payload: list[dict[str, Any]] = []
        rival_player_ids: set[str] = set()
        mgr_sem = asyncio.Semaphore(3)

        async def _fetch_manager(mgr: dict[str, Any]) -> dict[str, Any] | None:
            mid = mgr["id"]
            if not mid:
                return None
            async with mgr_sem:
                try:
                    dash, m_squad, m_perf, m_transfers = await asyncio.gather(
                        self.api.managers.get_manager_dashboard(self.league_id, mid),
                        self.api.managers.get_manager_squad(self.league_id, mid),
                        self.api.managers.get_manager_performance(self.league_id, mid),
                        self.api.managers.get_manager_transfers(self.league_id, mid),
                    )
                except KickbaseAuthError:
                    raise
                except KickbaseError as err:
                    _LOGGER.warning("Skipping manager %s during sync: %s", mid, err)
                    return None

            m_squad_players: list[dict[str, Any]] = []
            for rp in (m_squad.get("it") or []) if isinstance(m_squad, dict) else []:
                np = normalize_player(rp, ibp)
                if not np.get("owner_user_id"):
                    np["owner_user_id"] = mid
                if not np.get("owner_name"):
                    np["owner_name"] = mgr.get("name")
                m_squad_players.append(np)

            transfer_list = [
                {
                    "player_id": str(t.get("pi", "")),
                    "player_name": t.get("pn"),
                    "team_id": str(t.get("tid", "")),
                    "type": t.get("tty"),
                    "other_manager": t.get("othnm"),
                    "price": t.get("trp", 0),
                    "date": t.get("dt"),
                    "image": resolve_image_url(t.get("pim"), ibp),
                }
                for t in ((m_transfers.get("it") or []) if isinstance(m_transfers, dict) else [])
            ]

            return {
                **mgr,
                "dashboard": {
                    "id": str(dash.get("u", mid)) if isinstance(dash, dict) else mid,
                    "name": (dash.get("unm") if isinstance(dash, dict) else None) or mgr.get("name"),
                    "avatar": resolve_image_url(dash.get("uim"), ibp)
                    if isinstance(dash, dict) and dash.get("uim")
                    else mgr.get("avatar"),
                    "rank": dash.get("pl", mgr.get("rank", 0)) if isinstance(dash, dict) else mgr.get("rank", 0),
                    "average_points": dash.get("ap", mgr.get("points_avg", 0)) if isinstance(dash, dict) else mgr.get("points_avg", 0),
                    "total_points": dash.get("tp", mgr.get("season_points", 0)) if isinstance(dash, dict) else mgr.get("season_points", 0),
                    "matchday_wins": dash.get("mdw", 0) if isinstance(dash, dict) else 0,
                    "team_value": dash.get("tv", mgr.get("team_value", 0)) if isinstance(dash, dict) else mgr.get("team_value", 0),
                    "profit": dash.get("prft", 0) if isinstance(dash, dict) else 0,
                },
                "squad": m_squad_players,
                "performance": (m_perf.get("it") or []) if isinstance(m_perf, dict) else [],
                "transfers": transfer_list,
            }

        mgr_results = await asyncio.gather(*(_fetch_manager(m) for m in managers_list))
        for res in mgr_results:
            if res is None:
                continue
            managers_payload.append(res)
            is_me = bool(res.get("is_me"))
            scope = "my_squad" if is_me else "rival_squad"
            for sp in res.get("squad") or []:
                if not is_me and sp.get("id"):
                    rival_player_ids.add(sp["id"])
                _register_player(sp, scope)

        # ------------------------------------------------------------------
        # Phase 4: Enrich unique players (details, MV history backfill, perf)
        # ------------------------------------------------------------------
        all_player_ids = list(player_pool.keys())
        existing_meta = await self.store.async_get_player_sync_meta(
            self.league_id, all_player_ids
        )
        now_dt = datetime.now(UTC)
        mv_stale_cutoff = now_dt - timedelta(hours=DEFAULT_DETAILS_REFRESH_HOURS)
        player_sem = asyncio.Semaphore(3)

        async def _enrich_player(pid: str) -> dict[str, Any]:
            p = player_pool[pid]
            meta = existing_meta.get(pid) or {}
            mv_synced_dt = parse_iso_datetime(meta.get("market_value_synced_at"))
            need_mv_backfill = force_full or mv_synced_dt is None or mv_synced_dt < mv_stale_cutoff

            details_dict: dict[str, Any] | None = None
            mv_series_info: dict[str, Any] | None = None
            perf_list: list[Any] | None = None
            transfers_dict: dict[str, Any] | None = None
            transfer_hist_list: list[Any] | None = None
            details_refreshed = False
            mv_refreshed = False

            if self._fetch_player_details or need_mv_backfill:
                async with player_sem:
                    try:
                        if need_mv_backfill:
                            raw_det, raw_mv, raw_perf, raw_tr, raw_th = await asyncio.gather(
                                self.api.market.get_player_details(self.league_id, pid),
                                self.api.market.get_player_market_value(
                                    self.league_id, pid, self.market_value_timeframe
                                ),
                                self.api.market.get_player_performance(self.league_id, pid),
                                self.api.market.get_player_transfers(self.league_id, pid),
                                self.api.market.get_player_transfer_history(self.league_id, pid),
                            )
                            mv_refreshed = True
                            if isinstance(raw_mv, dict):
                                mv_series_info = normalize_market_value_series(raw_mv)
                            if isinstance(raw_perf, dict):
                                perf_list = raw_perf.get("it") or []
                            if isinstance(raw_tr, dict):
                                transfers_dict = raw_tr
                            if isinstance(raw_th, dict):
                                transfer_hist_list = [
                                    {
                                        "user_id": str(h.get("u", "")) if h.get("u") else None,
                                        "user_name": h.get("unm") or "Kickbase",
                                        "user_avatar": resolve_image_url(h.get("uim"), ibp),
                                        "date": h.get("dt"),
                                        "price": h.get("trp", 0),
                                        "type": h.get("t"),
                                    }
                                    for h in (raw_th.get("it") or [])
                                ]
                        else:
                            raw_det = await self.api.market.get_player_details(self.league_id, pid)

                        if isinstance(raw_det, dict) and raw_det:
                            details_refreshed = True
                            norm_det = normalize_player(raw_det, ibp)
                            p = _merge_player(p, norm_det)
                            details_dict = {
                                "season_match_count": raw_det.get("smc"),
                                "matchday_summaries": raw_det.get("mdsum", []),
                                "status_text": raw_det.get("stxt"),
                                "ligainsider_url": resolve_image_url(raw_det.get("plpurl"), ibp),
                                "prob_history": raw_det.get("ph", []),
                                "transfer_price": (mv_series_info or {}).get("transfer_price", 0),
                                "profit_loss": (mv_series_info or {}).get(
                                    "profit_loss", p.get("market_value_since_buy", 0)
                                ),
                                "lowest_market_value": (mv_series_info or {}).get("lowest_market_value", 0),
                                "highest_market_value": (mv_series_info or {}).get("highest_market_value", 0),
                            }
                            if raw_det.get("stxt"):
                                p["status_text"] = raw_det["stxt"]
                    except KickbaseAuthError:
                        raise
                    except KickbaseError as err:
                        _LOGGER.debug("Player detail sync partial fallback for %s: %s", pid, err)

            scopes = sorted(player_scopes.get(pid) or set())
            p["scopes"] = scopes
            p["is_scouted"] = pid in scouted_ids
            return {
                "player": p,
                "scopes": scopes,
                "is_scouted": pid in scouted_ids,
                "details": details_dict,
                "market_value_series": mv_series_info,
                "performance": perf_list,
                "transfers": transfers_dict,
                "transfer_history": transfer_hist_list,
                "details_refreshed": details_refreshed,
                "mv_refreshed": mv_refreshed,
            }

        enriched_items = await asyncio.gather(*(_enrich_player(pid) for pid in all_player_ids))

        # ------------------------------------------------------------------
        # Phase 5: Local photo cache (download only if missing on disk!)
        # ------------------------------------------------------------------
        photos_downloaded = 0
        if self._cache_photos:
            photo_targets: dict[str, str] = {}
            for item in enriched_items:
                pl = item["player"]
                if pl.get("image"):
                    photo_targets[f"player_{pl['id']}"] = pl["image"]
                if pl.get("team_image") and pl.get("team_id"):
                    photo_targets[f"team_{pl['team_id']}"] = pl["team_image"]
            for mgr in managers_payload:
                if mgr.get("avatar"):
                    photo_targets[f"manager_{mgr['id']}"] = mgr["avatar"]

            cached_map = await self.store.async_find_cached_photos(list(photo_targets.keys()))
            missing_keys = [k for k in photo_targets if k not in cached_map]

            photo_sem = asyncio.Semaphore(4)

            async def _download_missing(pkey: str) -> tuple[str, str | None]:
                async with photo_sem:
                    dl = await self.api.client.async_download_bytes(photo_targets[pkey])
                    if not dl:
                        return pkey, None
                    raw_bytes, ct = dl
                    if not raw_bytes:
                        return pkey, None
                    local_url = await self.store.async_save_photo(
                        pkey, raw_bytes, remote_url=photo_targets[pkey], content_type=ct
                    )
                    return pkey, local_url

            if missing_keys:
                dl_results = await asyncio.gather(*(_download_missing(k) for k in missing_keys))
                for pkey, local_url in dl_results:
                    if local_url:
                        cached_map[pkey] = local_url
                        photos_downloaded += 1

            # Attach local_image URLs onto in-memory & persisted payloads
            for item in enriched_items:
                pl = item["player"]
                if loc := cached_map.get(f"player_{pl['id']}"):
                    pl["local_image"] = loc
                if pl.get("team_id") and (tloc := cached_map.get(f"team_{pl['team_id']}")):
                    pl["local_team_image"] = tloc
            for mgr in managers_payload:
                if alog := cached_map.get(f"manager_{mgr['id']}"):
                    mgr["local_avatar"] = alog

        # Index enriched players for returning fresh local_image into squad/lineup/market payloads
        enriched_by_id = {item["player"]["id"]: item["player"] for item in enriched_items}

        # ------------------------------------------------------------------
        # Phase 6: Optional Live Matchday & Feed/Achievements (same hourly pass)
        # ------------------------------------------------------------------
        live_data: dict[str, Any] | None = None
        if need_live:
            live_data = await self._fetch_live_matchday_section(ibp, myeleven_raw)

        feed_data: dict[str, Any] | None = None
        if need_feed:
            feed_data = await self._fetch_feed_achievements_section()

        # ------------------------------------------------------------------
        # Phase 7: Atomic SQLite Persistence + HA Events
        # ------------------------------------------------------------------
        total_api_requests = max(0, self.api.client.request_count - start_req_count)
        sync_meta = {
            "started_at": started_at,
            "players_total": len(enriched_items),
            "my_squad_count": len(squad_players),
            "market_count": len(market_players),
            "rival_players_count": len(rival_player_ids),
            "managers_synced": len(managers_payload),
            "photos_downloaded": photos_downloaded,
            "api_requests": total_api_requests,
            "status": "ok",
        }
        status_changes = await self.store.async_upsert_bulk_sync(
            league_id=self.league_id,
            players_payload=enriched_items,
            managers_payload=managers_payload,
            sync_meta=sync_meta,
        )
        for chg in status_changes:
            self.hass.bus.async_fire(EVENT_PLAYER_STATUS_CHANGED, chg)

        # Build squad_lineup & market_transfers module dicts using enriched/cached photos
        squad_lineup_data: dict[str, Any] | None = None
        if need_squad:
            enriched_squad = [
                _merge_player(p, enriched_by_id.get(p["id"], {})) for p in squad_players
            ]
            enriched_squad.sort(
                key=lambda p: (p.get("position_code") or 9, -(p.get("market_value") or 0))
            )
            enriched_lineup = [
                _merge_player(p, enriched_by_id.get(p["id"], {})) for p in lineup_players
            ]
            lineup_issues = [
                p
                for p in enriched_lineup
                if p["status"]["severity"] == "danger" or p.get("matchday_status") == 8
            ]
            captain = next((p for p in enriched_lineup if p.get("is_captain")), None)

            squad_lineup_data = {
                "squad": enriched_squad,
                "summary": {
                    "count": len(enriched_squad),
                    "total_market_value": total_mv,
                    "total_24h_change": total_24h,
                    "total_season_diff": total_season_diff,
                    "total_profit_loss": total_profit,
                    "average_player_points": round(avg_points_sum / len(enriched_squad), 1)
                    if enriched_squad
                    else 0.0,
                    "rising_count": rising_count,
                    "falling_count": falling_count,
                    "injured_or_suspended_count": injured_or_suspended_count,
                },
                "lineup": {
                    "formation": lineup_ov_raw.get("t", "4-4-2")
                    if isinstance(lineup_ov_raw, dict)
                    else "4-4-2",
                    "matchday": lineup_ov_raw.get("mdln")
                    if isinstance(lineup_ov_raw, dict)
                    else None,
                    "lock_at": lineup_ov_raw.get("lis")
                    if isinstance(lineup_ov_raw, dict)
                    else None,
                    "player_count": lineup_ov_raw.get("lpc", len(enriched_lineup))
                    if isinstance(lineup_ov_raw, dict)
                    else len(enriched_lineup),
                    "confirmed_count": lineup_ov_raw.get("clpc", 0)
                    if isinstance(lineup_ov_raw, dict)
                    else 0,
                    "has_captain": bool(lineup_ov_raw.get("cpte", False))
                    if isinstance(lineup_ov_raw, dict)
                    else False,
                    "captain_name": captain["name"] if captain else None,
                    "captain_id": captain["id"] if captain else None,
                    "players": enriched_lineup,
                    "issue_count": len(lineup_issues),
                    "issues": [p["name"] for p in lineup_issues],
                },
                "team_images": team_images,
            }

        market_data: dict[str, Any] | None = None
        if need_market:
            enriched_market = [
                _merge_player(p, enriched_by_id.get(p["id"], {})) for p in market_players
            ]
            enriched_market.sort(
                key=lambda p: (
                    p["expiry_seconds"]
                    if isinstance(p.get("expiry_seconds"), (int, float))
                    else 9999999,
                    -(p.get("market_value") or 0),
                )
            )
            enriched_scouted = [
                _merge_player(p, enriched_by_id.get(p["id"], {})) for p in scouted_players
            ]

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

            cheapest = (
                min(
                    enriched_market,
                    key=lambda p: p.get("price") or p.get("market_value") or 0,
                )
                if enriched_market
                else None
            )
            most_valuable = (
                max(enriched_market, key=lambda p: p.get("market_value") or 0)
                if enriched_market
                else None
            )
            market_data = {
                "market": enriched_market,
                "market_count": len(enriched_market),
                "expiring_soon_count": expiring_soon_count,
                "market_value_update_at": market_raw.get("mvud")
                if isinstance(market_raw, dict)
                else None,
                "next_matchday_at": market_raw.get("dt")
                if isinstance(market_raw, dict)
                else None,
                "matchday": market_raw.get("day")
                if isinstance(market_raw, dict)
                else None,
                "cheapest_player": cheapest,
                "most_valuable_player": most_valuable,
                "scouted": enriched_scouted,
                "scouted_count": len(enriched_scouted),
                "scouted_on_market": scouted_matches,
                "scouted_on_market_count": len(scouted_matches),
            }

        db_stats = await self.store.async_get_stats(self.league_id)

        return {
            MODULE_LEAGUE_OVERVIEW: overview_data,
            MODULE_SQUAD_LINEUP: squad_lineup_data,
            MODULE_MARKET_TRANSFERS: market_data,
            MODULE_LIVE_MATCHDAY: live_data,
            MODULE_FEED_ACHIEVEMENTS: feed_data,
            "db_stats": db_stats,
            "last_sync_at": db_stats.get("last_sync_at") or datetime.now(UTC).isoformat(),
            "last_api_requests": total_api_requests,
        }

    async def _fetch_live_matchday_section(
        self, ibp: str, myeleven_raw: dict[str, Any]
    ) -> dict[str, Any]:
        matchdays_raw, table_raw, comp_ranking_raw = await asyncio.gather(
            self.api.competitions.get_matchdays(self.competition_id),
            self.api.competitions.get_table(self.competition_id),
            self.api.competitions.get_ranking(self.competition_id),
        )
        if not myeleven_raw:
            myeleven_raw = await self.api.squad.get_my_eleven(self.league_id)

        current_day = matchdays_raw.get("day") if isinstance(matchdays_raw, dict) else None
        teamcenter_raw: dict[str, Any] = {}
        if self.user_id and current_day is not None:
            tc = await self.api.squad.get_user_teamcenter(
                self.league_id, self.user_id, day_number=int(current_day)
            )
            if isinstance(tc, dict):
                teamcenter_raw = tc

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

        current_matches: list[dict[str, Any]] = []
        all_matchdays: list[dict[str, Any]] = []
        live_match_ids: list[str] = []

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

        is_any_live = bool(live_match_ids) or any(m.get("is_live") for m in current_matches)
        if self._adaptive_live_polling:
            desired_interval = LIVE_MATCHDAY_ACTIVE_INTERVAL if is_any_live else self._base_interval
            if self.update_interval != desired_interval:
                self.update_interval = desired_interval

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

        my_tc_rank = None
        my_tc_points = myeleven_raw.get("p", 0) if isinstance(myeleven_raw, dict) else 0
        teamcenter_users = []
        for u in teamcenter_raw.get("us") or []:
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

    async def _fetch_feed_achievements_section(self) -> dict[str, Any]:
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
