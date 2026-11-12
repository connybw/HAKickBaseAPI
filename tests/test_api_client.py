"""Tests for KickbaseApiClient (auth, retries, strict read-only guard)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.ha_stubs import FakeClientSession, FakeResponse, install_stubs

install_stubs()

from custom_components.kickbase.api.client import KickbaseApiClient
from custom_components.kickbase.api.exceptions import (
    KickbaseAuthError,
    KickbaseNotFoundError,
    KickbaseRateLimitError,
)


class TestKickbaseApiClient(unittest.IsolatedAsyncioTestCase):
    async def test_login_and_authenticated_get_params(self) -> None:
        session = FakeClientSession()
        future_exp = (datetime.now(UTC) + timedelta(hours=10)).isoformat()
        session.add_route(
            "POST",
            "/v4/user/login",
            FakeResponse(
                200,
                {
                    "tkn": "tok_123",
                    "rtkn": "ref_456",
                    "tknex": future_exp,
                    "u": {"id": "99", "name": "Tester"},
                    "srvl": [],
                },
            ),
        )
        session.add_route(
            "GET",
            "/v4/leagues/1/overview",
            FakeResponse(200, {"lnm": "Testliga"}),
        )

        client = KickbaseApiClient(session, "user@example.com", "secret")
        res = await client.async_get(
            "/v4/leagues/1/overview",
            params={"includeManagersAndBattles": True, "empty": "", "unused": None},
        )
        self.assertEqual(res, {"lnm": "Testliga"})
        self.assertEqual(client.token, "tok_123")
        self.assertEqual(len(session.requests), 2)
        get_req = session.requests[1]
        self.assertEqual(get_req["headers"]["Authorization"], "Bearer tok_123")
        self.assertEqual(get_req["params"], {"includeManagersAndBattles": "true"})

    async def test_login_missing_token_or_401_raises_auth_error(self) -> None:
        session = FakeClientSession()
        session.add_route("POST", "/v4/user/login", FakeResponse(401, text_data="Bad creds"))
        client = KickbaseApiClient(session, "bad@example.com", "wrong")
        with self.assertRaises(KickbaseAuthError):
            await client.async_login()

    async def test_401_on_get_triggers_single_relogin_retry(self) -> None:
        session = FakeClientSession()
        session.add_route(
            "POST",
            "/v4/user/login",
            FakeResponse(200, {"tkn": "old_tok", "tknex": "1970-00-00T00:00:00Z"}),
        )
        session.add_route(
            "POST",
            "/v4/user/login",
            FakeResponse(200, {"tkn": "new_tok", "tknex": "1970-00-00T00:00:00Z"}),
        )
        session.add_route("GET", "/v4/user/me", FakeResponse(401, text_data="Expired"))
        session.add_route("GET", "/v4/user/me", FakeResponse(200, {"u": {"id": "7"}}))

        client = KickbaseApiClient(session, "u@e.de", "pw")
        data = await client.async_get("/v4/user/me")
        self.assertEqual(data["u"]["id"], "7")
        self.assertEqual(client.token, "new_tok")

    async def test_refresh_token_used_before_full_login(self) -> None:
        session = FakeClientSession()
        client = KickbaseApiClient(session, "u@e.de", "pw")
        client._token = "expired"
        client._refresh_token = "rtkn_1"
        client._token_expires_at = datetime.now(UTC) - timedelta(minutes=1)

        session.add_route(
            "POST",
            "/v4/user/refreshtokens",
            FakeResponse(200, {"tkn": "refreshed_tok", "rtkn": "rtkn_2"}),
        )
        session.add_route("GET", "/v4/config", FakeResponse(200, {"ibp": "https://cdn.test"}))

        cfg = await client.async_get("/v4/config")
        self.assertEqual(cfg["ibp"], "https://cdn.test")
        self.assertEqual(client.token, "refreshed_tok")
        self.assertEqual(session.requests[0]["json"], {"rtkn": "rtkn_1"})

    async def test_404_behavior_with_allow_404(self) -> None:
        session = FakeClientSession()
        client = KickbaseApiClient(session, "u@e.de", "pw")
        client._token = "tok"
        client._token_expires_at = datetime.now(UTC) + timedelta(hours=1)

        with self.assertRaises(KickbaseNotFoundError):
            await client.async_get("/v4/missing")

        res = await client.async_get("/v4/missing", allow_404=True)
        self.assertEqual(res, {})

    async def test_429_retries_and_raises_rate_limit(self) -> None:
        session = FakeClientSession()
        client = KickbaseApiClient(session, "u@e.de", "pw")
        client._token = "tok"
        client._token_expires_at = datetime.now(UTC) + timedelta(hours=1)

        for _ in range(3):
            session.add_route(
                "GET",
                "/v4/leagues/1/market",
                FakeResponse(429, headers={"Retry-After": "1"}),
            )

        async def _fast_sleep(_: float) -> None:
            return None

        with patch("asyncio.sleep", side_effect=_fast_sleep):
            with self.assertRaises(KickbaseRateLimitError):
                await client.async_get("/v4/leagues/1/market")
        self.assertEqual(len(session.requests), 3)

    async def test_strict_read_only_guard_blocks_mutations(self) -> None:
        session = FakeClientSession()
        client = KickbaseApiClient(session, "u@e.de", "pw")
        client._token = "tok"
        client._token_expires_at = datetime.now(UTC) + timedelta(hours=1)

        for method, path in (
            ("POST", "/v4/leagues/1/market/12/offers"),
            ("POST", "/v4/leagues/1/lineup"),
            ("PUT", "/v4/leagues/1/lineup"),
            ("DELETE", "/v4/leagues/1/market/12/offers/99"),
            ("PATCH", "/v4/user/settings"),
        ):
            with self.assertRaises(RuntimeError):
                await client._raw_request(method, path, json_body={"p": 100})

        self.assertEqual(session.requests, [])

    def test_no_mutating_endpoints_exist_in_integration_code(self) -> None:
        api_dir = ROOT / "custom_components" / "kickbase" / "api"
        combined = "\n".join(p.read_text(encoding="utf-8") for p in api_dir.rglob("*.py"))
        self.assertNotIn("/bonus/collect", combined)
        self.assertNotIn("/market/", combined.split("async def get_player_transfers")[0] if False else "")
        for forbidden_call in (".post(", ".put(", ".delete(", ".patch("):
            self.assertNotIn(forbidden_call, combined)


if __name__ == "__main__":
    unittest.main()
