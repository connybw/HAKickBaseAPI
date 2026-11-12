"""Local SQLite database and player photo cache for Kickbase."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import logging
from pathlib import Path
import re
import sqlite3
import threading
from typing import TYPE_CHECKING, Any

from .const import STATIC_PHOTOS_URL_PATH

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from .api.client import KickbaseHttpClient

_LOGGER = logging.getLogger(__name__)

_SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_-]")
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".svg")
_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


def _safe_key(val: str) -> str:
    return _SAFE_ID_RE.sub("_", str(val or "unknown"))


def asset_photo_key(prefix: str, item_id: str | None, remote_url: str | None = None) -> str:
    """Build deterministic cache key for non-player assets (league/news/team/user/banner)."""
    clean_id = str(item_id or "").strip()
    if clean_id:
        return f"{prefix}_{_safe_key(clean_id)}"
    digest = hashlib.sha1(str(remote_url or "").encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _guess_extension(url: str | None, content_type: str | None) -> str:
    ct = (content_type or "").lower()
    if "webp" in ct:
        return ".webp"
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "svg" in ct:
        return ".svg"
    if "png" in ct:
        return ".png"
    if url:
        clean = url.split("?")[0].lower()
        for ext in _IMAGE_EXTS:
            if clean.endswith(ext):
                return ext
    return ".png"


class KickbaseLocalStore:
    """Thread-safe local SQLite store + disk photo cache."""

    def __init__(
        self,
        hass: HomeAssistant,
        data_dir: Path,
        *,
        static_photos_url: str = STATIC_PHOTOS_URL_PATH,
    ) -> None:
        self._hass = hass
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "kickbase.db"
        self.photos_dir = self.data_dir / "photos"
        self._static_photos_url = static_photos_url.rstrip("/")
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    def _ensure_conn(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is not None:
                return self._conn
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.photos_dir.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            self._init_schema(conn)
            self._conn = conn
            return conn

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS players (
                league_id TEXT NOT NULL,
                player_id TEXT NOT NULL,
                name TEXT,
                full_name TEXT,
                first_name TEXT,
                last_name TEXT,
                team_id TEXT,
                team_name TEXT,
                shirt_number INTEGER,
                position_code INTEGER,
                position_short TEXT,
                position_name_de TEXT,
                status_code INTEGER,
                status_key TEXT,
                status_label_de TEXT,
                status_severity TEXT,
                status_text TEXT,
                matchday_status INTEGER,
                market_value INTEGER DEFAULT 0,
                market_value_24h_change INTEGER DEFAULT 0,
                market_value_since_buy INTEGER DEFAULT 0,
                market_value_season_diff INTEGER DEFAULT 0,
                market_value_trend TEXT,
                points INTEGER DEFAULT 0,
                total_points INTEGER DEFAULT 0,
                average_points REAL DEFAULT 0,
                goals INTEGER DEFAULT 0,
                assists INTEGER DEFAULT 0,
                yellow_cards INTEGER DEFAULT 0,
                red_cards INTEGER DEFAULT 0,
                seconds_played INTEGER DEFAULT 0,
                owner_user_id TEXT,
                owner_name TEXT,
                is_on_market INTEGER DEFAULT 0,
                is_scouted INTEGER DEFAULT 0,
                market_price INTEGER DEFAULT 0,
                expiry_seconds INTEGER,
                expiry_at TEXT,
                scopes_json TEXT DEFAULT '[]',
                remote_image_url TEXT,
                local_image_path TEXT,
                team_image_url TEXT,
                local_team_image_path TEXT,
                player_json TEXT DEFAULT '{}',
                details_json TEXT DEFAULT '{}',
                performance_json TEXT DEFAULT '[]',
                transfers_json TEXT DEFAULT '{}',
                transfer_history_json TEXT DEFAULT '[]',
                updated_at TEXT NOT NULL,
                details_updated_at TEXT,
                market_value_synced_at TEXT,
                PRIMARY KEY (league_id, player_id)
            );

            CREATE TABLE IF NOT EXISTS player_market_value_history (
                league_id TEXT NOT NULL,
                player_id TEXT NOT NULL,
                recorded_date TEXT NOT NULL,
                market_value INTEGER NOT NULL,
                recorded_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'hourly_sync',
                PRIMARY KEY (league_id, player_id, recorded_date)
            );
            CREATE INDEX IF NOT EXISTS idx_mv_hist_lookup
                ON player_market_value_history (league_id, player_id, recorded_date);

            CREATE TABLE IF NOT EXISTS player_status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                league_id TEXT NOT NULL,
                player_id TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                status_code INTEGER,
                status_key TEXT,
                status_label_de TEXT,
                status_severity TEXT,
                status_text TEXT,
                matchday_status INTEGER,
                market_value INTEGER DEFAULT 0,
                owner_user_id TEXT,
                owner_name TEXT,
                is_on_market INTEGER DEFAULT 0,
                market_price INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_status_hist_lookup
                ON player_status_history (league_id, player_id, id DESC);

            CREATE TABLE IF NOT EXISTS manager_snapshots (
                league_id TEXT NOT NULL,
                manager_id TEXT NOT NULL,
                name TEXT,
                is_admin INTEGER DEFAULT 0,
                rank INTEGER DEFAULT 0,
                matchday_rank INTEGER DEFAULT 0,
                season_points INTEGER DEFAULT 0,
                matchday_points INTEGER DEFAULT 0,
                team_value INTEGER DEFAULT 0,
                points_avg REAL DEFAULT 0,
                avatar_url TEXT,
                local_avatar_path TEXT,
                dashboard_json TEXT DEFAULT '{}',
                squad_json TEXT DEFAULT '[]',
                performance_json TEXT DEFAULT '[]',
                transfers_json TEXT DEFAULT '[]',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (league_id, manager_id)
            );

            CREATE TABLE IF NOT EXISTS sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                league_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                players_total INTEGER DEFAULT 0,
                my_squad_count INTEGER DEFAULT 0,
                market_count INTEGER DEFAULT 0,
                rival_players_count INTEGER DEFAULT 0,
                managers_synced INTEGER DEFAULT 0,
                photos_downloaded INTEGER DEFAULT 0,
                api_requests INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'ok',
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS cached_snapshots (
                cache_key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.commit()

    def _close_sync(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    async def async_init(self) -> None:
        """Initialize SQLite schema & photo directory asynchronously."""
        await self._hass.async_add_executor_job(self._ensure_conn)

    async def async_close(self) -> None:
        """Close SQLite connection."""
        await self._hass.async_add_executor_job(self._close_sync)

    # ------------------------------------------------------------------
    # Local photo cache helpers
    # ------------------------------------------------------------------
    def _find_cached_photo_sync(self, photo_key: str) -> str | None:
        safe = _safe_key(photo_key)
        for ext in _IMAGE_EXTS:
            candidate = self.photos_dir / f"{safe}{ext}"
            if candidate.is_file() and candidate.stat().st_size > 0:
                return f"{self._static_photos_url}/{safe}{ext}"
        return None

    def _save_photo_sync(
        self,
        photo_key: str,
        raw_bytes: bytes,
        remote_url: str | None = None,
        content_type: str | None = None,
    ) -> str:
        self.photos_dir.mkdir(parents=True, exist_ok=True)
        safe = _safe_key(photo_key)
        ext = _guess_extension(remote_url, content_type)
        target = self.photos_dir / f"{safe}{ext}"
        tmp = self.photos_dir / f"{safe}{ext}.tmp"
        tmp.write_bytes(raw_bytes)
        tmp.replace(target)
        return f"{self._static_photos_url}/{safe}{ext}"

    async def async_find_cached_photos(
        self, keys: list[str]
    ) -> dict[str, str]:
        """Return mapping `{photo_key: local_static_url}` for photos already on disk."""

        def _scan() -> dict[str, str]:
            self.photos_dir.mkdir(parents=True, exist_ok=True)
            found: dict[str, str] = {}
            for k in keys:
                if url := self._find_cached_photo_sync(k):
                    found[k] = url
            return found

        return await self._hass.async_add_executor_job(_scan)

    async def async_save_photo(
        self,
        photo_key: str,
        raw_bytes: bytes,
        *,
        remote_url: str | None = None,
        content_type: str | None = None,
    ) -> str:
        """Persist downloaded image bytes locally and return static URL path."""
        return await self._hass.async_add_executor_job(
            self._save_photo_sync, photo_key, raw_bytes, remote_url, content_type
        )

    def _read_photo_bytes_sync(self, photo_key: str) -> tuple[bytes, str] | None:
        safe = _safe_key(photo_key)
        for ext in _IMAGE_EXTS:
            candidate = self.photos_dir / f"{safe}{ext}"
            if candidate.is_file() and candidate.stat().st_size > 0:
                return candidate.read_bytes(), _CONTENT_TYPES.get(ext, "image/png")
        return None

    async def async_read_photo_bytes(
        self, photo_key: str
    ) -> tuple[bytes, str] | None:
        """Read cached image bytes + content-type directly from disk (0 HTTP calls)."""
        return await self._hass.async_add_executor_job(
            self._read_photo_bytes_sync, photo_key
        )

    async def async_cache_image_urls(
        self,
        api_client: KickbaseHttpClient,
        urls_by_key: dict[str, str],
        *,
        enabled: bool = True,
        concurrency: int = 4,
    ) -> tuple[dict[str, str], int]:
        """Cache missing remote URLs on disk and return `{key: /api/kickbase_photos/...}`."""
        clean_urls = {
            k: v
            for k, v in urls_by_key.items()
            if k and v and isinstance(v, str) and not v.startswith("/")
        }
        # Preserve already-local URLs directly in result
        cached_map = await self.async_find_cached_photos(list(clean_urls.keys()))
        for k, v in urls_by_key.items():
            if isinstance(v, str) and v.startswith("/"):
                cached_map[k] = v

        if not enabled:
            return cached_map, 0

        missing_keys = [k for k in clean_urls if k not in cached_map]
        if not missing_keys:
            return cached_map, 0

        import asyncio

        sem = asyncio.Semaphore(max(1, concurrency))

        async def _dl_one(pkey: str) -> tuple[str, str | None]:
            url = clean_urls[pkey]
            async with sem:
                dl = await api_client.async_download_bytes(url)
                if not dl:
                    return pkey, None
                raw_bytes, ct = dl
                if not raw_bytes:
                    return pkey, None
                local_url = await self.async_save_photo(
                    pkey, raw_bytes, remote_url=url, content_type=ct
                )
                return pkey, local_url

        results = await asyncio.gather(*(_dl_one(k) for k in missing_keys))
        downloaded = 0
        for pkey, local_url in results:
            if local_url:
                cached_map[pkey] = local_url
                downloaded += 1
        return cached_map, downloaded

    # ------------------------------------------------------------------
    # Sync metadata & bulk transactional persistence
    # ------------------------------------------------------------------
    def _get_player_sync_meta_sync(
        self, league_id: str, player_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        conn = self._ensure_conn()
        with self._lock:
            rows = conn.execute(
                """
                SELECT player_id, details_updated_at, market_value_synced_at, local_image_path,
                       details_json, performance_json, transfers_json, transfer_history_json
                FROM players
                WHERE league_id = ?
                """,
                (league_id,),
            ).fetchall()
            wanted = set(player_ids)
            out: dict[str, dict[str, Any]] = {}
            for r in rows:
                pid = r["player_id"]
                if wanted and pid not in wanted:
                    continue
                out[pid] = {
                    "details_updated_at": r["details_updated_at"],
                    "market_value_synced_at": r["market_value_synced_at"],
                    "local_image_path": r["local_image_path"],
                    "details_json": r["details_json"],
                    "performance_json": r["performance_json"],
                    "transfers_json": r["transfers_json"],
                    "transfer_history_json": r["transfer_history_json"],
                }
            return out

    async def async_get_player_sync_meta(
        self, league_id: str, player_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Read cached per-player sync timestamps & JSON cache before hitting Kickbase API."""
        return await self._hass.async_add_executor_job(
            self._get_player_sync_meta_sync, league_id, player_ids
        )

    def _upsert_bulk_sync_sync(
        self,
        *,
        league_id: str,
        players_payload: list[dict[str, Any]],
        managers_payload: list[dict[str, Any]],
        sync_meta: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Atomically save players, market value histories, status diffs, managers, and sync run."""
        conn = self._ensure_conn()
        now_dt = datetime.now(UTC)
        now_iso = now_dt.isoformat()
        today_str = now_dt.date().isoformat()
        status_changes: list[dict[str, Any]] = []

        with self._lock:
            cur = conn.cursor()
            try:
                cur.execute("BEGIN")

                for item in players_payload:
                    p = item["player"]
                    pid = str(p["id"])
                    scopes = sorted(set(item.get("scopes") or []))
                    details = item.get("details")
                    mv_series_info = item.get("market_value_series")
                    perf = item.get("performance")
                    transfers = item.get("transfers")
                    transfer_hist = item.get("transfer_history")
                    details_refreshed = bool(item.get("details_refreshed", False))
                    mv_refreshed = bool(item.get("mv_refreshed", False))

                    existing = cur.execute(
                        """
                        SELECT details_json, performance_json, transfers_json, transfer_history_json,
                               details_updated_at, market_value_synced_at, local_image_path, local_team_image_path
                        FROM players WHERE league_id = ? AND player_id = ?
                        """,
                        (league_id, pid),
                    ).fetchone()

                    details_json = (
                        json.dumps(details)
                        if details is not None
                        else (existing["details_json"] if existing else "{}")
                    )
                    perf_json = (
                        json.dumps(perf)
                        if perf is not None
                        else (existing["performance_json"] if existing else "[]")
                    )
                    transfers_json = (
                        json.dumps(transfers)
                        if transfers is not None
                        else (existing["transfers_json"] if existing else "{}")
                    )
                    transfer_hist_json = (
                        json.dumps(transfer_hist)
                        if transfer_hist is not None
                        else (existing["transfer_history_json"] if existing else "[]")
                    )
                    details_ts = (
                        now_iso
                        if details_refreshed
                        else (existing["details_updated_at"] if existing else None)
                    )
                    mv_ts = (
                        now_iso
                        if mv_refreshed
                        else (existing["market_value_synced_at"] if existing else None)
                    )

                    local_img = p.get("local_image") or (
                        existing["local_image_path"] if existing else None
                    )
                    local_team_img = p.get("local_team_image") or (
                        existing["local_team_image_path"] if existing else None
                    )
                    if local_img:
                        p["local_image"] = local_img
                    if local_team_img:
                        p["local_team_image"] = local_team_img

                    status_obj = p.get("status") or {}
                    pos_obj = p.get("position") or {}

                    cur.execute(
                        """
                        INSERT INTO players (
                            league_id, player_id, name, full_name, first_name, last_name,
                            team_id, team_name, shirt_number, position_code, position_short, position_name_de,
                            status_code, status_key, status_label_de, status_severity, status_text, matchday_status,
                            market_value, market_value_24h_change, market_value_since_buy, market_value_season_diff,
                            market_value_trend, points, total_points, average_points,
                            goals, assists, yellow_cards, red_cards, seconds_played,
                            owner_user_id, owner_name, is_on_market, is_scouted, market_price,
                            expiry_seconds, expiry_at, scopes_json,
                            remote_image_url, local_image_path, team_image_url, local_team_image_path,
                            player_json, details_json, performance_json, transfers_json, transfer_history_json,
                            updated_at, details_updated_at, market_value_synced_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(league_id, player_id) DO UPDATE SET
                            name = excluded.name,
                            full_name = excluded.full_name,
                            first_name = excluded.first_name,
                            last_name = excluded.last_name,
                            team_id = COALESCE(excluded.team_id, players.team_id),
                            team_name = COALESCE(excluded.team_name, players.team_name),
                            shirt_number = COALESCE(excluded.shirt_number, players.shirt_number),
                            position_code = COALESCE(excluded.position_code, players.position_code),
                            position_short = excluded.position_short,
                            position_name_de = excluded.position_name_de,
                            status_code = excluded.status_code,
                            status_key = excluded.status_key,
                            status_label_de = excluded.status_label_de,
                            status_severity = excluded.status_severity,
                            status_text = COALESCE(excluded.status_text, players.status_text),
                            matchday_status = COALESCE(excluded.matchday_status, players.matchday_status),
                            market_value = excluded.market_value,
                            market_value_24h_change = excluded.market_value_24h_change,
                            market_value_since_buy = excluded.market_value_since_buy,
                            market_value_season_diff = excluded.market_value_season_diff,
                            market_value_trend = excluded.market_value_trend,
                            points = excluded.points,
                            total_points = excluded.total_points,
                            average_points = excluded.average_points,
                            goals = excluded.goals,
                            assists = excluded.assists,
                            yellow_cards = excluded.yellow_cards,
                            red_cards = excluded.red_cards,
                            seconds_played = excluded.seconds_played,
                            owner_user_id = excluded.owner_user_id,
                            owner_name = excluded.owner_name,
                            is_on_market = excluded.is_on_market,
                            is_scouted = excluded.is_scouted,
                            market_price = excluded.market_price,
                            expiry_seconds = excluded.expiry_seconds,
                            expiry_at = excluded.expiry_at,
                            scopes_json = excluded.scopes_json,
                            remote_image_url = COALESCE(excluded.remote_image_url, players.remote_image_url),
                            local_image_path = COALESCE(excluded.local_image_path, players.local_image_path),
                            team_image_url = COALESCE(excluded.team_image_url, players.team_image_url),
                            local_team_image_path = COALESCE(excluded.local_team_image_path, players.local_team_image_path),
                            player_json = excluded.player_json,
                            details_json = excluded.details_json,
                            performance_json = excluded.performance_json,
                            transfers_json = excluded.transfers_json,
                            transfer_history_json = excluded.transfer_history_json,
                            updated_at = excluded.updated_at,
                            details_updated_at = excluded.details_updated_at,
                            market_value_synced_at = excluded.market_value_synced_at
                        """,
                        (
                            league_id,
                            pid,
                            p.get("name"),
                            p.get("full_name"),
                            p.get("first_name"),
                            p.get("last_name"),
                            p.get("team_id"),
                            p.get("team_name"),
                            p.get("shirt_number"),
                            p.get("position_code"),
                            pos_obj.get("short"),
                            pos_obj.get("name_de"),
                            p.get("status_code"),
                            status_obj.get("key"),
                            status_obj.get("label_de"),
                            status_obj.get("severity"),
                            p.get("status_text"),
                            p.get("matchday_status"),
                            int(p.get("market_value") or 0),
                            int(p.get("market_value_24h_change") or 0),
                            int(p.get("market_value_since_buy") or 0),
                            int(p.get("market_value_season_diff") or 0),
                            p.get("market_value_trend"),
                            int(p.get("points") or 0),
                            int(p.get("total_points") or 0),
                            float(p.get("average_points") or 0),
                            int(p.get("goals") or 0),
                            int(p.get("assists") or 0),
                            int(p.get("yellow_cards") or 0),
                            int(p.get("red_cards") or 0),
                            int(p.get("seconds_played") or 0),
                            p.get("owner_user_id"),
                            p.get("owner_name"),
                            1 if p.get("is_on_market") else 0,
                            1 if item.get("is_scouted") else 0,
                            int(p.get("price") or 0),
                            p.get("expiry_seconds"),
                            p.get("expiry_at"),
                            json.dumps(scopes),
                            p.get("image"),
                            local_img,
                            p.get("team_image"),
                            local_team_img,
                            json.dumps(p),
                            details_json,
                            perf_json,
                            transfers_json,
                            transfer_hist_json,
                            now_iso,
                            details_ts,
                            mv_ts,
                        ),
                    )

                    # Market value history: backfill from Kickbase series if fetched, then upsert today's snapshot
                    if isinstance(mv_series_info, dict):
                        for pt in mv_series_info.get("series") or []:
                            rec_date = pt.get("date")
                            if rec_date:
                                cur.execute(
                                    """
                                    INSERT INTO player_market_value_history
                                        (league_id, player_id, recorded_date, market_value, recorded_at, source)
                                    VALUES (?, ?, ?, ?, ?, 'kickbase_api')
                                    ON CONFLICT(league_id, player_id, recorded_date) DO UPDATE SET
                                        market_value = excluded.market_value,
                                        recorded_at = excluded.recorded_at
                                    """,
                                    (league_id, pid, str(rec_date), int(pt.get("market_value") or 0), now_iso),
                                )

                    cur_mv = int(p.get("market_value") or 0)
                    if cur_mv > 0:
                        cur.execute(
                            """
                            INSERT INTO player_market_value_history
                                (league_id, player_id, recorded_date, market_value, recorded_at, source)
                            VALUES (?, ?, ?, ?, ?, 'hourly_sync')
                            ON CONFLICT(league_id, player_id, recorded_date) DO UPDATE SET
                                market_value = excluded.market_value,
                                recorded_at = excluded.recorded_at,
                                source = 'hourly_sync'
                            """,
                            (league_id, pid, today_str, cur_mv, now_iso),
                        )

                    # Deduplicated status/ownership/market history tracking
                    last_st = cur.execute(
                        """
                        SELECT status_code, status_text, matchday_status, owner_user_id, is_on_market
                        FROM player_status_history
                        WHERE league_id = ? AND player_id = ?
                        ORDER BY id DESC LIMIT 1
                        """,
                        (league_id, pid),
                    ).fetchone()

                    cur_is_market = 1 if p.get("is_on_market") else 0
                    cur_state = (
                        p.get("status_code"),
                        p.get("status_text"),
                        p.get("matchday_status"),
                        p.get("owner_user_id"),
                        cur_is_market,
                    )
                    if last_st is None:
                        changed = True
                        prev_state = None
                    else:
                        prev_state = (
                            last_st["status_code"],
                            last_st["status_text"],
                            last_st["matchday_status"],
                            last_st["owner_user_id"],
                            last_st["is_on_market"],
                        )
                        changed = cur_state != prev_state

                    if changed:
                        cur.execute(
                            """
                            INSERT INTO player_status_history (
                                league_id, player_id, recorded_at, status_code, status_key,
                                status_label_de, status_severity, status_text, matchday_status,
                                market_value, owner_user_id, owner_name, is_on_market, market_price
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                league_id,
                                pid,
                                now_iso,
                                p.get("status_code"),
                                status_obj.get("key"),
                                status_obj.get("label_de"),
                                status_obj.get("severity"),
                                p.get("status_text"),
                                p.get("matchday_status"),
                                cur_mv,
                                p.get("owner_user_id"),
                                p.get("owner_name"),
                                cur_is_market,
                                int(p.get("price") or 0),
                            ),
                        )
                        if prev_state is not None:
                            status_changes.append(
                                {
                                    "league_id": league_id,
                                    "player_id": pid,
                                    "player_name": p.get("full_name") or p.get("name"),
                                    "old_status_code": prev_state[0],
                                    "new_status_code": cur_state[0],
                                    "new_status_label": status_obj.get("label_de"),
                                    "status_text": p.get("status_text"),
                                    "old_owner_id": prev_state[3],
                                    "new_owner_id": cur_state[3],
                                    "new_owner_name": p.get("owner_name"),
                                    "is_on_market": bool(cur_is_market),
                                    "market_value": cur_mv,
                                }
                            )

                # Upsert manager snapshots (all managers in the league)
                for mgr in managers_payload:
                    mid = str(mgr["id"])
                    cur.execute(
                        """
                        INSERT INTO manager_snapshots (
                            league_id, manager_id, name, is_admin, rank, matchday_rank,
                            season_points, matchday_points, team_value, points_avg,
                            avatar_url, local_avatar_path, dashboard_json, squad_json,
                            performance_json, transfers_json, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(league_id, manager_id) DO UPDATE SET
                            name = excluded.name,
                            is_admin = excluded.is_admin,
                            rank = excluded.rank,
                            matchday_rank = excluded.matchday_rank,
                            season_points = excluded.season_points,
                            matchday_points = excluded.matchday_points,
                            team_value = excluded.team_value,
                            points_avg = excluded.points_avg,
                            avatar_url = COALESCE(excluded.avatar_url, manager_snapshots.avatar_url),
                            local_avatar_path = COALESCE(excluded.local_avatar_path, manager_snapshots.local_avatar_path),
                            dashboard_json = excluded.dashboard_json,
                            squad_json = excluded.squad_json,
                            performance_json = excluded.performance_json,
                            transfers_json = excluded.transfers_json,
                            updated_at = excluded.updated_at
                        """,
                        (
                            league_id,
                            mid,
                            mgr.get("name"),
                            1 if mgr.get("is_admin") else 0,
                            int(mgr.get("rank") or 0),
                            int(mgr.get("matchday_rank") or 0),
                            int(mgr.get("season_points") or 0),
                            int(mgr.get("matchday_points") or 0),
                            int(mgr.get("team_value") or 0),
                            float(mgr.get("points_avg") or 0),
                            mgr.get("avatar"),
                            mgr.get("local_avatar"),
                            json.dumps(mgr.get("dashboard") or {}),
                            json.dumps(mgr.get("squad") or []),
                            json.dumps(mgr.get("performance") or []),
                            json.dumps(mgr.get("transfers") or []),
                            now_iso,
                        ),
                    )

                # Record sync run audit entry
                cur.execute(
                    """
                    INSERT INTO sync_runs (
                        league_id, started_at, finished_at, players_total, my_squad_count,
                        market_count, rival_players_count, managers_synced, photos_downloaded,
                        api_requests, status, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        league_id,
                        sync_meta.get("started_at") or now_iso,
                        now_iso,
                        int(sync_meta.get("players_total") or len(players_payload)),
                        int(sync_meta.get("my_squad_count") or 0),
                        int(sync_meta.get("market_count") or 0),
                        int(sync_meta.get("rival_players_count") or 0),
                        int(sync_meta.get("managers_synced") or len(managers_payload)),
                        int(sync_meta.get("photos_downloaded") or 0),
                        int(sync_meta.get("api_requests") or 0),
                        sync_meta.get("status") or "ok",
                        sync_meta.get("error"),
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return status_changes

    async def async_upsert_bulk_sync(
        self,
        *,
        league_id: str,
        players_payload: list[dict[str, Any]],
        managers_payload: list[dict[str, Any]],
        sync_meta: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Persist consolidated hourly sync batch to SQLite asynchronously."""
        return await self._hass.async_add_executor_job(
            lambda: self._upsert_bulk_sync_sync(
                league_id=league_id,
                players_payload=players_payload,
                managers_payload=managers_payload,
                sync_meta=sync_meta,
            )
        )

    # ------------------------------------------------------------------
    # Read APIs (zero Kickbase network requests!)
    # ------------------------------------------------------------------
    def _get_player_detail_sync(
        self, league_id: str, player_id: str, *, days: int | None = None
    ) -> dict[str, Any] | None:
        conn = self._ensure_conn()
        with self._lock:
            row = conn.execute(
                "SELECT * FROM players WHERE league_id = ? AND player_id = ?",
                (league_id, str(player_id)),
            ).fetchone()
            if row is None:
                return None

            player_dict = json.loads(row["player_json"] or "{}")
            details_dict = json.loads(row["details_json"] or "{}")
            if row["local_image_path"]:
                player_dict["local_image"] = row["local_image_path"]
            if row["local_team_image_path"]:
                player_dict["local_team_image"] = row["local_team_image_path"]
            if details_dict:
                for k in ("season_match_count", "matchday_summaries", "status_text", "ligainsider_url", "prob_history", "transfer_price", "profit_loss", "lowest_market_value", "highest_market_value"):
                    if k in details_dict and details_dict[k] is not None:
                        player_dict[k] = details_dict[k]
            player_dict["scopes"] = json.loads(row["scopes_json"] or "[]")
            player_dict["db_updated_at"] = row["updated_at"]

            mv_query = """
                SELECT recorded_date, market_value, recorded_at, source
                FROM player_market_value_history
                WHERE league_id = ? AND player_id = ?
            """
            params: list[Any] = [league_id, str(player_id)]
            if days is not None and days > 0:
                cutoff = (datetime.now(UTC) - timedelta(days=int(days))).date().isoformat()
                mv_query += " AND recorded_date >= ?"
                params.append(cutoff)
            mv_query += " ORDER BY recorded_date ASC"

            mv_rows = conn.execute(mv_query, params).fetchall()
            series = [
                {
                    "date": r["recorded_date"],
                    "market_value": r["market_value"],
                    "recorded_at": r["recorded_at"],
                    "source": r["source"],
                }
                for r in mv_rows
            ]
            values = [p["market_value"] for p in series if p["market_value"]]

            status_rows = conn.execute(
                """
                SELECT recorded_at, status_code, status_key, status_label_de, status_severity,
                       status_text, matchday_status, market_value, owner_user_id, owner_name,
                       is_on_market, market_price
                FROM player_status_history
                WHERE league_id = ? AND player_id = ?
                ORDER BY id DESC LIMIT 50
                """,
                (league_id, str(player_id)),
            ).fetchall()
            status_history = [
                {
                    "recorded_at": r["recorded_at"],
                    "status_code": r["status_code"],
                    "status_key": r["status_key"],
                    "status_label_de": r["status_label_de"],
                    "status_severity": r["status_severity"],
                    "status_text": r["status_text"],
                    "matchday_status": r["matchday_status"],
                    "market_value": r["market_value"],
                    "owner_user_id": r["owner_user_id"],
                    "owner_name": r["owner_name"],
                    "is_on_market": bool(r["is_on_market"]),
                    "market_price": r["market_price"],
                }
                for r in status_rows
            ]

            return {
                "from_local_db": True,
                "db_updated_at": row["updated_at"],
                "player": player_dict,
                "market_value": {
                    "series": series,
                    "transfer_price": details_dict.get("transfer_price", 0),
                    "profit_loss": details_dict.get("profit_loss", player_dict.get("market_value_since_buy", 0)),
                    "lowest_market_value": details_dict.get("lowest_market_value") or (min(values) if values else 0),
                    "highest_market_value": details_dict.get("highest_market_value") or (max(values) if values else 0),
                    "is_on_sale": bool(row["is_on_market"]),
                },
                "status_history": status_history,
                "performance": json.loads(row["performance_json"] or "[]"),
                "transfers": json.loads(row["transfers_json"] or "{}"),
                "transfer_history": json.loads(row["transfer_history_json"] or "[]"),
            }

    async def async_get_player_detail(
        self, league_id: str, player_id: str, *, days: int | None = None
    ) -> dict[str, Any] | None:
        """Load full player profile, market value series, and status history from SQLite."""
        return await self._hass.async_add_executor_job(
            lambda: self._get_player_detail_sync(league_id, player_id, days=days)
        )

    def _get_manager_detail_sync(
        self, league_id: str, manager_id: str
    ) -> dict[str, Any] | None:
        conn = self._ensure_conn()
        with self._lock:
            row = conn.execute(
                "SELECT * FROM manager_snapshots WHERE league_id = ? AND manager_id = ?",
                (league_id, str(manager_id)),
            ).fetchone()
            if row is None:
                return None
            dash = json.loads(row["dashboard_json"] or "{}")
            if row["local_avatar_path"]:
                dash["local_avatar"] = row["local_avatar_path"]
            return {
                "from_local_db": True,
                "db_updated_at": row["updated_at"],
                "dashboard": dash,
                "squad": json.loads(row["squad_json"] or "[]"),
                "performance": json.loads(row["performance_json"] or "[]"),
                "transfers": json.loads(row["transfers_json"] or "[]"),
            }

    async def async_get_manager_detail(
        self, league_id: str, manager_id: str
    ) -> dict[str, Any] | None:
        """Load manager dashboard, squad, and transfers directly from SQLite."""
        return await self._hass.async_add_executor_job(
            self._get_manager_detail_sync, league_id, manager_id
        )

    def _query_players_sync(
        self,
        league_id: str,
        *,
        query: str = "",
        scope: str | None = None,
        status_severity: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conn = self._ensure_conn()
        sql = """
            SELECT player_json, scopes_json, local_image_path, local_team_image_path, updated_at, is_scouted
            FROM players
            WHERE league_id = ?
        """
        params: list[Any] = [league_id]
        if query:
            q_like = f"%{query.strip().lower()}%"
            sql += " AND (LOWER(COALESCE(full_name,'')) LIKE ? OR LOWER(COALESCE(name,'')) LIKE ? OR LOWER(COALESCE(owner_name,'')) LIKE ?)"
            params.extend([q_like, q_like, q_like])
        if scope and scope != "all":
            sql += " AND scopes_json LIKE ?"
            params.append(f'%"{scope}"%')
        if status_severity and status_severity != "all":
            if status_severity == "issues":
                sql += " AND status_severity IN ('warning', 'danger')"
            else:
                sql += " AND status_severity = ?"
                params.append(status_severity)

        sql += " ORDER BY market_value DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))

        with self._lock:
            rows = conn.execute(sql, params).fetchall()
            items: list[dict[str, Any]] = []
            for r in rows:
                p = json.loads(r["player_json"] or "{}")
                p["scopes"] = json.loads(r["scopes_json"] or "[]")
                p["is_scouted"] = bool(r["is_scouted"])
                if r["local_image_path"]:
                    p["local_image"] = r["local_image_path"]
                if r["local_team_image_path"]:
                    p["local_team_image"] = r["local_team_image_path"]
                p["db_updated_at"] = r["updated_at"]
                items.append(p)
            return items

    async def async_query_players(
        self,
        league_id: str,
        *,
        query: str = "",
        scope: str | None = None,
        status_severity: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query locally persisted players by name, owner, scope, or fitness status."""
        return await self._hass.async_add_executor_job(
            lambda: self._query_players_sync(
                league_id,
                query=query,
                scope=scope,
                status_severity=status_severity,
                limit=limit,
            )
        )

    def _get_stats_sync(self, league_id: str | None = None) -> dict[str, Any]:
        conn = self._ensure_conn()
        with self._lock:
            where = "WHERE league_id = ?" if league_id else ""
            args = (league_id,) if league_id else ()

            players_count = conn.execute(
                f"SELECT COUNT(*) FROM players {where}", args
            ).fetchone()[0]
            mv_points = conn.execute(
                f"SELECT COUNT(*) FROM player_market_value_history {where}", args
            ).fetchone()[0]
            status_events = conn.execute(
                f"SELECT COUNT(*) FROM player_status_history {where}", args
            ).fetchone()[0]
            managers_count = conn.execute(
                f"SELECT COUNT(*) FROM manager_snapshots {where}", args
            ).fetchone()[0]

            scope_counts = {"my_squad": 0, "market": 0, "rival_squad": 0}
            for r in conn.execute(f"SELECT scopes_json FROM players {where}", args).fetchall():
                try:
                    sc = set(json.loads(r["scopes_json"] or "[]"))
                except ValueError:
                    sc = set()
                for key in scope_counts:
                    if key in sc:
                        scope_counts[key] += 1

            last_run_row = conn.execute(
                f"SELECT * FROM sync_runs {where} ORDER BY id DESC LIMIT 1", args
            ).fetchone()
            last_run = dict(last_run_row) if last_run_row else None

            recent_runs = [
                dict(r)
                for r in conn.execute(
                    f"SELECT * FROM sync_runs {where} ORDER BY id DESC LIMIT 10", args
                ).fetchall()
            ]

            photo_files = (
                sum(1 for p in self.photos_dir.iterdir() if p.is_file() and not p.name.endswith(".tmp"))
                if self.photos_dir.is_dir()
                else 0
            )
            db_size_bytes = self.db_path.stat().st_size if self.db_path.is_file() else 0

            return {
                "players_count": players_count,
                "my_squad_count": scope_counts["my_squad"],
                "market_count": scope_counts["market"],
                "rival_players_count": scope_counts["rival_squad"],
                "market_value_points": mv_points,
                "status_events_count": status_events,
                "managers_count": managers_count,
                "photos_cached": photo_files,
                "db_size_kb": round(db_size_bytes / 1024.0, 1),
                "last_sync": last_run,
                "last_sync_at": last_run["finished_at"] if last_run else None,
                "recent_runs": recent_runs,
            }

    async def async_get_stats(self, league_id: str | None = None) -> dict[str, Any]:
        """Return database and photo cache metrics."""
        return await self._hass.async_add_executor_job(self._get_stats_sync, league_id)

    # ------------------------------------------------------------------
    # Full module & detail snapshot persistence (strict DB-only GUI reads)
    # ------------------------------------------------------------------
    def _save_snapshots_batch_sync(self, items: dict[str, dict[str, Any]]) -> None:
        if not items:
            return
        conn = self._ensure_conn()
        now_iso = datetime.now(UTC).isoformat()
        with self._lock:
            cur = conn.cursor()
            try:
                cur.execute("BEGIN")
                for key, payload in items.items():
                    cur.execute(
                        """
                        INSERT INTO cached_snapshots (cache_key, payload_json, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(cache_key) DO UPDATE SET
                            payload_json = excluded.payload_json,
                            updated_at = excluded.updated_at
                        """,
                        (str(key), json.dumps(payload), now_iso),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    async def async_save_snapshot(
        self, cache_key: str, payload: dict[str, Any]
    ) -> None:
        """Persist a normalized JSON snapshot in SQLite."""
        await self.async_save_snapshots_batch({cache_key: payload})

    async def async_save_snapshots_batch(
        self, items: dict[str, dict[str, Any]]
    ) -> None:
        """Atomically persist multiple JSON snapshots in SQLite."""
        await self._hass.async_add_executor_job(
            self._save_snapshots_batch_sync, items
        )

    def _get_snapshot_sync(
        self, cache_key: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        conn = self._ensure_conn()
        with self._lock:
            row = conn.execute(
                "SELECT payload_json, updated_at FROM cached_snapshots WHERE cache_key = ?",
                (str(cache_key),),
            ).fetchone()
            if row is None:
                return None, None
            try:
                return json.loads(row["payload_json"]), row["updated_at"]
            except ValueError:
                return None, None

    async def async_get_snapshot(
        self, cache_key: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Load cached JSON snapshot and timestamp from SQLite."""
        return await self._hass.async_add_executor_job(
            self._get_snapshot_sync, cache_key
        )
