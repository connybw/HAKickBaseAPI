"""Tests for Kickbase data normalization helpers & decoders."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.ha_stubs import install_stubs

install_stubs()

from custom_components.kickbase.api.models import (
    decode_activity_type,
    decode_market_trend,
    decode_match_status,
    decode_player_status,
    decode_position,
    epoch_days_to_iso,
    normalize_market_value_series,
    normalize_player,
    parse_iso_datetime,
    resolve_image_url,
)


class TestKickbaseModels(unittest.TestCase):
    def test_resolve_image_url(self) -> None:
        self.assertIsNone(resolve_image_url(None))
        self.assertIsNone(resolve_image_url(""))
        self.assertEqual(
            resolve_image_url("content/player/123.png", "https://kickbase.b-cdn.net/"),
            "https://kickbase.b-cdn.net/content/player/123.png",
        )
        self.assertEqual(
            resolve_image_url("/content/team/1.png", "https://cdn.example"),
            "https://cdn.example/content/team/1.png",
        )
        self.assertEqual(
            resolve_image_url("https://other.cdn/img.png", "https://cdn.example"),
            "https://other.cdn/img.png",
        )

    def test_epoch_days_and_iso_parsing(self) -> None:
        self.assertEqual(epoch_days_to_iso(0), "1970-01-01")
        self.assertEqual(epoch_days_to_iso(20100), "2025-01-12")
        self.assertIsNone(epoch_days_to_iso(None))

        # Kickbase invalid sentinel date from Postman samples
        self.assertIsNone(parse_iso_datetime("1970-00-00T00:00:00Z"))
        self.assertIsNone(parse_iso_datetime("not-a-date"))
        parsed = parse_iso_datetime("2025-02-14T19:30:00Z")
        self.assertEqual(parsed, datetime(2025, 2, 14, 19, 30, tzinfo=UTC))

    def test_decoders(self) -> None:
        self.assertEqual(decode_position(1)["short"], "TW")
        self.assertEqual(decode_position(4)["key"], "fwd")
        self.assertEqual(decode_position(99)["key"], "unknown")

        self.assertEqual(decode_player_status(0)["severity"], "ok")
        self.assertEqual(decode_player_status(1)["severity"], "danger")
        self.assertEqual(decode_player_status(4)["severity"], "warning")
        combined = decode_player_status(1 | 4)
        self.assertEqual(combined["severity"], "danger")
        self.assertIn("Verletzt", combined["label_de"])

        self.assertEqual(decode_market_trend(1), "rising")
        self.assertEqual(decode_market_trend(2), "falling")
        self.assertEqual(decode_market_trend(0), "stable")

        self.assertEqual(decode_match_status(1), "live")
        self.assertEqual(decode_match_status(2), "finished")
        self.assertEqual(decode_activity_type(15)["key"], "matchday_result")

    def test_normalize_player_squad_and_market_shapes(self) -> None:
        squad_raw = {
            "i": "4577",
            "fn": "Harry",
            "ln": "Kane",
            "tid": "2",
            "tn": "FC Bayern",
            "pos": 4,
            "st": 0,
            "mvt": 1,
            "mv": 72500000,
            "tfhmvt": 450000,
            "mvgl": 3200000,
            "p": 1950,
            "ap": 177,
            "lo": 10,
            "ictp": True,
            "pim": "player/4577.png",
        }
        norm = normalize_player(squad_raw, "https://kickbase.b-cdn.net/")
        self.assertEqual(norm["id"], "4577")
        self.assertEqual(norm["full_name"], "Harry Kane")
        self.assertEqual(norm["name"], "Kane")
        self.assertEqual(norm["position"]["short"], "ST")
        self.assertEqual(norm["market_value_trend"], "rising")
        self.assertTrue(norm["is_captain"])
        self.assertEqual(norm["image"], "https://kickbase.b-cdn.net/player/4577.png")

        market_raw = {
            "pi": "9001",
            "pn": "Wirtz",
            "pos": 3,
            "st": 2,
            "mv": 50000000,
            "prc": 52000000,
            "exs": 1800,
            "u": {"n": "Max"},
        }
        norm_m = normalize_player(market_raw, "https://cdn/")
        self.assertEqual(norm_m["id"], "9001")
        self.assertEqual(norm_m["owner_name"], "Max")
        self.assertEqual(norm_m["price"], 52000000)

    def test_normalize_market_value_series(self) -> None:
        raw = {
            "trp": 40000000,
            "prlo": 5000000,
            "lmv": 38000000,
            "hmv": 46000000,
            "iso": True,
            "it": [
                {"dt": 20099, "mv": 44000000},
                {"dt": 20100, "mv": 45000000},
            ],
        }
        res = normalize_market_value_series(raw)
        self.assertEqual(res["transfer_price"], 40000000)
        self.assertTrue(res["is_on_sale"])
        self.assertEqual(res["series"][0]["date"], "2025-01-11")
        self.assertEqual(res["series"][1]["market_value"], 45000000)


if __name__ == "__main__":
    unittest.main()
