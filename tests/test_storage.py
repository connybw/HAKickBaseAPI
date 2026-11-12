"""Tests for KickbaseLocalStore (SQLite persistence, status diffs, MV history, photo cache)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.ha_stubs import install_stubs

install_stubs()

from homeassistant.core import HomeAssistant

from custom_components.kickbase.storage import KickbaseLocalStore


def _make_norm_player(
    pid: str,
    name: str,
    *,
    mv: int = 50000000,
    status_code: int = 0,
    status_key: str = "fit",
    status_label: str = "Fit",
    severity: str = "ok",
    status_text: str | None = None,
    owner_user_id: str | None = "100",
    owner_name: str | None = "Chris",
    is_on_market: bool = False,
    price: int = 0,
) -> dict:
    return {
        "id": pid,
        "name": name,
        "full_name": name,
        "first_name": name.split()[0],
        "last_name": name.split()[-1],
        "team_id": "2",
        "team_name": "FC Bayern",
        "shirt_number": 9,
        "position_code": 4,
        "position": {"key": "fwd", "short": "ST", "name_de": "Sturm"},
        "status_code": status_code,
        "status": {"key": status_key, "label_de": status_label, "severity": severity},
        "status_text": status_text,
        "matchday_status": 1,
        "market_value": mv,
        "market_value_24h_change": 250000,
        "market_value_since_buy": 2000000,
        "market_value_season_diff": 5000000,
        "market_value_trend": "rising",
        "points": 120,
        "total_points": 1500,
        "average_points": 155.0,
        "goals": 15,
        "assists": 4,
        "yellow_cards": 1,
        "red_cards": 0,
        "seconds_played": 900,
        "owner_user_id": owner_user_id,
        "owner_name": owner_name,
        "is_on_market": is_on_market,
        "price": price,
        "image": f"https://kickbase.b-cdn.net/p/{pid}.png",
        "team_image": "https://kickbase.b-cdn.net/team/2.png",
    }


class TestKickbaseLocalStore(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="kb_store_test_"))
        self.hass = HomeAssistant(self.tmp_dir)
        self.store = KickbaseLocalStore(self.hass, self.tmp_dir / "kickbase_data")
        await self.store.async_init()

    async def asyncTearDown(self) -> None:
        await self.store.async_close()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    async def test_bulk_sync_mv_history_deduplicated_status_history_and_queries(self) -> None:
        today = datetime.now(UTC).date().isoformat()
        p_kane = _make_norm_player("4577", "Harry Kane", mv=72000000)
        p_wirtz = _make_norm_player(
            "555",
            "Florian Wirtz",
            mv=52000000,
            owner_user_id="0",
            owner_name="Kickbase",
            is_on_market=True,
            price=52500000,
        )
        p_musiala = _make_norm_player(
            "777",
            "Jamal Musiala",
            mv=61000000,
            status_code=2,
            status_key="knock",
            status_label="Angeschlagen",
            severity="warning",
            status_text="Muskelprobleme",
            owner_user_id="101",
            owner_name="Max",
        )

        # Save cached photo & ensure find_cached_photos picks it up
        local_url = await self.store.async_save_photo(
            "player_4577",
            b"\x89PNG\r\n\x1a\nfake",
            remote_url="https://kickbase.b-cdn.net/p/4577.png",
            content_type="image/png",
        )
        self.assertEqual(local_url, "/api/kickbase_photos/player_4577.png")
        found = await self.store.async_find_cached_photos(["player_4577", "player_999"])
        self.assertEqual(found, {"player_4577": "/api/kickbase_photos/player_4577.png"})
        p_kane["local_image"] = found["player_4577"]

        changes_1 = await self.store.async_upsert_bulk_sync(
            league_id="2001",
            players_payload=[
                {
                    "player": p_kane,
                    "scopes": ["my_squad"],
                    "is_scouted": False,
                    "details": {"status_text": "Topfit", "transfer_price": 68000000, "profit_loss": 4000000},
                    "market_value_series": {
                        "series": [
                            {"date": "2026-01-01", "market_value": 69000000},
                            {"date": "2026-01-02", "market_value": 70500000},
                        ]
                    },
                    "performance": [{"ti": "25/26", "ph": []}],
                    "transfers": {},
                    "transfer_history": [{"user_name": "Chris", "price": 68000000}],
                    "details_refreshed": True,
                    "mv_refreshed": True,
                },
                {
                    "player": p_wirtz,
                    "scopes": ["market", "scouted"],
                    "is_scouted": True,
                    "details": {},
                    "details_refreshed": True,
                },
                {
                    "player": p_musiala,
                    "scopes": ["rival_squad"],
                    "is_scouted": False,
                    "details": {"status_text": "Muskelprobleme"},
                    "details_refreshed": True,
                },
            ],
            managers_payload=[
                {
                    "id": "101",
                    "name": "Max",
                    "rank": 1,
                    "season_points": 18200,
                    "team_value": 152000000,
                    "avatar": "https://kickbase.b-cdn.net/u/101.png",
                    "local_avatar": "/api/kickbase_photos/manager_101.png",
                    "dashboard": {"id": "101", "name": "Max", "rank": 1},
                    "squad": [p_musiala],
                    "performance": [],
                    "transfers": [],
                }
            ],
            sync_meta={
                "my_squad_count": 1,
                "market_count": 1,
                "rival_players_count": 1,
                "photos_downloaded": 1,
                "api_requests": 14,
            },
        )
        # Initial insert has prev_state=None -> does not emit transition event
        self.assertEqual(changes_1, [])

        # Second sync with identical status for Kane -> NO duplicate status_history row
        p_kane_same = _make_norm_player("4577", "Harry Kane", mv=72300000)
        changes_2 = await self.store.async_upsert_bulk_sync(
            league_id="2001",
            players_payload=[{"player": p_kane_same, "scopes": ["my_squad"], "is_scouted": False}],
            managers_payload=[],
            sync_meta={"my_squad_count": 1, "api_requests": 4},
        )
        self.assertEqual(changes_2, [])

        # Third sync: Musiala gets injured & listed on market -> status transition event + new history row
        p_musiala_inj = _make_norm_player(
            "777",
            "Jamal Musiala",
            mv=59500000,
            status_code=1,
            status_key="injured",
            status_label="Verletzt",
            severity="danger",
            status_text="Kapselverletzung",
            owner_user_id="101",
            owner_name="Max",
            is_on_market=True,
            price=60000000,
        )
        changes_3 = await self.store.async_upsert_bulk_sync(
            league_id="2001",
            players_payload=[{"player": p_musiala_inj, "scopes": ["market", "rival_squad"], "is_scouted": False}],
            managers_payload=[],
            sync_meta={"market_count": 1, "rival_players_count": 1, "api_requests": 5},
        )
        self.assertEqual(len(changes_3), 1)
        self.assertEqual(changes_3[0]["player_id"], "777")
        self.assertEqual(changes_3[0]["old_status_code"], 2)
        self.assertEqual(changes_3[0]["new_status_code"], 1)

        # Check player detail read from SQLite
        kane_det = await self.store.async_get_player_detail("2001", "4577")
        self.assertIsNotNone(kane_det)
        self.assertTrue(kane_det["from_local_db"])
        self.assertEqual(kane_det["player"]["local_image"], "/api/kickbase_photos/player_4577.png")
        # 2 backfilled points + 1 today snapshot (updated to 72,300,000)
        dates = [pt["date"] for pt in kane_det["market_value"]["series"]]
        self.assertIn("2026-01-01", dates)
        self.assertIn(today, dates)
        today_pt = next(pt for pt in kane_det["market_value"]["series"] if pt["date"] == today)
        self.assertEqual(today_pt["market_value"], 72300000)
        # Status history deduplicated to 1 entry for Kane
        self.assertEqual(len(kane_det["status_history"]), 1)

        musiala_det = await self.store.async_get_player_detail("2001", "777")
        self.assertEqual(len(musiala_det["status_history"]), 2)
        self.assertEqual(musiala_det["status_history"][0]["status_key"], "injured")
        self.assertEqual(musiala_det["status_history"][1]["status_key"], "knock")

        # Manager snapshot read
        mgr_det = await self.store.async_get_manager_detail("2001", "101")
        self.assertIsNotNone(mgr_det)
        self.assertEqual(mgr_det["dashboard"]["local_avatar"], "/api/kickbase_photos/manager_101.png")

        # Queries & filters
        issues = await self.store.async_query_players("2001", status_severity="issues")
        self.assertEqual([p["id"] for p in issues], ["777"])
        market_only = await self.store.async_query_players("2001", scope="market")
        self.assertEqual({p["id"] for p in market_only}, {"555", "777"})
        search_wirtz = await self.store.async_query_players("2001", query="Wirtz")
        self.assertEqual([p["id"] for p in search_wirtz], ["555"])

        # Stats check
        stats = await self.store.async_get_stats("2001")
        self.assertEqual(stats["players_count"], 3)
        self.assertEqual(stats["my_squad_count"], 1)
        self.assertEqual(stats["market_count"], 2)
        self.assertEqual(stats["rival_players_count"], 1)
        self.assertEqual(stats["photos_cached"], 1)
        self.assertEqual(len(stats["recent_runs"]), 3)


if __name__ == "__main__":
    unittest.main()
