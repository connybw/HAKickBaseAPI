"""Home Assistant WebSocket API for modular Kickbase cards, panel & local DB."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .api.exceptions import KickbaseError
from .api.models import (
    normalize_market_value_series,
    normalize_player,
    resolve_image_url,
)
from .const import (
    DOMAIN,
    MODULE_CHALLENGES,
    MODULE_FEED_ACHIEVEMENTS,
    MODULE_LEAGUE_OVERVIEW,
    MODULE_LIVE_MATCHDAY,
    MODULE_MARKET_TRANSFERS,
    MODULE_NEWS_PREDICTIONS,
    MODULE_SQUAD_LINEUP,
)

if TYPE_CHECKING:
    from . import KickbaseConfigEntry
    from .coordinators import KickbaseRuntimeData

_LOGGER = logging.getLogger(__name__)
_SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)


def _get_loaded_entries(hass: HomeAssistant) -> list[KickbaseConfigEntry]:
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if getattr(entry, "runtime_data", None) is not None
    ]


def _resolve_runtime(
    hass: HomeAssistant,
    entry_id: str | None = None,
    league_id: str | None = None,
) -> tuple[KickbaseConfigEntry, KickbaseRuntimeData]:
    entries = _get_loaded_entries(hass)
    if not entries:
        raise ValueError("No loaded Kickbase configuration entry found")

    if entry_id:
        for e in entries:
            if e.entry_id == entry_id:
                return e, e.runtime_data
        raise ValueError(f"Unknown Kickbase entry_id: {entry_id}")

    if league_id:
        for e in entries:
            rt: KickbaseRuntimeData = e.runtime_data
            if league_id in rt.leagues:
                return e, rt

    return entries[0], entries[0].runtime_data


def _build_snapshot_payload(
    hass: HomeAssistant,
    entry_id: str | None = None,
    league_id: str | None = None,
) -> dict[str, Any]:
    entries = _get_loaded_entries(hass)
    if not entries:
        return {"configured": False, "entries": []}

    selected_entry, runtime = _resolve_runtime(hass, entry_id=entry_id, league_id=league_id)
    account_data = runtime.account.data or {}
    account_leagues = account_data.get("leagues") or {}

    selected_league_id = (
        league_id
        if league_id and league_id in runtime.leagues
        else (
            runtime.primary_league_id
            if runtime.primary_league_id in runtime.leagues
            else next(iter(runtime.leagues.keys()), "")
        )
    )

    leagues_meta = []
    for lid, lset in runtime.leagues.items():
        acc_l = account_leagues.get(lid) or {}
        sync_data = (lset.sync.data or {}) if lset.sync else {}
        ov_sub = sync_data.get(MODULE_LEAGUE_OVERVIEW) or {}
        ov_l = ov_sub.get("league", {}) if isinstance(ov_sub, dict) else {}
        ov_me = ov_sub.get("me", {}) if isinstance(ov_sub, dict) else {}
        leagues_meta.append(
            {
                "id": lid,
                "name": ov_l.get("name") or lset.league_name,
                "competition_id": ov_l.get("competition_id") or lset.competition_id,
                "competition_name": ov_l.get("competition_name") or acc_l.get("competition_name") or "Bundesliga",
                "image": ov_l.get("image") or acc_l.get("image"),
                "rank": ov_me.get("rank") or acc_l.get("rank"),
                "budget": ov_me.get("budget") if "budget" in ov_me else acc_l.get("budget"),
                "is_live": ov_l.get("is_live", False),
            }
        )

    league_data: dict[str, Any] = {}
    db_stats: dict[str, Any] | None = None
    last_sync_at: str | None = None
    last_api_requests: int = 0
    if selected_league_id and selected_league_id in runtime.leagues:
        lset = runtime.leagues[selected_league_id]
        sync_data = (lset.sync.data or {}) if lset.sync else {}
        league_data = {
            MODULE_LEAGUE_OVERVIEW: sync_data.get(MODULE_LEAGUE_OVERVIEW),
            MODULE_SQUAD_LINEUP: sync_data.get(MODULE_SQUAD_LINEUP),
            MODULE_MARKET_TRANSFERS: sync_data.get(MODULE_MARKET_TRANSFERS),
            MODULE_LIVE_MATCHDAY: sync_data.get(MODULE_LIVE_MATCHDAY),
            MODULE_FEED_ACHIEVEMENTS: sync_data.get(MODULE_FEED_ACHIEVEMENTS),
        }
        db_stats = sync_data.get("db_stats")
        last_sync_at = sync_data.get("last_sync_at")
        last_api_requests = int(sync_data.get("last_api_requests") or 0)

    entries_meta = []
    for e in entries:
        rt: KickbaseRuntimeData = e.runtime_data
        u = (rt.account.data or {}).get("user") or {}
        entries_meta.append(
            {
                "entry_id": e.entry_id,
                "title": e.title,
                "user_name": u.get("name", e.title),
                "user_avatar": u.get("avatar"),
            }
        )

    return {
        "configured": True,
        "entries": entries_meta,
        "active_entry_id": selected_entry.entry_id,
        "user": account_data.get("user") or {},
        "enabled_modules": sorted(runtime.enabled_modules),
        "primary_league_id": runtime.primary_league_id,
        "selected_league_id": selected_league_id,
        "leagues": leagues_meta,
        "league_data": league_data,
        "db_stats": db_stats,
        "last_sync_at": last_sync_at,
        "last_api_requests": last_api_requests,
        MODULE_NEWS_PREDICTIONS: runtime.news_predictions.data if runtime.news_predictions else None,
        MODULE_CHALLENGES: runtime.challenges.data if runtime.challenges else None,
        "event_types": account_data.get("event_types") or {},
        "competitions": account_data.get("competitions") or {},
        "market_value_timeframe": runtime.market_value_timeframe,
    }


@callback
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register all Kickbase WebSocket commands once."""
    websocket_api.async_register_command(hass, ws_get_snapshot)
    websocket_api.async_register_command(hass, ws_get_player_detail)
    websocket_api.async_register_command(hass, ws_get_manager_detail)
    websocket_api.async_register_command(hass, ws_query_local_players)
    websocket_api.async_register_command(hass, ws_get_db_stats)
    websocket_api.async_register_command(hass, ws_get_match_detail)
    websocket_api.async_register_command(hass, ws_get_news_item)
    websocket_api.async_register_command(hass, ws_search_players)
    websocket_api.async_register_command(hass, ws_get_challenge_detail)
    websocket_api.async_register_command(hass, ws_refresh)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "kickbase/get_snapshot",
        vol.Optional("entry_id"): str,
        vol.Optional("league_id"): str,
    }
)
@callback
def ws_get_snapshot(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return full modular snapshot for UI cards and sidebar panel."""
    try:
        payload = _build_snapshot_payload(
            hass,
            entry_id=msg.get("entry_id"),
            league_id=msg.get("league_id"),
        )
        connection.send_result(msg["id"], payload)
    except ValueError as err:
        connection.send_error(msg["id"], "not_found", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "kickbase/get_player_detail",
        vol.Required("league_id"): str,
        vol.Required("player_id"): str,
        vol.Optional("entry_id"): str,
        vol.Optional("timeframe"): int,
        vol.Optional("force_refresh"): bool,
    }
)
@websocket_api.async_response
async def ws_get_player_detail(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Read player details, MV curve & status history from local SQLite first (0 API calls)."""
    try:
        _, runtime = _resolve_runtime(
            hass, entry_id=msg.get("entry_id"), league_id=msg["league_id"]
        )
        league_id = msg["league_id"]
        player_id = str(msg["player_id"])
        requested_tf = msg.get("timeframe")
        timeframe = int(requested_tf) if requested_tf else runtime.market_value_timeframe
        force_refresh = bool(msg.get("force_refresh", False))

        # 1. Serve directly from local SQLite database unless caller forces a live refresh
        if not force_refresh:
            local_data = await runtime.store.async_get_player_detail(
                league_id,
                player_id,
                days=int(requested_tf) if requested_tf else None,
            )
            if local_data is not None:
                connection.send_result(msg["id"], local_data)
                return

        # 2. On-demand API fallback (e.g. for an unowned search result not in bulk scope)
        async def _fetch() -> dict[str, Any]:
            ibp = runtime.api.client.image_base_url
            details, mv_raw, perf_raw, transfers_raw, history_raw = await asyncio.gather(
                runtime.api.market.get_player_details(league_id, player_id),
                runtime.api.market.get_player_market_value(league_id, player_id, timeframe),
                runtime.api.market.get_player_performance(league_id, player_id),
                runtime.api.market.get_player_transfers(league_id, player_id),
                runtime.api.market.get_player_transfer_history(league_id, player_id),
            )
            norm = normalize_player(details if isinstance(details, dict) else {}, ibp)
            norm["season_match_count"] = details.get("smc") if isinstance(details, dict) else None
            norm["matchday_summaries"] = details.get("mdsum", []) if isinstance(details, dict) else []
            norm["status_text"] = details.get("stxt") if isinstance(details, dict) else None
            norm["ligainsider_url"] = (
                resolve_image_url(details.get("plpurl"), ibp)
                if isinstance(details, dict)
                else None
            )
            norm["prob_history"] = details.get("ph", []) if isinstance(details, dict) else []
            mv_series = normalize_market_value_series(mv_raw if isinstance(mv_raw, dict) else {})
            perf_list = (perf_raw.get("it") or []) if isinstance(perf_raw, dict) else []
            transfers_dict = transfers_raw if isinstance(transfers_raw, dict) else {}

            history_items = []
            for h in (history_raw.get("it") or []) if isinstance(history_raw, dict) else []:
                history_items.append(
                    {
                        "user_id": str(h.get("u", "")) if h.get("u") else None,
                        "user_name": h.get("unm") or "Kickbase",
                        "user_avatar": resolve_image_url(h.get("uim"), ibp),
                        "date": h.get("dt"),
                        "price": h.get("trp", 0),
                        "type": h.get("t"),
                    }
                )

            return {
                "from_local_db": False,
                "player": norm,
                "market_value": mv_series,
                "status_history": [],
                "performance": perf_list,
                "transfers": transfers_dict,
                "transfer_history": history_items,
            }

        data = await runtime.cache.get_or_fetch(
            f"player:{league_id}:{player_id}:{timeframe}",
            _fetch,
            ttl=600,
            force=force_refresh,
        )
        connection.send_result(msg["id"], data)
    except (ValueError, KickbaseError) as err:
        connection.send_error(msg["id"], "kickbase_error", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "kickbase/get_manager_detail",
        vol.Required("league_id"): str,
        vol.Required("manager_id"): str,
        vol.Optional("entry_id"): str,
        vol.Optional("force_refresh"): bool,
    }
)
@websocket_api.async_response
async def ws_get_manager_detail(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Serve rival manager dashboard, squad & transfers from local SQLite first."""
    try:
        _, runtime = _resolve_runtime(
            hass, entry_id=msg.get("entry_id"), league_id=msg["league_id"]
        )
        league_id = msg["league_id"]
        manager_id = str(msg["manager_id"])
        force_refresh = bool(msg.get("force_refresh", False))

        if not force_refresh:
            local_mgr = await runtime.store.async_get_manager_detail(league_id, manager_id)
            if local_mgr is not None:
                connection.send_result(msg["id"], local_mgr)
                return

        async def _fetch() -> dict[str, Any]:
            ibp = runtime.api.client.image_base_url
            dash, squad, perf, transfers = await asyncio.gather(
                runtime.api.managers.get_manager_dashboard(league_id, manager_id),
                runtime.api.managers.get_manager_squad(league_id, manager_id),
                runtime.api.managers.get_manager_performance(league_id, manager_id),
                runtime.api.managers.get_manager_transfers(league_id, manager_id),
            )
            squad_players = [
                normalize_player(p, ibp)
                for p in ((squad.get("it") or []) if isinstance(squad, dict) else [])
            ]
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
                for t in ((transfers.get("it") or []) if isinstance(transfers, dict) else [])
            ]
            return {
                "from_local_db": False,
                "dashboard": {
                    "id": str(dash.get("u", manager_id)) if isinstance(dash, dict) else manager_id,
                    "name": dash.get("unm") if isinstance(dash, dict) else "Manager",
                    "avatar": resolve_image_url(dash.get("uim"), ibp)
                    if isinstance(dash, dict)
                    else None,
                    "rank": dash.get("pl") if isinstance(dash, dict) else 0,
                    "average_points": dash.get("ap") if isinstance(dash, dict) else 0,
                    "total_points": dash.get("tp") if isinstance(dash, dict) else 0,
                    "matchday_wins": dash.get("mdw") if isinstance(dash, dict) else 0,
                    "team_value": dash.get("tv") if isinstance(dash, dict) else 0,
                    "profit": dash.get("prft") if isinstance(dash, dict) else 0,
                },
                "squad": squad_players,
                "performance": (perf.get("it") or []) if isinstance(perf, dict) else [],
                "transfers": transfer_list,
            }

        data = await runtime.cache.get_or_fetch(
            f"manager:{league_id}:{manager_id}",
            _fetch,
            ttl=300,
            force=force_refresh,
        )
        connection.send_result(msg["id"], data)
    except (ValueError, KickbaseError) as err:
        connection.send_error(msg["id"], "kickbase_error", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "kickbase/query_local_players",
        vol.Required("league_id"): str,
        vol.Optional("entry_id"): str,
        vol.Optional("query"): str,
        vol.Optional("scope"): str,
        vol.Optional("status_severity"): str,
        vol.Optional("limit"): int,
    }
)
@websocket_api.async_response
async def ws_query_local_players(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Query locally cached SQLite player database without Kickbase API requests."""
    try:
        _, runtime = _resolve_runtime(
            hass, entry_id=msg.get("entry_id"), league_id=msg["league_id"]
        )
        league_id = msg["league_id"]
        players, stats = await asyncio.gather(
            runtime.store.async_query_players(
                league_id,
                query=str(msg.get("query") or ""),
                scope=msg.get("scope"),
                status_severity=msg.get("status_severity"),
                limit=int(msg.get("limit") or 120),
            ),
            runtime.store.async_get_stats(league_id),
        )
        connection.send_result(
            msg["id"],
            {"from_local_db": True, "players": players, "stats": stats},
        )
    except ValueError as err:
        connection.send_error(msg["id"], "not_found", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "kickbase/get_db_stats",
        vol.Optional("league_id"): str,
        vol.Optional("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_get_db_stats(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return local SQLite database metrics and recent sync runs."""
    try:
        _, runtime = _resolve_runtime(
            hass, entry_id=msg.get("entry_id"), league_id=msg.get("league_id")
        )
        stats = await runtime.store.async_get_stats(msg.get("league_id"))
        connection.send_result(msg["id"], stats)
    except ValueError as err:
        connection.send_error(msg["id"], "not_found", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "kickbase/get_match_detail",
        vol.Required("match_id"): str,
        vol.Optional("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_get_match_detail(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Fetch match lineups, scores, and live events timeline."""
    try:
        _, runtime = _resolve_runtime(hass, entry_id=msg.get("entry_id"))
        match_id = msg["match_id"]

        async def _fetch() -> dict[str, Any]:
            ibp = runtime.api.client.image_base_url
            raw = await runtime.api.competitions.get_match_details(match_id)
            ev_map = (runtime.account.data or {}).get("event_types") or {}
            events = []
            for ev in (raw.get("events") or []) if isinstance(raw, dict) else []:
                ke = ev.get("ke")
                events.append(
                    {
                        "player_id": str(ev.get("pi", "")),
                        "player_name": ev.get("pn"),
                        "team_id": str(ev.get("tid", "")),
                        "event_code": ke,
                        "event_label": ev_map.get(ke) or ev_map.get(str(ke)) or f"Event #{ke}",
                        "minute": ev.get("mt"),
                        "image": resolve_image_url(ev.get("pim"), ibp),
                        "replaced_player": ev.get("rev"),
                    }
                )
            return {
                "match_id": match_id,
                "team1_id": str(raw.get("t1", "")),
                "team2_id": str(raw.get("t2", "")),
                "team1_name": raw.get("t1n") or raw.get("t1sy") or str(raw.get("t1", "")),
                "team2_name": raw.get("t2n") or raw.get("t2sy") or str(raw.get("t2", "")),
                "team1_short": raw.get("t1sy"),
                "team2_short": raw.get("t2sy"),
                "team1_goals": raw.get("t1g", 0),
                "team2_goals": raw.get("t2g", 0),
                "team1_image": resolve_image_url(raw.get("t1im"), ibp),
                "team2_image": resolve_image_url(raw.get("t2im"), ibp),
                "minute": raw.get("mtd") or raw.get("mt"),
                "date": raw.get("md"),
                "is_live": bool(raw.get("il", False)),
                "team1_lineup": [normalize_player(p, ibp) for p in (raw.get("t1lp") or [])],
                "team1_bench": [normalize_player(p, ibp) for p in (raw.get("t1nlp") or [])],
                "team2_lineup": [normalize_player(p, ibp) for p in (raw.get("t2lp") or [])],
                "team2_bench": [normalize_player(p, ibp) for p in (raw.get("t2nlp") or [])],
                "events": events,
            }

        data = await runtime.cache.get_or_fetch(f"match:{match_id}", _fetch, ttl=60)
        connection.send_result(msg["id"], data)
    except (ValueError, KickbaseError) as err:
        connection.send_error(msg["id"], "kickbase_error", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "kickbase/get_news_item",
        vol.Required("item_id"): str,
        vol.Optional("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_get_news_item(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Fetch full Kickbase news article (sanitized HTML)."""
    try:
        _, runtime = _resolve_runtime(hass, entry_id=msg.get("entry_id"))
        item_id = msg["item_id"]

        async def _fetch() -> dict[str, Any]:
            ibp = runtime.api.client.image_base_url
            raw = await runtime.api.base_news.get_item_detail(item_id)
            html_content = raw.get("cnt", "") if isinstance(raw, dict) else ""
            safe_html = _SCRIPT_TAG_RE.sub("", html_content)
            return {
                "id": item_id,
                "title": raw.get("ti") if isinstance(raw, dict) else "",
                "label": raw.get("rl") if isinstance(raw, dict) else "",
                "date": raw.get("dt") if isinstance(raw, dict) else None,
                "image": resolve_image_url(raw.get("ci"), ibp) if isinstance(raw, dict) else None,
                "html": safe_html,
            }

        data = await runtime.cache.get_or_fetch(f"news:{item_id}", _fetch, ttl=3600)
        connection.send_result(msg["id"], data)
    except (ValueError, KickbaseError) as err:
        connection.send_error(msg["id"], "kickbase_error", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "kickbase/search_players",
        vol.Required("competition_id"): str,
        vol.Required("query"): str,
        vol.Optional("league_id"): str,
        vol.Optional("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_search_players(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Search players across a competition (checks local DB first when offline/online)."""
    try:
        _, runtime = _resolve_runtime(
            hass, entry_id=msg.get("entry_id"), league_id=msg.get("league_id")
        )
        ibp = runtime.api.client.image_base_url
        res = await runtime.api.competitions.search_players(
            msg["competition_id"],
            query=msg["query"],
            league_id=msg.get("league_id"),
            max_items=25,
        )
        players = [
            normalize_player(p, ibp)
            for p in ((res.get("it") or []) if isinstance(res, dict) else [])
        ]
        connection.send_result(msg["id"], {"players": players})
    except (ValueError, KickbaseError) as err:
        connection.send_error(msg["id"], "kickbase_error", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "kickbase/get_challenge_detail",
        vol.Required("challenge_id"): str,
        vol.Optional("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_get_challenge_detail(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Fetch detailed challenge standings, top10, and livepitch."""
    try:
        _, runtime = _resolve_runtime(hass, entry_id=msg.get("entry_id"))
        cid = msg["challenge_id"]

        async def _fetch() -> dict[str, Any]:
            ibp = runtime.api.client.image_base_url
            profile, table, top10, livepitch = await asyncio.gather(
                runtime.api.challenges.get_challenge_profile(cid),
                runtime.api.challenges.get_challenge_table(cid),
                runtime.api.challenges.get_challenge_top10(cid),
                runtime.api.challenges.get_challenge_livepitch(cid),
            )
            return {
                "id": cid,
                "profile": profile,
                "table": table,
                "top10": top10,
                "live_points": livepitch.get("p", 0) if isinstance(livepitch, dict) else 0,
                "lineup": [
                    normalize_player(p, ibp)
                    for p in ((livepitch.get("lp") or []) if isinstance(livepitch, dict) else [])
                ],
            }

        data = await runtime.cache.get_or_fetch(f"challenge:{cid}", _fetch, ttl=120)
        connection.send_result(msg["id"], data)
    except (ValueError, KickbaseError) as err:
        connection.send_error(msg["id"], "kickbase_error", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "kickbase/refresh",
        vol.Optional("entry_id"): str,
        vol.Optional("league_id"): str,
        vol.Optional("module"): str,
        vol.Optional("force_details"): bool,
    }
)
@websocket_api.async_response
async def ws_refresh(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Manually trigger consolidated sync or global module refresh and return snapshot."""
    try:
        entry, runtime = _resolve_runtime(
            hass, entry_id=msg.get("entry_id"), league_id=msg.get("league_id")
        )
        target_league = msg.get("league_id") or runtime.primary_league_id
        module = msg.get("module")
        force_details = bool(msg.get("force_details", False))
        tasks = []

        if module == MODULE_NEWS_PREDICTIONS and runtime.news_predictions is not None:
            tasks.append(runtime.news_predictions.async_request_refresh())
        elif module == MODULE_CHALLENGES and runtime.challenges is not None:
            tasks.append(runtime.challenges.async_request_refresh())
        elif target_league in runtime.leagues:
            lset = runtime.leagues[target_league]
            if lset.sync is not None:
                tasks.append(lset.sync.async_trigger_sync(force_full_details=force_details))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        payload = _build_snapshot_payload(
            hass, entry_id=entry.entry_id, league_id=target_league
        )
        connection.send_result(msg["id"], payload)
    except ValueError as err:
        connection.send_error(msg["id"], "kickbase_error", str(err))
