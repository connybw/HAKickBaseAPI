"""The Kickbase Home Assistant integration (modular, read-only)."""

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
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KickbaseApi
from .const import (
    ALL_MODULES,
    CONF_DEFAULT_COMPETITION_ID,
    CONF_EMAIL,
    CONF_ENABLE_SIDEBAR_PANEL,
    CONF_LEAGUES,
    CONF_MARKET_VALUE_TIMEFRAME,
    CONF_MODULES,
    CONF_PASSWORD,
    CONF_PRIMARY_LEAGUE,
    CONF_SCAN_INTERVALS,
    DEFAULT_COMPETITION_ID,
    DEFAULT_ENABLED_MODULES,
    DEFAULT_INTERVALS,
    DEFAULT_MARKET_VALUE_TIMEFRAME,
    DOMAIN,
    MODULE_CHALLENGES,
    MODULE_FEED_ACHIEVEMENTS,
    MODULE_LEAGUE_OVERVIEW,
    MODULE_LIVE_MATCHDAY,
    MODULE_MARKET_TRANSFERS,
    MODULE_NEWS_PREDICTIONS,
    MODULE_SQUAD_LINEUP,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL_PATH,
    STATIC_URL_PATH,
    VERSION,
)
from .coordinators import KickbaseRuntimeData, LeagueCoordinatorSet
from .coordinators.account import AccountCoordinator
from .coordinators.global_modules import ChallengesCoordinator, NewsPredictionsCoordinator
from .coordinators.league import (
    FeedAchievementsCoordinator,
    LeagueOverviewCoordinator,
    LiveMatchdayCoordinator,
    MarketTransfersCoordinator,
    SquadLineupCoordinator,
)
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
    """Serve modular Lovelace cards & panel assets and register extra JS once."""
    if hass.data.get(_FRONTEND_REGISTERED_KEY):
        return

    frontend_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                url_path=STATIC_URL_PATH,
                path=str(frontend_dir),
                cache_headers=False,
            )
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


def _async_ensure_services(hass: HomeAssistant) -> None:
    """Register read-only Kickbase services once."""
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
            for lid, lset in rt.leagues.items():
                if target_league and lid != target_league:
                    continue
                if target_module:
                    mapping = {
                        MODULE_LEAGUE_OVERVIEW: lset.overview,
                        MODULE_SQUAD_LINEUP: lset.squad_lineup,
                        MODULE_MARKET_TRANSFERS: lset.market_transfers,
                        MODULE_LIVE_MATCHDAY: lset.live_matchday,
                        MODULE_FEED_ACHIEVEMENTS: lset.feed_achievements,
                    }
                    if coord := mapping.get(target_module):
                        tasks.append(coord.async_request_refresh())
                else:
                    for coord in lset.active_coordinators():
                        tasks.append(coord.async_request_refresh())
            if (not target_module or target_module == MODULE_NEWS_PREDICTIONS) and rt.news_predictions:
                tasks.append(rt.news_predictions.async_request_refresh())
            if (not target_module or target_module == MODULE_CHALLENGES) and rt.challenges:
                tasks.append(rt.challenges.async_request_refresh())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

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
    timeframe = int(options.get(CONF_MARKET_VALUE_TIMEFRAME, DEFAULT_MARKET_VALUE_TIMEFRAME))

    session = async_get_clientsession(hass)
    api = KickbaseApi(session, email, password)

    # 1. Global AccountCoordinator (handles initial login, competitions, event types & league discovery)
    account_coord = AccountCoordinator(
        hass, entry, api, update_seconds=int(intervals.get("account", 3600))
    )
    await account_coord.async_config_entry_first_refresh()

    account_data = account_coord.data or {}
    user_id = str((account_data.get("user") or {}).get("id") or "")
    discovered_leagues = account_data.get("leagues") or {}

    configured_leagues = list(options.get(CONF_LEAGUES) or [])
    if not configured_leagues:
        configured_leagues = list(discovered_leagues.keys())

    primary_league_id = str(options.get(CONF_PRIMARY_LEAGUE) or "")
    if primary_league_id not in configured_leagues and configured_leagues:
        primary_league_id = configured_leagues[0]

    runtime = KickbaseRuntimeData(
        api=api,
        account=account_coord,
        enabled_modules=enabled_modules,
        league_ids=configured_leagues,
        primary_league_id=primary_league_id,
        market_value_timeframe=timeframe,
    )

    # 2. Instantiate modular per-league coordinators ONLY for enabled modules
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

        if MODULE_LEAGUE_OVERVIEW in enabled_modules:
            lset.overview = LeagueOverviewCoordinator(
                hass,
                entry,
                api,
                lid,
                user_id,
                update_seconds=int(intervals[MODULE_LEAGUE_OVERVIEW]),
            )
            first_refresh_tasks.append(lset.overview.async_config_entry_first_refresh())

        if MODULE_SQUAD_LINEUP in enabled_modules:
            lset.squad_lineup = SquadLineupCoordinator(
                hass,
                entry,
                api,
                lid,
                update_seconds=int(intervals[MODULE_SQUAD_LINEUP]),
            )
            first_refresh_tasks.append(lset.squad_lineup.async_config_entry_first_refresh())

        if MODULE_MARKET_TRANSFERS in enabled_modules:
            lset.market_transfers = MarketTransfersCoordinator(
                hass,
                entry,
                api,
                lid,
                update_seconds=int(intervals[MODULE_MARKET_TRANSFERS]),
            )
            first_refresh_tasks.append(lset.market_transfers.async_config_entry_first_refresh())

        if MODULE_LIVE_MATCHDAY in enabled_modules:
            lset.live_matchday = LiveMatchdayCoordinator(
                hass,
                entry,
                api,
                lid,
                user_id,
                comp_id,
                idle_seconds=int(intervals[MODULE_LIVE_MATCHDAY]),
            )
            first_refresh_tasks.append(lset.live_matchday.async_config_entry_first_refresh())

        if MODULE_FEED_ACHIEVEMENTS in enabled_modules:
            lset.feed_achievements = FeedAchievementsCoordinator(
                hass,
                entry,
                api,
                lid,
                update_seconds=int(intervals[MODULE_FEED_ACHIEVEMENTS]),
            )
            first_refresh_tasks.append(lset.feed_achievements.async_config_entry_first_refresh())

        runtime.leagues[lid] = lset

    # 3. Optional Global Module Coordinators
    if MODULE_NEWS_PREDICTIONS in enabled_modules:
        runtime.news_predictions = NewsPredictionsCoordinator(
            hass,
            entry,
            api,
            competition_ids or [DEFAULT_COMPETITION_ID],
            update_seconds=int(intervals[MODULE_NEWS_PREDICTIONS]),
        )
        first_refresh_tasks.append(runtime.news_predictions.async_config_entry_first_refresh())

    if MODULE_CHALLENGES in enabled_modules:
        runtime.challenges = ChallengesCoordinator(
            hass,
            entry,
            api,
            update_seconds=int(intervals[MODULE_CHALLENGES]),
        )
        first_refresh_tasks.append(runtime.challenges.async_config_entry_first_refresh())

    if first_refresh_tasks:
        await asyncio.gather(*first_refresh_tasks)

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
        entry.runtime_data = None  # type: ignore[assignment]
        _sync_sidebar_panel(hass)
    return unload_ok
