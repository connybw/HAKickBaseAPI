"""End-to-end tests for consolidated hourly sync, local DB, photo cache, platforms & WebSockets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.ha_stubs import FakeClientSession, FakeResponse, install_stubs

install_stubs()

from homeassistant.components import frontend, websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.kickbase import async_setup_entry, async_unload_entry
from custom_components.kickbase.api import KickbaseApi
from custom_components.kickbase.binary_sensor import async_setup_entry as bs_setup
from custom_components.kickbase.calendar import async_setup_entry as cal_setup
from custom_components.kickbase.config_flow import KickbaseConfigFlow
from custom_components.kickbase.const import (
    ALL_MODULES,
    CONF_ADAPTIVE_LIVE_POLLING,
    CONF_CACHE_PHOTOS,
    CONF_EMAIL,
    CONF_ENABLE_PLAYER_ENTITIES,
    CONF_ENABLE_SIDEBAR_PANEL,
    CONF_FETCH_PLAYER_DETAILS,
    CONF_LEAGUES,
    CONF_MARKET_VALUE_TIMEFRAME,
    CONF_MODULES,
    CONF_PASSWORD,
    CONF_PRIMARY_LEAGUE,
    CONF_SYNC_INTERVAL,
    DEFAULT_SYNC_INTERVAL_SECONDS,
    EVENT_LIVE_PLAYER_EVENT,
    EVENT_NEGATIVE_BUDGET,
    EVENT_NEW_ACTIVITY,
    EVENT_PLAYER_STATUS_CHANGED,
    EVENT_SCOUTED_ON_MARKET,
    LIVE_MATCHDAY_ACTIVE_INTERVAL,
    MODULE_LEAGUE_OVERVIEW,
    MODULE_SQUAD_LINEUP,
    STATIC_PHOTOS_URL_PATH,
)
from custom_components.kickbase.coordinators.account import AccountCoordinator
from custom_components.kickbase.image import async_setup_entry as img_setup
from custom_components.kickbase.sensor import async_setup_entry as sensor_setup
from custom_components.kickbase.websocket_api import (
    ws_get_challenge_detail,
    ws_get_db_stats,
    ws_get_manager_detail,
    ws_get_match_detail,
    ws_get_news_item,
    ws_get_player_detail,
    ws_get_snapshot,
    ws_query_local_players,
    ws_refresh,
    ws_search_players,
)


def _seed_mock_kickbase_session(
    *,
    budget: int = 12500000,
    is_live: bool = True,
    scouted_on_market: bool = True,
) -> FakeClientSession:
    session = FakeClientSession()
    exp = (datetime.now(UTC) + timedelta(hours=12)).isoformat()
    lock_iso = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    match_iso = (datetime.now(UTC) + timedelta(days=1)).isoformat()

    session.add_route(
        "POST",
        "/v4/user/login",
        FakeResponse(
            200,
            {
                "tkn": "jwt_abc",
                "rtkn": "rtkn_abc",
                "tknex": exp,
                "u": {"id": "100", "name": "Chris", "email": "chris@example.com"},
                "srvl": [{"id": "2001", "name": "Champions Runde"}],
            },
        ),
    )
    session.add_route("GET", "/v4/config/version", FakeResponse(200, {"ibp": "https://kickbase.b-cdn.net"}))
    session.add_route("GET", "/v4/config", FakeResponse(200, {"ibp": "https://kickbase.b-cdn.net", "pturl": "https://kb/pts"}))
    session.add_route(
        "GET",
        "/v4/competitions",
        FakeResponse(200, {"it": [{"i": "1", "n": "Bundesliga", "cpim": "comp/1.png"}]}),
    )
    session.add_route(
        "GET",
        "/v4/live/eventtypes",
        FakeResponse(200, {"it": [{"i": 1, "ti": "Tor"}, {"i": 12, "ti": "Vorlage"}]}),
    )
    session.add_route(
        "GET",
        "/v4/user/me",
        FakeResponse(
            200,
            {
                "u": {
                    "id": "100",
                    "name": "Chris",
                    "email": "chris@example.com",
                    "notifications": 3,
                    "proExpiry": "2027-06-01T00:00:00Z",
                    "profile": "user/100.png",
                }
            },
        ),
    )
    session.add_route(
        "GET",
        "/v4/leagues/selection",
        FakeResponse(
            200,
            {
                "it": [
                    {
                        "i": "2001",
                        "n": "Champions Runde",
                        "cpi": "1",
                        "b": budget,
                        "tv": 145000000,
                        "pl": 2,
                        "un": 10,
                        "lpc": 11,
                        "adm": True,
                        "lim": "league/2001.png",
                    }
                ]
            },
        ),
    )
    session.add_route("GET", "/v4/leagues", FakeResponse(200, {"lins": []}))
    session.add_route("GET", "/v4/settings/subscriptionStatus", FakeResponse(200, {"active": True}))
    session.add_route(
        "GET",
        "/v4/refiner/identify",
        FakeResponse(200, {"userTraits": {"currentActiveSubscription": True}}),
    )

    # League overview
    session.add_route(
        "GET",
        "/v4/leagues/2001/overview",
        FakeResponse(
            200,
            {
                "lnm": "Champions Runde",
                "cpi": "1",
                "cpn": "Bundesliga",
                "lim": "league/2001.png",
                "mgc": 10,
                "btls": [
                    {"t": 1, "n": "Torjäger", "d": "Meiste Tore", "u": {"i": "101", "n": "Max"}}
                ],
            },
        ),
    )
    session.add_route("GET", "/v4/leagues/2001/me", FakeResponse(200, {"b": budget, "tpc": [{"tid": "2", "npt": 3}]}))
    session.add_route("GET", "/v4/leagues/2001/me/budget", FakeResponse(200, {"b": budget, "pbas": budget + 20000000, "bs": 1}))
    session.add_route(
        "GET",
        "/v4/leagues/2001/ranking",
        FakeResponse(
            200,
            {
                "sn": "2025/2026",
                "day": 21,
                "nd": 34,
                "il": is_live,
                "us": [
                    {"i": "101", "n": "Max", "sp": 18200, "mdp": 890, "tv": 152000000, "spl": 1, "mdpl": 2, "uim": "user/101.png"},
                    {"i": "100", "n": "Chris", "sp": 17950, "mdp": 1050, "tv": 145000000, "spl": 2, "mdpl": 1, "adm": True, "uim": "user/100.png"},
                ],
            },
        ),
    )
    session.add_route("GET", "/v4/leagues/2001/settings", FakeResponse(200, {"d": "Top Liga"}))

    # Squad & Lineup
    session.add_route(
        "GET",
        "/v4/leagues/2001/squad",
        FakeResponse(
            200,
            {
                "it": [
                    {
                        "i": "4577",
                        "fn": "Harry",
                        "ln": "Kane",
                        "tid": "2",
                        "pos": 4,
                        "st": 0,
                        "mvt": 1,
                        "mv": 72000000,
                        "tfhmvt": 350000,
                        "mvgl": 4500000,
                        "p": 1900,
                        "ap": 182,
                        "pim": "p/4577.png",
                    },
                    {
                        "i": "111",
                        "fn": "Manuel",
                        "ln": "Neuer",
                        "tid": "2",
                        "pos": 1,
                        "st": 1,
                        "mvt": 2,
                        "mv": 18000000,
                        "tfhmvt": -120000,
                        "mvgl": -500000,
                        "p": 980,
                        "ap": 102,
                        "pim": "p/111.png",
                    },
                ]
            },
        ),
    )
    session.add_route(
        "GET",
        "/v4/leagues/2001/lineup/overview",
        FakeResponse(
            200,
            {
                "t": "3-4-3",
                "mdln": 21,
                "lis": lock_iso,
                "lpc": 2,
                "clpc": 2,
                "cpte": True,
                "lp": [
                    {"i": "4577", "ln": "Kane", "tid": "2", "pos": 4, "st": 0, "mdst": 1, "ictp": True, "ap": 182},
                    {"i": "111", "ln": "Neuer", "tid": "2", "pos": 1, "st": 1, "mdst": 8, "ictp": False, "ap": 102},
                ],
            },
        ),
    )
    session.add_route(
        "GET",
        "/v4/leagues/2001/lineup/teams",
        FakeResponse(200, {"tms": [{"tid": "2", "tim": "team/fcb.png"}]}),
    )
    session.add_route(
        "GET",
        "/v4/leagues/2001/teamcenter/myeleven",
        FakeResponse(
            200,
            {
                "p": 1050,
                "lp": [{"i": "4577", "ln": "Kane", "pos": 4, "p": 320, "md": match_iso, "mi": "9901"}],
                "nlp": [],
            },
        ),
    )

    # Market & Scouted
    market_items = [
        {
            "i": "555",
            "fn": "Florian",
            "ln": "Wirtz",
            "pos": 3,
            "st": 0,
            "mv": 52000000,
            "prc": 52000000,
            "exs": 1200,
            "onm": "Kickbase",
            "ap": 165,
            "pim": "p/555.png",
        }
    ]
    if scouted_on_market:
        market_items.append(
            {
                "i": "777",
                "fn": "Jamal",
                "ln": "Musiala",
                "pos": 3,
                "st": 0,
                "mv": 61000000,
                "prc": 61500000,
                "exs": 4500,
                "onm": "Kickbase",
                "ap": 170,
                "pim": "p/777.png",
            }
        )
    session.add_route(
        "GET",
        "/v4/leagues/2001/market",
        FakeResponse(200, {"it": market_items, "mvud": lock_iso, "day": 21}),
    )
    session.add_route(
        "GET",
        "/v4/leagues/2001/scoutedplayers",
        FakeResponse(200, {"it": [{"i": "777", "fn": "Jamal", "ln": "Musiala", "pos": 3, "mv": 61000000}]}),
    )

    # Managers (both me=100 and rival=101, rival owns player 888!)
    session.add_route("GET", "/v4/leagues/2001/managers/100/dashboard", FakeResponse(200, {"u": "100", "unm": "Chris", "pl": 2, "tp": 17950}))
    session.add_route("GET", "/v4/leagues/2001/managers/100/squad", FakeResponse(200, {"it": []}))
    session.add_route("GET", "/v4/leagues/2001/managers/100/performance", FakeResponse(200, {"it": []}))
    session.add_route("GET", "/v4/leagues/2001/managers/100/transfer", FakeResponse(200, {"it": []}))

    session.add_route("GET", "/v4/leagues/2001/managers/101/dashboard", FakeResponse(200, {"u": "101", "unm": "Max", "pl": 1, "tp": 18200, "uim": "user/101.png"}))
    session.add_route("GET", "/v4/leagues/2001/managers/101/squad", FakeResponse(200, {"it": [{"i": "888", "fn": "Michael", "ln": "Olise", "tid": "2", "pos": 3, "st": 0, "mv": 58000000, "pim": "p/888.png"}]}))
    session.add_route("GET", "/v4/leagues/2001/managers/101/performance", FakeResponse(200, {"it": []}))
    session.add_route("GET", "/v4/leagues/2001/managers/101/transfer", FakeResponse(200, {"it": []}))

    # Per-player detail endpoints for all synced players (4577, 111, 555, 777, 888)
    for pid, ln, mv in (
        ("4577", "Kane", 72000000),
        ("111", "Neuer", 18000000),
        ("555", "Wirtz", 52000000),
        ("777", "Musiala", 61000000),
        ("888", "Olise", 58000000),
    ):
        session.add_route("GET", f"/v4/leagues/2001/players/{pid}", FakeResponse(200, {"i": pid, "ln": ln, "mv": mv, "st": 1 if pid == "111" else 0, "stxt": "Rücken" if pid == "111" else None}))
        session.add_route("GET", f"/v4/leagues/2001/players/{pid}/marketvalue/92", FakeResponse(200, {"trp": mv - 2000000, "prlo": 2000000, "it": [{"dt": 20100, "mv": mv - 1000000}]}))
        session.add_route("GET", f"/v4/leagues/2001/players/{pid}/performance", FakeResponse(200, {"it": []}))
        session.add_route("GET", f"/v4/leagues/2001/players/{pid}/transfers", FakeResponse(200, {"it": []}))
        session.add_route("GET", f"/v4/leagues/2001/players/{pid}/transferHistory", FakeResponse(200, {"it": [{"unm": "Chris", "trp": mv - 2000000}]}))

    # Photo binary CDN routes
    for path in ("/p/4577.png", "/p/111.png", "/p/555.png", "/p/777.png", "/p/888.png", "/team/fcb.png", "/user/100.png", "/user/101.png"):
        session.add_route("GET", path, FakeResponse(200, bytes_data=b"\x89PNGFAKE", headers={"Content-Type": "image/png"}))

    # Live Matchday
    session.add_route(
        "GET",
        "/v4/competitions/1/matchdays",
        FakeResponse(
            200,
            {
                "day": 21,
                "it": [
                    {
                        "day": 21,
                        "it": [
                            {
                                "mi": "9901",
                                "dt": match_iso,
                                "t1": "2",
                                "t2": "3",
                                "t1sy": "FCB",
                                "t2sy": "BVB",
                                "t1g": 2,
                                "t2g": 1,
                                "mtd": "67",
                                "st": 1 if is_live else 2,
                                "il": is_live,
                            }
                        ],
                    }
                ],
            },
        ),
    )
    session.add_route("GET", "/v4/competitions/1/table", FakeResponse(200, {"it": [{"tid": "2", "tn": "FC Bayern", "cpl": 1, "cp": 52, "mc": 21, "gd": 38}]}))
    session.add_route("GET", "/v4/competitions/1/ranking", FakeResponse(200, {"it": [{"tid": "2", "tn": "FC Bayern", "spl": 1, "sp": 28000, "mdp": 1400}]}))
    session.add_route("GET", "/v4/leagues/2001/users/100/teamcenter", FakeResponse(200, {"us": [{"i": "100", "unm": "Chris", "mdp": 1050, "pl": 1}]}))
    session.add_route(
        "GET",
        "/v4/matches/9901/details",
        FakeResponse(
            200,
            {
                "t1": "2",
                "t2": "3",
                "t1n": "FC Bayern",
                "t2n": "Borussia Dortmund",
                "t1g": 2,
                "t2g": 1,
                "il": is_live,
                "mtd": "67",
                "t1lp": [{"i": "4577", "ln": "Kane", "pos": 4}],
                "t2lp": [],
                "events": [{"pi": "4577", "pn": "Kane", "ke": 1, "mt": 42}],
            },
        ),
    )

    # Feed & Achievements
    session.add_route("GET", "/v4/leagues/2001/activitiesFeed", FakeResponse(200, {"af": [{"i": "act_1", "t": 15, "dt": match_iso, "coc": 2, "data": {"pn": "Kane"}}]}))
    session.add_route("GET", "/v4/leagues/2001/user/achievements", FakeResponse(200, {"it": [{"t": 1, "n": "1000er Club", "ac": 2, "ise": True}]}))

    # News & Predictions
    session.add_route("GET", "/v4/base/overview", FakeResponse(200, {"sect": []}))
    session.add_route("GET", "/v4/base/stage", FakeResponse(200, {"stg": [{"i": "st1", "ti": "Topspiel"}]}))
    session.add_route("GET", "/v4/base/news/1", FakeResponse(200, {"it": [{"i": "n1", "ti": "Kane trifft doppelt", "rl": "News", "dt": match_iso}]}))
    session.add_route("GET", "/v4/base/predictions/teams/1", FakeResponse(200, {"tms": [{"tid": "2", "tn": "FC Bayern", "plpim": "pred/fcb.png"}]}))
    session.add_route("GET", "/v4/base/items/n1", FakeResponse(200, {"ti": "Kane trifft doppelt", "cnt": "<p>Hallo</p><script>alert(1)</script>"}))

    # Challenges
    session.add_route("GET", "/v4/challenges/lobby/overview", FakeResponse(200, {"my": [{"ch": "ch1", "n": "Topspiel Challenge", "cpi": "1", "b": 150000000, "il": True, "uc": 500, "lpc": 11}]}))
    session.add_route("GET", "/v4/challenges/lobby/overview/live", FakeResponse(200, {"it": []}))
    session.add_route("GET", "/v4/challenges/lobby/profile", FakeResponse(200, {"n": "Saison 25/26", "skp": 420, "avskp": 120, "ap": 890, "dv": {"dvi": "3", "dvn": "Gold"}}))
    session.add_route("GET", "/v4/challenges/lobby/divisionLadder", FakeResponse(200, {"dvs": [{"dvi": "3", "dvn": "Gold", "bod": 800, "uc": 1200}]}))
    session.add_route("GET", "/v4/challenges/lobby/skillPoints/summary", FakeResponse(200, {"chs": []}))
    session.add_route("GET", "/v4/challenges/selection", FakeResponse(200, {"it": []}))
    session.add_route("GET", "/v4/challenges/ch1/profile", FakeResponse(200, {"n": "Topspiel Challenge"}))
    session.add_route("GET", "/v4/challenges/ch1/lineup/overview", FakeResponse(200, {"t": "4-4-2", "lp": []}))
    session.add_route("GET", "/v4/challenges/ch1/lineup/livepitch", FakeResponse(200, {"p": 760, "lp": []}))
    session.add_route("GET", "/v4/challenges/ch1/table", FakeResponse(200, {"it": []}))
    session.add_route("GET", "/v4/challenges/ch1/top10", FakeResponse(200, {"it": []}))

    # Search
    session.add_route("GET", "/v4/competitions/1/players/search", FakeResponse(200, {"it": [{"i": "4577", "fn": "Harry", "ln": "Kane", "pos": 4, "mv": 72000000}]}))

    return session


class TestKickbaseIntegration(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp_dirs: list[Path] = []

    def tearDown(self) -> None:
        for d in self._tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)

    def _new_hass(self) -> HomeAssistant:
        d = Path(tempfile.mkdtemp(prefix="kb_int_test_"))
        self._tmp_dirs.append(d)
        return HomeAssistant(d)

    async def test_config_and_options_flow(self) -> None:
        hass = self._new_hass()
        hass._test_session = _seed_mock_kickbase_session()

        flow = KickbaseConfigFlow()
        flow.hass = hass

        form1 = await flow.async_step_user()
        self.assertEqual(form1["step_id"], "user")

        step2 = await flow.async_step_user({CONF_EMAIL: "chris@example.com", CONF_PASSWORD: "secret"})
        self.assertEqual(step2["step_id"], "leagues")

        step3 = await flow.async_step_leagues({CONF_LEAGUES: ["2001"]})
        self.assertEqual(step3["step_id"], "modules")

        created = await flow.async_step_modules(
            {
                CONF_PRIMARY_LEAGUE: "2001",
                CONF_MODULES: [MODULE_LEAGUE_OVERVIEW, MODULE_SQUAD_LINEUP],
                CONF_ENABLE_SIDEBAR_PANEL: True,
                CONF_ENABLE_PLAYER_ENTITIES: True,
                CONF_CACHE_PHOTOS: True,
                CONF_FETCH_PLAYER_DETAILS: True,
                CONF_ADAPTIVE_LIVE_POLLING: False,
                CONF_SYNC_INTERVAL: 3600,
                CONF_MARKET_VALUE_TIMEFRAME: "180",
            }
        )
        self.assertEqual(created["type"], "create_entry")
        self.assertEqual(created["options"][CONF_MARKET_VALUE_TIMEFRAME], 180)
        self.assertEqual(created["options"][CONF_SYNC_INTERVAL], 3600)
        self.assertTrue(created["options"][CONF_CACHE_PHOTOS])

        entry = ConfigEntry(entry_id="e1", data=created["data"], options=created["options"])
        opt_flow = KickbaseConfigFlow.async_get_options_flow(entry)
        opt_flow.config_entry = entry
        opt_form = await opt_flow.async_step_init()
        self.assertEqual(opt_form["step_id"], "init")
        opt_done = await opt_flow.async_step_init(
            {
                CONF_MODULES: [MODULE_LEAGUE_OVERVIEW],
                CONF_MARKET_VALUE_TIMEFRAME: "365",
                CONF_SYNC_INTERVAL: 7200,
            }
        )
        self.assertEqual(opt_done["type"], "create_entry")
        self.assertEqual(opt_done["data"][CONF_MARKET_VALUE_TIMEFRAME], 365)
        self.assertEqual(opt_done["data"][CONF_SYNC_INTERVAL], 7200)

    async def test_modular_setup_with_consolidated_sync(self) -> None:
        hass = self._new_hass()
        hass._test_session = _seed_mock_kickbase_session(is_live=False)
        entry = ConfigEntry(
            entry_id="mod_only",
            data={CONF_EMAIL: "chris@example.com", CONF_PASSWORD: "secret"},
            options={
                CONF_LEAGUES: ["2001"],
                CONF_PRIMARY_LEAGUE: "2001",
                CONF_MODULES: [MODULE_LEAGUE_OVERVIEW],
                CONF_ENABLE_SIDEBAR_PANEL: False,
            },
        )
        hass.config_entries.add_entry(entry)

        ok = await async_setup_entry(hass, entry)
        self.assertTrue(ok)
        rt = entry.runtime_data
        self.assertIsNone(rt.news_predictions)
        self.assertIsNone(rt.challenges)
        lset = rt.leagues["2001"]
        self.assertIsNotNone(lset.sync)
        self.assertEqual(lset.sync.update_interval, timedelta(seconds=DEFAULT_SYNC_INTERVAL_SECONDS))
        self.assertIsNotNone(lset.sync.data[MODULE_LEAGUE_OVERVIEW])
        self.assertIsNone(lset.sync.data[MODULE_SQUAD_LINEUP])

        self.assertTrue(await async_unload_entry(hass, entry))

    async def test_full_hourly_sync_local_db_photo_cache_and_zero_api_websockets(self) -> None:
        frontend.panels.clear()
        frontend.extra_js_urls.clear()
        websocket_api.registered_commands.clear()

        hass = self._new_hass()
        session = _seed_mock_kickbase_session(budget=12500000, is_live=True, scouted_on_market=True)
        hass._test_session = session
        entry = ConfigEntry(
            entry_id="full_entry",
            data={CONF_EMAIL: "chris@example.com", CONF_PASSWORD: "secret"},
            options={
                CONF_LEAGUES: ["2001"],
                CONF_PRIMARY_LEAGUE: "2001",
                CONF_MODULES: list(ALL_MODULES),
                CONF_ENABLE_SIDEBAR_PANEL: True,
                CONF_ENABLE_PLAYER_ENTITIES: True,
                CONF_CACHE_PHOTOS: True,
                CONF_FETCH_PLAYER_DETAILS: True,
                CONF_ADAPTIVE_LIVE_POLLING: True,
                CONF_SYNC_INTERVAL: 3600,
                CONF_MARKET_VALUE_TIMEFRAME: 92,
            },
        )
        hass.config_entries.add_entry(entry)

        self.assertTrue(await async_setup_entry(hass, entry))
        rt = entry.runtime_data
        lset = rt.leagues["2001"]

        # Adaptive live polling switched to 60s when explicitly enabled & live
        self.assertEqual(lset.sync.update_interval, LIVE_MATCHDAY_ACTIVE_INTERVAL)

        # Panel & static routes (frontend + separate photos route)
        self.assertIn("kickbase", frontend.panels)
        self.assertTrue(any("kickbase-cards.js" in url for url in frontend.extra_js_urls))
        static_urls = {p["url_path"] for p in hass.http.static_paths}
        self.assertIn("/api/kickbase_static", static_urls)
        self.assertIn(STATIC_PHOTOS_URL_PATH, static_urls)

        # Verify all 5 players (my_squad: 4577, 111; market: 555, 777; rival_squad: 888) saved to local SQLite!
        db_stats = await rt.store.async_get_stats("2001")
        self.assertEqual(db_stats["players_count"], 5)
        self.assertEqual(db_stats["my_squad_count"], 2)
        self.assertEqual(db_stats["market_count"], 2)
        self.assertEqual(db_stats["rival_players_count"], 1)
        self.assertGreater(db_stats["photos_cached"], 0)
        self.assertEqual(db_stats["last_sync"]["photos_downloaded"], db_stats["photos_cached"])

        # 2nd sync MUST NOT re-download photos OR re-fetch already-synced MV history (<12h)
        req_before_2nd_sync = len(session.requests)
        session.set_route("GET", "/v4/leagues/2001/me/budget", FakeResponse(200, {"b": -450000, "pbas": 500000}))
        session.set_route(
            "GET",
            "/v4/matches/9901/details",
            FakeResponse(
                200,
                {
                    "t1": "2",
                    "t2": "3",
                    "t1n": "FC Bayern",
                    "t2n": "Borussia Dortmund",
                    "events": [
                        {"pi": "4577", "pn": "Kane", "ke": 1, "mt": 42},
                        {"pi": "4577", "pn": "Kane", "ke": 1, "mt": 78},
                    ],
                },
            ),
        )
        session.set_route(
            "GET",
            "/v4/leagues/2001/activitiesFeed",
            FakeResponse(200, {"af": [{"i": "act_2", "t": 15, "data": {"pn": "Wirtz"}}]}),
        )
        # Simulate Kane getting knocked (st=2) on 2nd sync -> emits EVENT_PLAYER_STATUS_CHANGED
        session.set_route(
            "GET",
            "/v4/leagues/2001/players/4577",
            FakeResponse(200, {"i": "4577", "ln": "Kane", "mv": 72500000, "st": 2, "stxt": "Sprunggelenk"}),
        )
        lset.sync._known_scouted_on_market = set()
        await lset.sync.async_request_refresh()

        reqs_2nd = session.requests[req_before_2nd_sync:]
        # Zero image downloads and zero marketvalue/92 backfill requests on 2nd sync!
        self.assertFalse(any(r["url"].endswith(".png") for r in reqs_2nd))
        self.assertFalse(any("/marketvalue/" in r["url"] for r in reqs_2nd))

        stats_after = await rt.store.async_get_stats("2001")
        self.assertEqual(stats_after["last_sync"]["photos_downloaded"], 0)

        # Verify all HA events fired
        event_names = {ev for ev, _ in hass.bus.events}
        self.assertIn(EVENT_NEGATIVE_BUDGET, event_names)
        self.assertIn(EVENT_LIVE_PLAYER_EVENT, event_names)
        self.assertIn(EVENT_NEW_ACTIVITY, event_names)
        self.assertIn(EVENT_SCOUTED_ON_MARKET, event_names)
        self.assertIn(EVENT_PLAYER_STATUS_CHANGED, event_names)

        # Verify platforms
        sensors: list[Any] = []
        await sensor_setup(hass, entry, sensors.extend)
        db_sensor = next(s for s in sensors if s.entity_description.key == "db_players_count")
        self.assertEqual(db_sensor.native_value, 5)
        self.assertEqual(db_sensor.extra_state_attributes["rival_players_count"], 1)

        kane_sensor = next(s for s in sensors if s._attr_unique_id.endswith("_player_4577"))
        self.assertEqual(kane_sensor.native_value, 72500000)
        self.assertEqual(kane_sensor.entity_picture, "/api/kickbase_photos/player_4577.png")

        bins: list[Any] = []
        await bs_setup(hass, entry, bins.extend)
        self.assertEqual(len(bins), 5)
        budget_neg_bs = next(b for b in bins if b.entity_description.key == "budget_negative")
        self.assertTrue(budget_neg_bs.is_on)

        cals: list[Any] = []
        await cal_setup(hass, entry, cals.extend)
        self.assertEqual(len(cals), 1)
        events = await cals[0].async_get_events(
            hass, datetime.now(UTC) - timedelta(days=1), datetime.now(UTC) + timedelta(days=5)
        )
        self.assertEqual(len(events), 2)

        imgs: list[Any] = []
        await img_setup(hass, entry, imgs.extend)
        self.assertEqual(len(imgs), 2)
        self.assertEqual(imgs[0].image_url, "https://kickbase.b-cdn.net/user/100.png")

        # Verify WebSocket commands serve player & manager details with ZERO API calls!
        class MockConn:
            def __init__(self) -> None:
                self.results: dict[int, Any] = {}
                self.errors: dict[int, Any] = {}

            def send_result(self, msg_id: int, payload: Any) -> None:
                self.results[msg_id] = payload

            def send_error(self, msg_id: int, code: str, message: str) -> None:
                self.errors[msg_id] = (code, message)

        conn = MockConn()
        ws_get_snapshot(hass, conn, {"id": 1, "type": "kickbase/get_snapshot"})
        self.assertTrue(conn.results[1]["configured"])
        self.assertEqual(conn.results[1]["db_stats"]["players_count"], 5)

        req_before_ws_reads = len(session.requests)
        await ws_get_player_detail(hass, conn, {"id": 2, "type": "kickbase/get_player_detail", "league_id": "2001", "player_id": "4577"})
        self.assertTrue(conn.results[2]["from_local_db"])
        self.assertEqual(conn.results[2]["player"]["local_image"], "/api/kickbase_photos/player_4577.png")
        self.assertEqual(len(conn.results[2]["status_history"]), 2)

        await ws_get_manager_detail(hass, conn, {"id": 3, "type": "kickbase/get_manager_detail", "league_id": "2001", "manager_id": "101"})
        self.assertTrue(conn.results[3]["from_local_db"])
        self.assertEqual(conn.results[3]["dashboard"]["name"], "Max")
        self.assertEqual(conn.results[3]["squad"][0]["id"], "888")

        await ws_query_local_players(hass, conn, {"id": 9, "type": "kickbase/query_local_players", "league_id": "2001", "scope": "rival_squad"})
        self.assertEqual([p["id"] for p in conn.results[9]["players"]], ["888"])

        await ws_get_db_stats(hass, conn, {"id": 10, "type": "kickbase/get_db_stats", "league_id": "2001"})
        self.assertEqual(conn.results[10]["players_count"], 5)

        # Confirm ZERO Kickbase HTTP requests happened during all those local reads!
        self.assertEqual(len(session.requests), req_before_ws_reads)

        # Verify local services (get_player_history & query_local_players)
        hist_res = await hass.services.services[("kickbase", "get_player_history")](
            ServiceCall({"player_id": "4577"})
        )
        self.assertTrue(hist_res["found"])
        self.assertEqual(len(hist_res["status_history"]), 2)
        query_res = await hass.services.services[("kickbase", "query_local_players")](
            ServiceCall({"scope": "market", "query": "Wirtz"})
        )
        self.assertEqual(query_res["count"], 1)
        self.assertEqual(len(session.requests), req_before_ws_reads)

        # Verify on-demand match, news, search, challenge & refresh WebSockets
        await ws_get_match_detail(hass, conn, {"id": 4, "type": "kickbase/get_match_detail", "match_id": "9901"})
        self.assertEqual(conn.results[4]["team1_name"], "FC Bayern")

        await ws_get_news_item(hass, conn, {"id": 5, "type": "kickbase/get_news_item", "item_id": "n1"})
        self.assertNotIn("<script>", conn.results[5]["html"])

        await ws_search_players(hass, conn, {"id": 6, "type": "kickbase/search_players", "competition_id": "1", "query": "Kane"})
        self.assertEqual(conn.results[6]["players"][0]["name"], "Kane")

        await ws_get_challenge_detail(hass, conn, {"id": 7, "type": "kickbase/get_challenge_detail", "challenge_id": "ch1"})
        self.assertEqual(conn.results[7]["live_points"], 760)

        await ws_refresh(hass, conn, {"id": 8, "type": "kickbase/refresh", "league_id": "2001"})
        self.assertTrue(conn.results[8]["configured"])

        self.assertTrue(await async_unload_entry(hass, entry))

    async def test_coordinator_auth_failure_raises_config_entry_auth_failed(self) -> None:
        hass = self._new_hass()
        session = FakeClientSession()
        session.add_route("POST", "/v4/user/login", FakeResponse(401, text_data="Invalid"))
        api = KickbaseApi(session, "bad@example.com", "wrong")
        entry = ConfigEntry(entry_id="bad_entry")
        coord = AccountCoordinator(hass, entry, api)
        with self.assertRaises(ConfigEntryAuthFailed):
            await coord.async_config_entry_first_refresh()

        session2 = FakeClientSession()
        for _ in range(3):
            session2.add_route("POST", "/v4/user/login", FakeResponse(500, text_data="Server down"))
        api2 = KickbaseApi(session2, "u@example.com", "pw")
        coord2 = AccountCoordinator(hass, entry, api2)

        async def _fast_sleep(_: float) -> None:
            return None

        with patch("asyncio.sleep", side_effect=_fast_sleep):
            with self.assertRaises(UpdateFailed):
                await coord2.async_config_entry_first_refresh()


if __name__ == "__main__":
    unittest.main()
