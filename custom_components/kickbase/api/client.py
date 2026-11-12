"""Core async HTTP client for the unofficial Kickbase v4 API (strictly read-only)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

import aiohttp

from ..const import API_BASE_URL, DEFAULT_IMAGE_BASE_URL
from .exceptions import (
    KickbaseAuthError,
    KickbaseConnectionError,
    KickbaseError,
    KickbaseNotFoundError,
    KickbaseRateLimitError,
)

_LOGGER = logging.getLogger(__name__)

# Only authentication endpoints are allowed to use POST. All data endpoints are strictly GET.
_ALLOWED_AUTH_POST_PATHS = frozenset({"/v4/user/login", "/v4/user/refreshtokens"})


class KickbaseApiClient:
    """Async read-only client for Kickbase API v4."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        *,
        base_url: str = API_BASE_URL,
        max_concurrency: int = 4,
        request_timeout: int = 20,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._auth_lock = asyncio.Lock()

        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self._refresh_token: str | None = None
        self._chat_token: str | None = None
        self._image_base_url: str = DEFAULT_IMAGE_BASE_URL
        self._login_payload: dict[str, Any] = {}
        self._request_count: int = 0

    @property
    def request_count(self) -> int:
        """Return total HTTP API requests made by this client instance."""
        return self._request_count

    @property
    def token(self) -> str | None:
        """Return current bearer token."""
        return self._token

    @property
    def image_base_url(self) -> str:
        """Return CDN base URL for images."""
        return self._image_base_url

    @image_base_url.setter
    def image_base_url(self, value: str) -> None:
        if value:
            self._image_base_url = value if value.endswith("/") else f"{value}/"

    @property
    def login_data(self) -> dict[str, Any]:
        """Return latest login payload (user + srvl leagues)."""
        return self._login_payload

    def _is_token_valid(self) -> bool:
        if not self._token:
            return False
        if self._token_expires_at is None:
            return True
        # Refresh proactively 5 minutes before expiry
        return datetime.now(UTC) < (self._token_expires_at - timedelta(minutes=5))

    async def async_login(self, force: bool = False) -> dict[str, Any]:
        """Authenticate against `/v4/user/login` and store bearer token."""
        async with self._auth_lock:
            if not force and self._is_token_valid() and self._login_payload:
                return self._login_payload

            payload = {
                "em": self._email,
                "pass": self._password,
                "loy": False,
                "rep": {},
            }
            data = await self._raw_request(
                "POST",
                "/v4/user/login",
                json_body=payload,
                authenticated=False,
                retry_on_401=False,
            )
            token = data.get("tkn")
            if not token:
                raise KickbaseAuthError("Kickbase login response did not contain a token ('tkn').")

            self._token = token
            self._refresh_token = data.get("rtkn")
            self._chat_token = data.get("chttkn")
            self._login_payload = data

            tknex = data.get("tknex")
            self._token_expires_at = None
            if isinstance(tknex, str) and not tknex.startswith("1970-00-00"):
                try:
                    dt = datetime.fromisoformat(tknex.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=UTC)
                    self._token_expires_at = dt
                except ValueError:
                    self._token_expires_at = datetime.now(UTC) + timedelta(hours=12)
            else:
                self._token_expires_at = datetime.now(UTC) + timedelta(hours=12)

            return data

    async def async_ensure_authenticated(self) -> None:
        """Ensure a valid bearer token is present before making GET requests."""
        if not self._is_token_valid():
            if self._refresh_token:
                try:
                    await self._async_refresh_token()
                    return
                except KickbaseError:
                    _LOGGER.debug("Token refresh failed, falling back to full login")
            await self.async_login(force=True)

    async def _async_refresh_token(self) -> None:
        """Attempt token refresh using `/v4/user/refreshtokens`."""
        async with self._auth_lock:
            if not self._refresh_token:
                raise KickbaseAuthError("No refresh token available")
            data = await self._raw_request(
                "POST",
                "/v4/user/refreshtokens",
                json_body={"rtkn": self._refresh_token},
                authenticated=False,
                retry_on_401=False,
            )
            new_token = data.get("tkn") or data.get("token")
            if not new_token:
                raise KickbaseAuthError("Refresh token response missing new token")
            self._token = new_token
            if new_rtkn := (data.get("rtkn") or data.get("refreshToken")):
                self._refresh_token = new_rtkn
            self._token_expires_at = datetime.now(UTC) + timedelta(hours=12)

    async def async_get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        allow_404: bool = False,
    ) -> dict[str, Any] | list[Any]:
        """Perform an authenticated GET request against the Kickbase API."""
        await self.async_ensure_authenticated()
        cleaned_params: dict[str, Any] | None = None
        if params:
            cleaned_params = {
                k: str(v).lower() if isinstance(v, bool) else v
                for k, v in params.items()
                if v is not None and v != ""
            }
        try:
            return await self._raw_request(
                "GET",
                path,
                params=cleaned_params,
                authenticated=True,
                retry_on_401=True,
            )
        except KickbaseNotFoundError:
            if allow_404:
                return {}
            raise

    async def _raw_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        authenticated: bool = True,
        retry_on_401: bool = True,
    ) -> Any:
        """Execute HTTP request with strict read-only guard, concurrency cap, and backoff."""
        method_upper = method.upper()
        if method_upper != "GET" and path not in _ALLOWED_AUTH_POST_PATHS:
            raise RuntimeError(
                f"Blocked non-read-only request {method_upper} {path}: integration is strictly read-only."
            )

        url = f"{self._base_url}{path}"
        headers = {
            "Accept": "application/json",
            "User-Agent": "KickbaseHomeAssistant/1.0",
        }
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        if authenticated and self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        max_attempts = 3
        for attempt in range(max_attempts):
            retry_delay: float | None = None
            needs_relogin = False
            try:
                async with self._semaphore:
                    self._request_count += 1
                    async with self._session.request(
                        method_upper,
                        url,
                        params=params,
                        json=json_body,
                        headers=headers,
                        timeout=self._timeout,
                    ) as resp:
                        if resp.status == 401:
                            text = await resp.text()
                            if retry_on_401 and authenticated:
                                _LOGGER.debug("Received 401 for %s, re-authenticating", path)
                                needs_relogin = True
                            else:
                                raise KickbaseAuthError(
                                    f"Authentication failed ({resp.status}): {text[:200]}"
                                )

                        elif resp.status == 403:
                            text = await resp.text()
                            raise KickbaseAuthError(
                                f"Access forbidden ({resp.status}) on {path}: {text[:200]}"
                            )

                        elif resp.status == 404:
                            raise KickbaseNotFoundError(f"Resource not found: {path}")

                        elif resp.status == 429:
                            retry_after = resp.headers.get("Retry-After")
                            delay = (
                                float(retry_after)
                                if retry_after and retry_after.isdigit()
                                else (2.0 ** attempt) * 2.0
                            )
                            if attempt < max_attempts - 1:
                                _LOGGER.warning(
                                    "Rate limited (429) on %s, retrying in %.1fs",
                                    path,
                                    delay,
                                )
                                retry_delay = min(delay, 15.0)
                            else:
                                raise KickbaseRateLimitError(
                                    f"Rate limit exceeded on {path}"
                                )

                        elif resp.status >= 500:
                            text = await resp.text()
                            if attempt < max_attempts - 1:
                                retry_delay = 1.5 * (attempt + 1)
                            else:
                                raise KickbaseConnectionError(
                                    f"Server error {resp.status} on {path}: {text[:200]}"
                                )

                        elif resp.status >= 400:
                            text = await resp.text()
                            raise KickbaseError(
                                f"HTTP {resp.status} on {path}: {text[:200]}"
                            )

                        elif resp.content_length == 0:
                            return {}

                        else:
                            content_type = resp.headers.get("Content-Type", "")
                            if "application/json" in content_type or not content_type:
                                try:
                                    return await resp.json(content_type=None)
                                except (ValueError, aiohttp.ContentTypeError):
                                    text = await resp.text()
                                    return {"raw": text} if text else {}
                            return {"raw": await resp.text()}

            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                if attempt < max_attempts - 1:
                    retry_delay = 1.0 * (attempt + 1)
                else:
                    raise KickbaseConnectionError(
                        f"Connection error on {path}: {err}"
                    ) from err

            if needs_relogin:
                await self.async_login(force=True)
                headers["Authorization"] = f"Bearer {self._token}"
                retry_on_401 = False
                continue

            if retry_delay is not None:
                await asyncio.sleep(retry_delay)
                continue

        raise KickbaseConnectionError(f"Exhausted retries on {path}")

    async def async_download_bytes(self, url: str) -> tuple[bytes, str] | None:
        """Strictly read-only GET helper to download static CDN image assets for local cache."""
        if not url or not url.startswith(("http://", "https://")):
            return None
        try:
            async with self._semaphore:
                async with self._session.request(
                    "GET",
                    url,
                    headers={"User-Agent": "KickbaseHomeAssistant/1.0"},
                    timeout=self._timeout,
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.read()
                    content_type = resp.headers.get("Content-Type", "image/png")
                    return data, content_type
        except (aiohttp.ClientError, asyncio.TimeoutError, AttributeError):
            return None
