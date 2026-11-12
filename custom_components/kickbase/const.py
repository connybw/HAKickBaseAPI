"""Constants for the Kickbase integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "kickbase"
INTEGRATION_NAME: Final = "Kickbase"
VERSION: Final = "1.0.0"

API_BASE_URL: Final = "https://api.kickbase.com"
DEFAULT_IMAGE_BASE_URL: Final = "https://kickbase.b-cdn.net/"

PANEL_URL_PATH: Final = "kickbase"
PANEL_TITLE: Final = "Kickbase"
PANEL_ICON: Final = "mdi:soccer"
STATIC_URL_PATH: Final = "/api/kickbase_static"
STATIC_PHOTOS_URL_PATH: Final = "/api/kickbase_photos"

# Config & Options keys
CONF_EMAIL: Final = "email"
CONF_PASSWORD: Final = "password"
CONF_LEAGUES: Final = "leagues"
CONF_PRIMARY_LEAGUE: Final = "primary_league"
CONF_MODULES: Final = "modules"
CONF_ENABLE_PLAYER_ENTITIES: Final = "enable_player_entities"
CONF_ENABLE_SIDEBAR_PANEL: Final = "enable_sidebar_panel"
CONF_MARKET_VALUE_TIMEFRAME: Final = "market_value_timeframe"
CONF_SCAN_INTERVALS: Final = "scan_intervals"
CONF_DEFAULT_COMPETITION_ID: Final = "default_competition_id"
CONF_SYNC_INTERVAL: Final = "sync_interval"
CONF_CACHE_PHOTOS: Final = "cache_photos"
CONF_FETCH_PLAYER_DETAILS: Final = "fetch_player_details"
CONF_ADAPTIVE_LIVE_POLLING: Final = "adaptive_live_polling"

# Modular Data Modules
MODULE_LEAGUE_OVERVIEW: Final = "league_overview"
MODULE_SQUAD_LINEUP: Final = "squad_lineup"
MODULE_MARKET_TRANSFERS: Final = "market_transfers"
MODULE_LIVE_MATCHDAY: Final = "live_matchday"
MODULE_FEED_ACHIEVEMENTS: Final = "feed_achievements"
MODULE_NEWS_PREDICTIONS: Final = "news_predictions"
MODULE_CHALLENGES: Final = "challenges"

ALL_MODULES: Final[tuple[str, ...]] = (
    MODULE_LEAGUE_OVERVIEW,
    MODULE_SQUAD_LINEUP,
    MODULE_MARKET_TRANSFERS,
    MODULE_LIVE_MATCHDAY,
    MODULE_FEED_ACHIEVEMENTS,
    MODULE_NEWS_PREDICTIONS,
    MODULE_CHALLENGES,
)

DEFAULT_ENABLED_MODULES: Final[list[str]] = list(ALL_MODULES)

# Default polling intervals (in seconds) — 3600s (1 hour) consolidated sync to minimize API calls
DEFAULT_INTERVALS: Final[dict[str, int]] = {
    "account": 3600,
    "league_sync": 3600,
    MODULE_LEAGUE_OVERVIEW: 3600,
    MODULE_SQUAD_LINEUP: 3600,
    MODULE_MARKET_TRANSFERS: 3600,
    MODULE_LIVE_MATCHDAY: 3600,
    MODULE_FEED_ACHIEVEMENTS: 3600,
    MODULE_NEWS_PREDICTIONS: 3600,
    MODULE_CHALLENGES: 3600,
}

DEFAULT_SYNC_INTERVAL_SECONDS: Final = 3600
DEFAULT_DETAILS_REFRESH_HOURS: Final = 12
LIVE_MATCHDAY_ACTIVE_INTERVAL: Final = timedelta(seconds=60)
MIN_POLL_INTERVAL_SECONDS: Final = 300
MAX_POLL_INTERVAL_SECONDS: Final = 86400

DEFAULT_MARKET_VALUE_TIMEFRAME: Final = 92
DEFAULT_COMPETITION_ID: Final = "1"  # 1. Bundesliga

# Event names fired onto HA event bus
EVENT_PREFIX: Final = "kickbase"
EVENT_NEW_ACTIVITY: Final = f"{EVENT_PREFIX}_new_activity"
EVENT_SCOUTED_ON_MARKET: Final = f"{EVENT_PREFIX}_scouted_on_market"
EVENT_NEGATIVE_BUDGET: Final = f"{EVENT_PREFIX}_negative_budget"
EVENT_LIVE_PLAYER_EVENT: Final = f"{EVENT_PREFIX}_live_player_event"
EVENT_PLAYER_STATUS_CHANGED: Final = f"{EVENT_PREFIX}_player_status_changed"

# Kickbase Player Positions
POSITIONS: Final[dict[int, dict[str, str]]] = {
    1: {"key": "gk", "short": "TW", "name_de": "Torwart", "name_en": "Goalkeeper"},
    2: {"key": "def", "short": "ABW", "name_de": "Abwehr", "name_en": "Defender"},
    3: {"key": "mid", "short": "MF", "name_de": "Mittelfeld", "name_en": "Midfielder"},
    4: {"key": "fwd", "short": "ST", "name_de": "Sturm", "name_en": "Forward"},
}

# Kickbase Player Fitness / Availability Status Codes (`st`)
PLAYER_STATUS_MAP: Final[dict[int, dict[str, str]]] = {
    0: {"key": "fit", "label_de": "Fit", "label_en": "Fit", "severity": "ok"},
    1: {"key": "injured", "label_de": "Verletzt", "label_en": "Injured", "severity": "danger"},
    2: {"key": "knock", "label_de": "Angeschlagen", "label_en": "Doubtful / Knock", "severity": "warning"},
    4: {"key": "rehab", "label_de": "Aufbautraining", "label_en": "Rehab / Training", "severity": "warning"},
    8: {"key": "red_card", "label_de": "Rote Karte", "label_en": "Red Card", "severity": "danger"},
    16: {"key": "yellow_red", "label_de": "Gelb-Rote Karte", "label_en": "Second Yellow", "severity": "danger"},
    32: {"key": "five_yellow", "label_de": "5. Gelbe Karte", "label_en": "5th Yellow Card", "severity": "danger"},
    64: {"key": "no_team", "label_de": "Nicht im Team", "label_en": "Left Club / Inactive", "severity": "muted"},
    128: {"key": "unknown", "label_de": "Nicht verfügbar", "label_en": "Unavailable", "severity": "muted"},
    256: {"key": "loaned", "label_de": "Verliehen / Abwesend", "label_en": "Absent", "severity": "muted"},
}

# Market Value Trend (`mvt`)
MARKET_TREND_MAP: Final[dict[int, str]] = {
    0: "stable",
    1: "rising",
    2: "falling",
}

# Match Status (`mst` / `st`)
MATCH_STATUS_MAP: Final[dict[int, str]] = {
    0: "scheduled",
    1: "live",
    2: "finished",
    4: "half_time",
    8: "postponed",
}

# Activity Feed Types (`t`) — best-effort mapping with safe fallback
ACTIVITY_FEED_TYPES: Final[dict[int, dict[str, str]]] = {
    1: {"key": "login", "label_de": "Login", "label_en": "Login"},
    2: {"key": "transfer", "label_de": "Transfer", "label_en": "Transfer"},
    3: {"key": "market_list", "label_de": "Auf Transfermarkt", "label_en": "Listed on Market"},
    12: {"key": "transfer_won", "label_de": "Transfer abgeschlossen", "label_en": "Transfer Completed"},
    14: {"key": "achievement", "label_de": "Erfolg freigeschaltet", "label_en": "Achievement Unlocked"},
    15: {"key": "matchday_result", "label_de": "Spieltagsergebnis", "label_en": "Matchday Result"},
    17: {"key": "league_join", "label_de": "Liga beigetreten", "label_en": "Joined League"},
    22: {"key": "bonus", "label_de": "Start-/Tagesbonus", "label_en": "Bonus"},
    26: {"key": "system", "label_de": "Liga-Ereignis", "label_en": "League Event"},
}
