"""Data normalization helpers and models for Kickbase API v4 responses."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ..const import (
    ACTIVITY_FEED_TYPES,
    DEFAULT_IMAGE_BASE_URL,
    MARKET_TREND_MAP,
    MATCH_STATUS_MAP,
    PLAYER_STATUS_MAP,
    POSITIONS,
)

_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def resolve_image_url(
    path: str | None, image_base_url: str = DEFAULT_IMAGE_BASE_URL
) -> str | None:
    """Resolve a Kickbase relative CDN path to an absolute URL."""
    if not path:
        return None
    if path.startswith(("http://", "https://")):
        return path
    base = image_base_url.rstrip("/")
    rel = path.lstrip("/")
    return f"{base}/{rel}"


def epoch_days_to_iso(days: int | float | None) -> str | None:
    """Convert Kickbase integer epoch day (days since 1970-01-01) to ISO date string."""
    if days is None:
        return None
    try:
        dt = _UNIX_EPOCH + timedelta(days=int(days))
    except (TypeError, ValueError, OverflowError):
        return None
    return dt.date().isoformat()


def parse_iso_datetime(value: str | None) -> datetime | None:
    """Parse Kickbase ISO-8601 timestamp safely."""
    if not value or not isinstance(value, str):
        return None
    if value.startswith("1970-00-00"):
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


def decode_position(pos: int | None) -> dict[str, str]:
    """Decode numeric Kickbase position (1-4)."""
    if pos is None:
        return {"key": "unknown", "short": "?", "name_de": "Unbekannt", "name_en": "Unknown"}
    return POSITIONS.get(
        int(pos),
        {"key": "unknown", "short": "?", "name_de": "Unbekannt", "name_en": "Unknown"},
    )


def decode_player_status(status: int | None) -> dict[str, str]:
    """Decode Kickbase player status bitmask / code (`st`)."""
    if status is None:
        return {"key": "unknown", "label_de": "Unbekannt", "label_en": "Unknown", "severity": "muted"}
    code = int(status)
    if code in PLAYER_STATUS_MAP:
        return PLAYER_STATUS_MAP[code]
    # Bitmask fallback if multiple flags are set
    labels_de: list[str] = []
    labels_en: list[str] = []
    severity = "ok"
    for bit, info in PLAYER_STATUS_MAP.items():
        if bit > 0 and (code & bit):
            labels_de.append(info["label_de"])
            labels_en.append(info["label_en"])
            if info["severity"] == "danger":
                severity = "danger"
            elif info["severity"] == "warning" and severity != "danger":
                severity = "warning"
    if labels_de:
        return {
            "key": f"code_{code}",
            "label_de": ", ".join(labels_de),
            "label_en": ", ".join(labels_en),
            "severity": severity,
        }
    return {
        "key": f"code_{code}",
        "label_de": f"Status {code}",
        "label_en": f"Status {code}",
        "severity": "muted",
    }


def decode_market_trend(trend: int | None) -> str:
    """Decode market value trend integer (`mvt`)."""
    if trend is None:
        return "stable"
    return MARKET_TREND_MAP.get(int(trend), "stable")


def decode_match_status(status: int | None) -> str:
    """Decode match status code (`mst` / `st`)."""
    if status is None:
        return "unknown"
    return MATCH_STATUS_MAP.get(int(status), "unknown")


STARTING_PROB_MAP: dict[int, dict[str, Any]] = {
    1: {"code": 1, "key": "certain", "label_de": "Sicher (S11)", "short": "100%", "severity": "ok"},
    2: {"code": 2, "key": "expected", "label_de": "Erwartet", "short": "75%", "severity": "ok"},
    3: {"code": 3, "key": "uncertain", "label_de": "Unsicher", "short": "50%", "severity": "warning"},
    4: {"code": 4, "key": "unlikely", "label_de": "Unwahrscheinlich", "short": "25%", "severity": "warning"},
    5: {"code": 5, "key": "excluded", "label_de": "Ausgeschlossen", "short": "0%", "severity": "danger"},
}


def decode_starting_prob(
    prob: Any = None, prob_history: Any = None
) -> dict[str, Any] | None:
    """Decode Kickbase starting XI probability (`prob` / `prb` / `ph`)."""
    code = prob
    if code is None and isinstance(prob_history, list) and prob_history:
        last = prob_history[-1]
        if isinstance(last, dict):
            code = last.get("p") if last.get("p") is not None else last.get("prob")
    if code is None:
        return None
    try:
        int_code = int(code)
    except (TypeError, ValueError):
        return None
    return STARTING_PROB_MAP.get(
        int_code,
        {"code": int_code, "key": f"prob_{int_code}", "label_de": f"S11 ({int_code})", "short": str(int_code), "severity": "muted"},
    )


def decode_activity_type(activity_type: int | None) -> dict[str, str]:
    """Decode activity feed item type (`t`)."""
    if activity_type is None:
        return {"key": "unknown", "label_de": "Aktivität", "label_en": "Activity"}
    return ACTIVITY_FEED_TYPES.get(
        int(activity_type),
        {"key": f"type_{activity_type}", "label_de": f"Ereignis #{activity_type}", "label_en": f"Event #{activity_type}"},
    )


def normalize_player(
    raw: dict[str, Any],
    image_base_url: str = DEFAULT_IMAGE_BASE_URL,
) -> dict[str, Any]:
    """Normalize heterogeneous Kickbase player payloads into a consistent schema."""
    player_id = str(raw.get("pi") or raw.get("i") or "")
    first_name = raw.get("fn") or ""
    last_name = raw.get("ln") or raw.get("pn") or raw.get("n") or ""
    full_name = f"{first_name} {last_name}".strip() if first_name and last_name else last_name or first_name
    pos_code = raw.get("pos")
    status_code = raw.get("st")
    mvt_code = raw.get("mvt")
    prob_raw = raw.get("prob") if raw.get("prob") is not None else raw.get("prb")
    starting_prob = decode_starting_prob(prob_raw, raw.get("ph"))

    return {
        "id": player_id,
        "name": last_name or full_name,
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "shirt_number": raw.get("shn"),
        "team_id": str(raw.get("tid")) if raw.get("tid") is not None else None,
        "team_name": raw.get("tn"),
        "position_code": pos_code,
        "position": decode_position(pos_code),
        "status_code": status_code,
        "status": decode_player_status(status_code),
        "status_list": raw.get("stl", []),
        "status_text": raw.get("stxt"),
        "last_status": raw.get("lst"),
        "matchday_status": raw.get("mdst"),
        "starting_prob_code": starting_prob["code"] if starting_prob else None,
        "starting_prob": starting_prob,
        "lineup_order": raw.get("lo"),
        "is_captain": bool(raw.get("ictp", False)),
        "market_value": raw.get("mv", 0),
        "current_value": raw.get("cv", raw.get("mv", 0)),
        "market_value_trend_code": mvt_code,
        "market_value_trend": decode_market_trend(mvt_code),
        "market_value_24h_change": raw.get("tfhmvt", 0),
        "market_value_since_buy": raw.get("mvgl", 0),
        "market_value_season_diff": raw.get("sdmvt", 0),
        "price": raw.get("prc", 0),
        "points": raw.get("p", 0),
        "total_points": raw.get("tp", raw.get("p", 0)),
        "average_points": raw.get("ap", 0),
        "goals": raw.get("g", 0),
        "assists": raw.get("a", 0),
        "yellow_cards": raw.get("y", 0),
        "red_cards": raw.get("r", 0),
        "seconds_played": raw.get("sec", 0),
        "is_on_market": bool(raw.get("iotm", False)),
        "offer_count": raw.get("ofc", 0),
        "owner_user_id": str(raw.get("oui")) if raw.get("oui") is not None else None,
        "owner_name": raw.get("onm") or raw.get("u", {}).get("n") if isinstance(raw.get("u"), dict) else raw.get("onm"),
        "expiry_seconds": raw.get("exs"),
        "expiry_at": raw.get("dt"),
        "match_id": str(raw.get("mi")) if raw.get("mi") is not None else None,
        "match_date": raw.get("md"),
        "match_status": raw.get("mst"),
        "home_team_id": str(raw.get("t1")) if raw.get("t1") is not None else None,
        "away_team_id": str(raw.get("t2")) if raw.get("t2") is not None else None,
        "home_team_image": resolve_image_url(raw.get("t1im"), image_base_url),
        "away_team_image": resolve_image_url(raw.get("t2im"), image_base_url),
        "opponent": {
            "id": str(raw["ot"].get("i")) if isinstance(raw.get("ot"), dict) and raw["ot"].get("i") is not None else None,
            "image": resolve_image_url(raw["ot"].get("tim"), image_base_url) if isinstance(raw.get("ot"), dict) else None,
        }
        if raw.get("ot")
        else None,
        "image": resolve_image_url(raw.get("pim"), image_base_url),
        "ligainsider_image": resolve_image_url(raw.get("plpim"), image_base_url),
    }


def normalize_market_value_series(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize `/marketvalue/{timeframe}` response with human-readable ISO dates."""
    points = []
    for item in raw.get("it", []) or []:
        dt_val = item.get("dt")
        points.append(
            {
                "epoch_day": dt_val,
                "date": epoch_days_to_iso(dt_val) if isinstance(dt_val, (int, float)) else dt_val,
                "market_value": item.get("mv", 0),
            }
        )
    return {
        "series": points,
        "transfer_price": raw.get("trp", 0),
        "profit_loss": raw.get("prlo", 0),
        "lowest_market_value": raw.get("lmv", 0),
        "highest_market_value": raw.get("hmv", 0),
        "is_on_sale": raw.get("iso", False),
    }
