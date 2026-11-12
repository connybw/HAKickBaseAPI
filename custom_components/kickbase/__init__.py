"""The Kickbase Home Assistant integration (consolidated hourly sync, local DB, read-only)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KickbaseApi
from .const import (
    ALL_MODULES,
    CONF_ADAPTIVE_LIVE_POLLING,
    CONF_CACHE_PHOTOS,
    CONF_DEFAULT_COMPETITION_ID,
    CONF_EMAIL,
    CONF_ENABLE_SIDEBAR_PANEL,
    CONF_FETCH_PLAYER_DETAILS,
    CONF_LEAGUES,
    CONF_MARKET_VALUE_TIMEFRAME,
    CONF_MODULES,
    CONF_PASSWORD,
    CONF_PRIMARY_LEAGUE,
    CONF_SCAN_INTERVALS,
    CONF_SYNC_INTERVAL,
    DEFAULT_COMPETITION_ID,
    DEFAULT_ENABLED_MODULES,
    DEFAULT_INTERVALS,
    DEFAULT_MARKET_VALUE_TIMEFRAME,
    DEFAULT_SYNC_INTERVAL_SECONDS,
    DOMAIN,
    MODULE_CHALLENGES,
    MODULE_NEWS_PREDICTIONS,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL_PATH,
    STATIC_PHOTOS_URL_PATH,
    STATIC_URL_PATH,
    VERSION,
)
from .coordinators import KickbaseRuntimeData, LeagueCoordinatorSet
from .coordinators.account import AccountCoordinator
from .coordinators.global_modules import ChallengesCoordinator, NewsPredictionsCoordinator
from .coordinators.league import LeagueSyncCoordinator
from .storage import KickbaseLocalStore
from .websocket_api import async_register_websocket_commands

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.IMAGE,
]

type KickbaseConfigEntry = ConfigEntry[KickbaseRuntimeData]

_FRONTEND_REGISTERED_KEY = f"{DOMAIN}_frontend_registered"
_PANEL_REGISTERED_KEY = f"{DOMAIN}_panel_registered"
_SERVICES_REGISTERED_KEY = f"{DOMAIN}_services_registered"


async def _async_ensure_frontend_assets(hass: HomeAssistant) -> None:
    """Serve modular Lovelace cards, panel assets & local cached photos once."""
    if hass.data.get(_FRONTEND_REGISTERED_KEY):
        return

    frontend_dir = Path(__file__).parent / "frontend"
    photos_dir = Path(hass.config.path("kickbase_data")) / "photos"
    await hass.async_add_executor_job(
        lambda: photos_dir.mkdir(parents=True, exist_ok=True)
    )

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                url_path=STATIC_URL_PATH,
                path=str(frontend_dir),
                cache_headers=False,
            ),
            StaticPathConfig(
                url_path=STATIC_PHOTOS_URL_PATH,
                path=str(photos_dir),
                cache_headers=True,
            ),
        ]
    )
    frontend.add_extra_js_url(
        hass, f"{STATIC_URL_PATH}/kickbase-cards.js?v={VERSION}"
    )
    async_register_websocket_commands(hass)
    hass.data[_FRONTEND_REGISTERED_KEY] = True


def _sync_sidebar_panel(hass: HomeAssistant) -> None:
    """Register or remove the built-in Kickbase sidebar panel depending on active entries."""
    wants_panel = any(
        entry.options.get(CONF_ENABLE_SIDEBAR_PANEL, True)
        for entry in hass.config_entries.async_entries(DOMAIN)
        if getattr(entry, "runtime_data", None) is not None
    )
    is_registered = bool(hass.data.get(_PANEL_REGISTERED_KEY, False))

    if wants_panel and not is_registered:
        frontend.async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            frontend_url_path=PANEL_URL_PATH,
            require_admin=False,
            config={
                "_panel_custom": {
                    "name": "kickbase-panel",
                    "embed_iframe": False,
                    "trust_external": False,
                    "module_url": f"{STATIC_URL_PATH}/kickbase-panel.js?v={VERSION}",
                }
            },
        )
        hass.data[_PANEL_REGISTERED_KEY] = True
    elif not wants_panel and is_registered:
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
        hass.data[_PANEL_REGISTERED_KEY] = False


def _resolve_service_runtime(
    hass: HomeAssistant, league_id: str | None = None
) -> tuple[KickbaseRuntimeData, str] | None:
    """Find the active KickbaseRuntimeData and league_id for local DB service calls."""
    loaded = [
        entry.runtime_data
        for entry in hass.config_entries.async_entries(DOMAIN)
        if getattr(entry, "runtime_data", None) is not None
    ]
    if not loaded:
        return None
    if league_id:
        for rt in loaded:
            if league_id in rt.leagues:
                return rt, league_id
        return loaded[0], league_id
    rt = loaded[0]
    lid = rt.primary_league_id or next(iter(rt.leagues.keys()), "")
    return rt, lid


def _async_ensure_services(hass: HomeAssistant) -> None:
    """Register read-only Kickbase sync and local-DB query services once."""
    if hass.data.get(_SERVICES_REGISTERED_KEY):
        return

    async def _handle_refresh(call: ServiceCall) -> None:
        target_league = call.data.get("league_id")
        target_module = call.data.get("module")
        tasks = []
        for entry in hass.config_entries.async_entries(DOMAIN):
            rt: KickbaseRuntimeData | None = getattr(entry, "runtime_data", None)
            if rt is None:
                continue
            if target_module not in (MODULE_NEWS_PREDICTIONS, MODULE_CHALLENGES):
                for lid, lset in rt.leagues.items():
                    if target_league and lid != target_league:
                        continue
                    if lset.sync is not None:
                        tasks.append(lset.sync.async_trigger_sync())
            if (not target_module or target_module == MODULE_NEWS_PREDICTIONS) and rt.news_predictions:
                tasks.append(rt.news_predictions.async_trigger_sync())
            if (not target_module or target_module == MODULE_CHALLENGES) and rt.challenges:
                tasks.append(rt.challenges.async_trigger_sync())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _handle_sync_database(call: ServiceCall) -> None:
        target_league = call.data.get("league_id")
        force_details = bool(call.data.get("force_details", False))
        tasks = []
        for entry in hass.config_entries.async_entries(DOMAIN):
            rt: KickbaseRuntimeData | None = getattr(entry, "runtime_data", None)
            if rt is None:
                continue
            for lid, lset in rt.leagues.items():
                if target_league and lid != target_league:
                    continue
                if lset.sync is not None:
                    tasks.append(
                        lset.sync.async_trigger_sync(force_full_details=force_details)
                    )
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _handle_get_player_history(call: ServiceCall) -> dict[str, Any]:
        resolved = _resolve_service_runtime(hass, call.data.get("league_id"))
        if resolved is None:
            return {"found": False, "error": "no_loaded_kickbase_entry"}
        rt, lid = resolved
        player_id = str(call.data["player_id"])
        days = call.data.get("days")
        data = await rt.store.async_get_player_detail(
            lid, player_id, days=int(days) if days is not None else None
        )
        if data is None:
            return {
                "found": False,
                "league_id": lid,
                "player_id": player_id,
            }
        return {"found": True, "league_id": lid, **data}

    async def _handle_query_local_players(call: ServiceCall) -> dict[str, Any]:
        resolved = _resolve_service_runtime(hass, call.data.get("league_id"))
        if resolved is None:
            return {"league_id": None, "count": 0, "players": []}
        rt, lid = resolved
        items = await rt.store.async_query_players(
            lid,
            query=str(call.data.get("query") or ""),
            scope=call.data.get("scope"),
            status_severity=call.data.get("status_severity"),
            limit=int(call.data.get("limit", 100)),
        )
        return {"league_id": lid, "count": len(items), "players": items}

    hass.services.async_register(
        DOMAIN,
        "refresh_data",
        _handle_refresh,
        schema=vol.Schema(
            {
                vol.Optional("league_id"): cv.string,
                vol.Optional("module"): vol.In(ALL_MODULES),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "sync_database",
        _handle_sync_database,
        schema=vol.Schema(
            {
                vol.Optional("league_id"): cv.string,
                vol.Optional("force_details", default=False): cv.boolean,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "get_player_history",
        _handle_get_player_history,
        schema=vol.Schema(
            {
                vol.Required("player_id"): cv.string,
                vol.Optional("league_id"): cv.string,
                vol.Optional("days"): vol.Coerce(int),
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "query_local_players",
        _handle_query_local_players,
        schema=vol.Schema(
            {
                vol.Optional("league_id"): cv.string,
                vol.Optional("query"): cv.string,
                vol.Optional("scope"): vol.In(["all", "my_squad", "market", "rival_squad", "scouted"]),
                vol.Optional("status_severity"): vol.In(["all", "issues", "ok", "warning", "danger"]),
                vol.Optional("limit", default=100): vol.Coerce(int),
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
    hass.data[_SERVICES_REGISTERED_KEY] = True


async def async_setup_entry(hass: HomeAssistant, entry: KickbaseConfigEntry) -> bool:
    """Set up Kickbase from a config entry."""
    await _async_ensure_frontend_assets(hass)
    _async_ensure_services(hass)

    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    options = entry.options

    enabled_modules = set(options.get(CONF_MODULES, DEFAULT_ENABLED_MODULES))
    intervals = dict(DEFAULT_INTERVALS)
    intervals.update(options.get(CONF_SCAN_INTERVALS) or {})
    sync_seconds = int(
        options.get(
            CONF_SYNC_INTERVAL,
            intervals.get("league_sync", DEFAULT_SYNC_INTERVAL_SECONDS),
        )
    )
    cache_photos = bool(options.get(CONF_CACHE_PHOTOS, True))
    fetch_player_details = bool(options.get(CONF_FETCH_PLAYER_DETAILS, True))
    adaptive_live_polling = bool(options.get(CONF_ADAPTIVE_LIVE_POLLING, False))
    timeframe = int(options.get(CONF_MARKET_VALUE_TIMEFRAME, DEFAULT_MARKET_VALUE_TIMEFRAME))

    store = KickbaseLocalStore(hass, Path(hass.config.path("kickbase_data")))
    await store.async_init()

    session = async_get_clientsession(hass)
    api = KickbaseApi(session, email, password)

    try:
        # 1. Global AccountCoordinator (handles initial login, competitions, event types & league discovery)
        account_coord = AccountCoordinator(
            hass,
            entry,
            api,
            update_seconds=int(intervals.get("account", sync_seconds)),
            store=store,
            cache_photos=cache_photos,
        )
        await account_coord.async_config_entry_first_refresh()

        account_data = account_coord.data or {}
        user_id = str((account_data.get("user") or {}).get("id") or "")
        discovered_leagues = account_data.get("leagues") or {}
        event_types_map = account_data.get("event_types") or {}

        configured_leagues = list(options.get(CONF_LEAGUES) or [])
        if not configured_leagues:
            configured_leagues = list(discovered_leagues.keys())

        primary_league_id = str(options.get(CONF_PRIMARY_LEAGUE) or "")
        if primary_league_id not in configured_leagues and configured_leagues:
            primary_league_id = configured_leagues[0]

        runtime = KickbaseRuntimeData(
            api=api,
            account=account_coord,
            store=store,
            enabled_modules=enabled_modules,
            league_ids=configured_leagues,
            primary_league_id=primary_league_id,
            market_value_timeframe=timeframe,
        )

        # 2. One consolidated hourly LeagueSyncCoordinator per selected league
        competition_ids: list[str] = []
        first_refresh_tasks = []

        for lid in configured_leagues:
            l_meta = discovered_leagues.get(lid) or {}
            lname = l_meta.get("name") or f"Liga {lid}"
            comp_id = str(
                l_meta.get("competition_id")
                or options.get(CONF_DEFAULT_COMPETITION_ID, DEFAULT_COMPETITION_ID)
            )
            if comp_id not in competition_ids:
                competition_ids.append(comp_id)

            lset = LeagueCoordinatorSet(
                league_id=lid,
                league_name=lname,
                competition_id=comp_id,
            )
            lset.sync = LeagueSyncCoordinator(
                hass,
                entry,
                api,
                store,
                league_id=lid,
                user_id=user_id,
                competition_id=comp_id,
                enabled_modules=enabled_modules,
                market_value_timeframe=timeframe,
                sync_seconds=sync_seconds,
                cache_photos=cache_photos,
                fetch_player_details=fetch_player_details,
                adaptive_live_polling=adaptive_live_polling,
                event_types_map=event_types_map,
            )
            first_refresh_tasks.append(lset.sync.async_config_entry_first_refresh())
            runtime.leagues[lid] = lset

        # 3. Optional Global Module Coordinators
        if MODULE_NEWS_PREDICTIONS in enabled_modules:
            runtime.news_predictions = NewsPredictionsCoordinator(
                hass,
                entry,
                api,
                competition_ids or [DEFAULT_COMPETITION_ID],
                update_seconds=int(intervals.get(MODULE_NEWS_PREDICTIONS, sync_seconds)),
                store=store,
                cache_photos=cache_photos,
            )
            first_refresh_tasks.append(runtime.news_predictions.async_config_entry_first_refresh())

        if MODULE_CHALLENGES in enabled_modules:
            runtime.challenges = ChallengesCoordinator(
                hass,
                entry,
                api,
                update_seconds=int(intervals.get(MODULE_CHALLENGES, sync_seconds)),
                store=store,
                cache_photos=cache_photos,
            )
            first_refresh_tasks.append(runtime.challenges.async_config_entry_first_refresh())

        if first_refresh_tasks:
            await asyncio.gather(*first_refresh_tasks)
    except Exception:
        await store.async_close()
        raise

    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _sync_sidebar_panel(hass)
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: KickbaseConfigEntry
) -> None:
    """Reload integration cleanly when user updates modular options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: KickbaseConfigEntry) -> bool:
    """Unload a Kickbase config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry.runtime_data.cache.clear()
        await entry.runtime_data.store.async_close()
        entry.runtime_data = None  # type: ignore[assignment]
        _sync_sidebar_panel(hass)
    return unload_ok
