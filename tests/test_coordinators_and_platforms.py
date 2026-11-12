"""End-to-end tests for modular coordinators, platforms, config flow, setup, and WebSocket API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
import types
import unittest
from typing import Any

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
from custom_components.kickbase.config_flow import KickbaseConfigFlow, KickbaseOptionsFlow
from custom_components.kickbase.const import (
    ALL_MODULES,
    CONF_EMAIL,
    CONF_ENABLE_PLAYER_ENTITIES,
    CONF_ENABLE_SIDEBAR_PANEL,
    CONF_LEAGUES,
    CONF_MARKET_VALUE_TIMEFRAME,
    CONF_MODULES,
    CONF_PASSWORD,
    CONF_PRIMARY_LEAGUE,
    EVENT_LIVE_PLAYER_EVENT,
    EVENT_NEGATIVE_BUDGET,
    EVENT_NEW_ACTIVITY,
    EVENT_SCOUTED_ON_MARKET,
    LIVE_MATCHDAY_ACTIVE_INTERVAL,
    MODULE_LEAGUE_OVERVIEW,
    MODULE_SQUAD_LINEUP,
)
from custom_components.kickbase.coordinators.account import AccountCoordinator
from custom_components.kickbase.image import async_setup_entry as img_setup
from custom_components.kickbase.sensor import async_setup_entry as sensor_setup
from custom_components.kickbase.websocket_api import (
    ws_get_challenge_detail,
    ws_get_manager_detail,
    ws_get_match_detail,
    ws_get_news_item,
    ws_get_player_detail,
    ws_get_snapshot,
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

    # League overview module
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
                    {"i": "101", "n": "Max", "sp": 18200, "mdp": 890, "tv": 152000000, "spl": 1, "mdpl": 2},
                    {"i": "100", "n": "Chris", "sp": 17950, "mdp": 1050, "tv": 145000000, "spl": 2, "mdpl": 1, "adm": True},
                ],
            },
        ),
    )
    session.add_route("GET", "/v4/leagues/2001/settings", FakeResponse(200, {"d": "Top Liga"}))

    # Squad & Lineup module
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

    # Market & Scouted module
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

    # Live Matchday module
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
    session.add_route(
        "GET",
        "/v4/competitions/1/table",
        FakeResponse(200, {"it": [{"tid": "2", "tn": "FC Bayern", "cpl": 1, "cp": 52, "mc": 21, "gd": 38}]}),
    )
    session.add_route(
        "GET",
        "/v4/competitions/1/ranking",
        FakeResponse(200, {"it": [{"tid": "2", "tn": "FC Bayern", "spl": 1, "sp": 28000, "mdp": 1400}]}),
    )
    session.add_route(
        "GET",
        "/v4/leagues/2001/users/100/teamcenter",
        FakeResponse(200, {"us": [{"i": "100", "unm": "Chris", "mdp": 1050, "pl": 1}]}),
    )
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
    session.add_route(
        "GET",
        "/v4/leagues/2001/activitiesFeed",
        FakeResponse(200, {"af": [{"i": "act_1", "t": 15, "dt": match_iso, "coc": 2, "data": {"pn": "Kane"}}]}),
    )
    session.add_route(
        "GET",
        "/v4/leagues/2001/user/achievements",
        FakeResponse(200, {"it": [{"t": 1, "n": "1000er Club", "ac": 2, "ise": True}, {"t": 2, "n": "Meister", "ac": 0, "ise": False}]}),
    )

    # News & Predictions
    session.add_route("GET", "/v4/base/overview", FakeResponse(200, {"sect": []}))
    session.add_route("GET", "/v4/base/stage", FakeResponse(200, {"stg": [{"i": "st1", "ti": "Topspiel"}]}))
    session.add_route(
        "GET",
        "/v4/base/news/1",
        FakeResponse(200, {"it": [{"i": "n1", "ti": "Kane trifft doppelt", "rl": "News", "dt": match_iso}]}),
    )
    session.add_route(
        "GET",
        "/v4/base/predictions/teams/1",
        FakeResponse(200, {"tms": [{"tid": "2", "tn": "FC Bayern", "plpim": "pred/fcb.png"}]}),
    )
    session.add_route(
        "GET",
        "/v4/base/items/n1",
        FakeResponse(200, {"ti": "Kane trifft doppelt", "cnt": "<p>Hallo</p><script>alert(1)</script>"}),
    )

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

    # Player & Manager & Search endpoints for WebSocket commands
    session.add_route("GET", "/v4/leagues/2001/players/4577", FakeResponse(200, {"i": "4577", "ln": "Kane", "pos": 4, "mv": 72000000}))
    session.add_route("GET", "/v4/leagues/2001/players/4577/marketvalue/92", FakeResponse(200, {"trp": 68000000, "prlo": 4000000, "it": [{"dt": 20100, "mv": 72000000}]}))
    session.add_route("GET", "/v4/leagues/2001/players/4577/performance", FakeResponse(200, {"it": []}))
    session.add_route("GET", "/v4/leagues/2001/players/4577/transfers", FakeResponse(200, {"it": []}))
    session.add_route("GET", "/v4/leagues/2001/players/4577/transferHistory", FakeResponse(200, {"it": [{"unm": "Chris", "trp": 68000000}]}))

    session.add_route("GET", "/v4/leagues/2001/managers/101/dashboard", FakeResponse(200, {"u": "101", "unm": "Max", "pl": 1, "tp": 18200}))
    session.add_route("GET", "/v4/leagues/2001/managers/101/squad", FakeResponse(200, {"it": [{"i": "555", "ln": "Wirtz", "pos": 3, "mv": 52000000}]}))
    session.add_route("GET", "/v4/leagues/2001/managers/101/performance", FakeResponse(200, {"it": []}))
    session.add_route("GET", "/v4/leagues/2001/managers/101/transfer", FakeResponse(200, {"it": []}))

    session.add_route("GET", "/v4/competitions/1/players/search", FakeResponse(200, {"it": [{"i": "4577", "fn": "Harry", "ln": "Kane", "pos": 4, "mv": 72000000}]}))

    return session


class TestKickbaseIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_config_and_options_flow(self) -> None:
        hass = HomeAssistant()
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
                CONF_MARKET_VALUE_TIMEFRAME: "180",
            }
        )
        self.assertEqual(created["type"], "create_entry")
        self.assertEqual(created["options"][CONF_MARKET_VALUE_TIMEFRAME], 180)
        self.assertEqual(created["options"][CONF_MODULES], [MODULE_LEAGUE_OVERVIEW, MODULE_SQUAD_LINEUP])

        # OptionsFlow does not take config_entry in __init__ (modern HA compliant)
        entry = ConfigEntry(entry_id="e1", data=created["data"], options=created["options"])
        opt_flow = KickbaseConfigFlow.async_get_options_flow(entry)
        opt_flow.config_entry = entry
        opt_form = await opt_flow.async_step_init()
        self.assertEqual(opt_form["step_id"], "init")
        opt_done = await opt_flow.async_step_init(
            {CONF_MODULES: [MODULE_LEAGUE_OVERVIEW], CONF_MARKET_VALUE_TIMEFRAME: "365"}
        )
        self.assertEqual(opt_done["type"], "create_entry")
        self.assertEqual(opt_done["data"][CONF_MARKET_VALUE_TIMEFRAME], 365)

    async def test_modular_setup_only_instantiates_enabled_modules(self) -> None:
        hass = HomeAssistant()
        hass._test_session = _seed_mock_kickbase_session()
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
        self.assertIsNotNone(lset.overview)
        self.assertIsNone(lset.squad_lineup)
        self.assertIsNone(lset.market_transfers)
        self.assertIsNone(lset.live_matchday)
        self.assertIsNone(lset.feed_achievements)

        self.assertTrue(await async_unload_entry(hass, entry))

    async def test_full_setup_platforms_events_and_websockets(self) -> None:
        frontend.panels.clear()
        frontend.extra_js_urls.clear()
        websocket_api.registered_commands.clear()

        hass = HomeAssistant()
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
                CONF_MARKET_VALUE_TIMEFRAME: 92,
            },
        )
        hass.config_entries.add_entry(entry)

        self.assertTrue(await async_setup_entry(hass, entry))
        rt = entry.runtime_data
        lset = rt.leagues["2001"]

        # Verify adaptive live polling switched to 60s active interval
        self.assertEqual(lset.live_matchday.update_interval, LIVE_MATCHDAY_ACTIVE_INTERVAL)

        # Verify panel & static assets registered
        self.assertIn("kickbase", frontend.panels)
        self.assertTrue(any("kickbase-cards.js" in url for url in frontend.extra_js_urls))
        self.assertEqual(len(hass.http.static_paths), 1)

        # Verify service call refreshes cleanly
        refresh_handler = hass.services.services[("kickbase", "refresh_data")]
        await refresh_handler(ServiceCall({"league_id": "2001", "module": MODULE_LEAGUE_OVERVIEW}))

        # Verify HA events fire on transitions
        # 1) Negative budget transition
        session.set_route("GET", "/v4/leagues/2001/me/budget", FakeResponse(200, {"b": -450000, "pbas": 500000}))
        await lset.overview.async_request_refresh()
        self.assertTrue(any(ev == EVENT_NEGATIVE_BUDGET for ev, _ in hass.bus.events))

        # 2) New live event for a player in my_eleven
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
        await lset.live_matchday.async_request_refresh()
        self.assertTrue(any(ev == EVENT_LIVE_PLAYER_EVENT and data["minute"] == 78 for ev, data in hass.bus.events))

        # 3) New activity feed event
        session.set_route(
            "GET",
            "/v4/leagues/2001/activitiesFeed",
            FakeResponse(200, {"af": [{"i": "act_2", "t": 15, "data": {"pn": "Wirtz"}}]}),
        )
        await lset.feed_achievements.async_request_refresh()
        self.assertTrue(any(ev == EVENT_NEW_ACTIVITY and data["activity_id"] == "act_2" for ev, data in hass.bus.events))

        # 4) Scouted player newly entering market
        lset.market_transfers._known_scouted_on_market = set()
        await lset.market_transfers.async_request_refresh()
        self.assertTrue(any(ev == EVENT_SCOUTED_ON_MARKET and data["player_id"] == "777" for ev, data in hass.bus.events))

        # Verify platforms
        sensors: list[Any] = []
        await sensor_setup(hass, entry, sensors.extend)
        self.assertGreater(len(sensors), 15)
        kane_sensor = next(s for s in sensors if s._attr_unique_id.endswith("_player_4577"))
        self.assertEqual(kane_sensor.native_value, 72000000)
        self.assertEqual(kane_sensor.entity_picture, "https://kickbase.b-cdn.net/p/4577.png")

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
        self.assertIsNotNone(cals[0].event)

        imgs: list[Any] = []
        await img_setup(hass, entry, imgs.extend)
        self.assertEqual(len(imgs), 2)
        self.assertEqual(imgs[0].image_url, "https://kickbase.b-cdn.net/user/100.png")
        imgs[0]._handle_coordinator_update()

        # Verify all 8 WebSocket commands return valid results
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

        await ws_get_player_detail(hass, conn, {"id": 2, "type": "kickbase/get_player_detail", "league_id": "2001", "player_id": "4577"})
        self.assertEqual(conn.results[2]["player"]["id"], "4577")

        await ws_get_manager_detail(hass, conn, {"id": 3, "type": "kickbase/get_manager_detail", "league_id": "2001", "manager_id": "101"})
        self.assertEqual(conn.results[3]["dashboard"]["name"], "Max")

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

    async def test_coordinator_auth_failure_raises_config_entry_auth_failed(self) -> None:
        hass = HomeAssistant()
        session = FakeClientSession()
        session.add_route("POST", "/v4/user/login", FakeResponse(401, text_data="Invalid"))
        api = KickbaseApi(session, "bad@example.com", "wrong")
        entry = ConfigEntry(entry_id="bad_entry")
        coord = AccountCoordinator(hass, entry, api)
        with self.assertRaises(ConfigEntryAuthFailed):
            await coord.async_config_entry_first_refresh()

        # Also test non-auth KickbaseError -> UpdateFailed
        session2 = FakeClientSession()
        for _ in range(3):
            session2.add_route("POST", "/v4/user/login", FakeResponse(500, text_data="Server down"))
        api2 = KickbaseApi(session2, "u@example.com", "pw")
        coord2 = AccountCoordinator(hass, entry, api2)
        from unittest.mock import patch

        async def _fast_sleep(_: float) -> None:
            return None

        with patch("asyncio.sleep", side_effect=_fast_sleep):
            with self.assertRaises(UpdateFailed):
                await coord2.async_config_entry_first_refresh()


if __name__ == "__main__":
    unittest.main()
