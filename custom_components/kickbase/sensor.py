"""Sensor platform for Kickbase (modular per-module & per-league sensors)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api.models import parse_iso_datetime
from .const import (
    CONF_ENABLE_PLAYER_ENTITIES,
    MODULE_CHALLENGES,
    MODULE_FEED_ACHIEVEMENTS,
    MODULE_LEAGUE_OVERVIEW,
    MODULE_LIVE_MATCHDAY,
    MODULE_MARKET_TRANSFERS,
    MODULE_NEWS_PREDICTIONS,
    MODULE_SQUAD_LINEUP,
)
from .entity import (
    build_account_device_info,
    build_challenges_device_info,
    build_league_device_info,
)

if TYPE_CHECKING:
    from . import KickbaseConfigEntry
    from .coordinators import KickbaseRuntimeData, LeagueCoordinatorSet


@dataclass(frozen=True, kw_only=True)
class KickbaseSensorDescription(SensorEntityDescription):
    """Describes a Kickbase sensor backed by a coordinator."""

    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


ACCOUNT_SENSORS: tuple[KickbaseSensorDescription, ...] = (
    KickbaseSensorDescription(
        key="account_notifications",
        name="Benachrichtigungen",
        icon="mdi:bell-badge-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("user") or {}).get("notifications", 0),
        attrs_fn=lambda d: {
            "user_id": (d.get("user") or {}).get("id"),
            "name": (d.get("user") or {}).get("name"),
            "email": (d.get("user") or {}).get("email"),
            "has_pro": (d.get("user") or {}).get("has_pro"),
            "pro_expiry": (d.get("user") or {}).get("pro_expiry"),
        },
    ),
    KickbaseSensorDescription(
        key="account_leagues_count",
        name="Aktive Ligen",
        icon="mdi:trophy-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.get("leagues") or {}),
        attrs_fn=lambda d: {
            "leagues": [
                {"id": lid, "name": info.get("name"), "rank": info.get("rank")}
                for lid, info in (d.get("leagues") or {}).items()
            ]
        },
    ),
)

LEAGUE_OVERVIEW_SENSORS: tuple[KickbaseSensorDescription, ...] = (
    KickbaseSensorDescription(
        key="budget",
        name="Budget",
        icon="mdi:cash",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: (d.get("me") or {}).get("budget"),
        attrs_fn=lambda d: {
            "max_bid": (d.get("me") or {}).get("max_bid"),
            "is_negative": (d.get("me") or {}).get("is_negative_budget"),
        },
    ),
    KickbaseSensorDescription(
        key="max_bid",
        name="Max. Gebot",
        icon="mdi:cash-plus",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: (d.get("me") or {}).get("max_bid"),
    ),
    KickbaseSensorDescription(
        key="team_value",
        name="Teamwert",
        icon="mdi:chart-line",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: (d.get("me") or {}).get("team_value"),
    ),
    KickbaseSensorDescription(
        key="rank",
        name="Tabellenplatz",
        icon="mdi:podium-gold",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("me") or {}).get("rank"),
        attrs_fn=lambda d: {
            "matchday_rank": (d.get("me") or {}).get("matchday_rank"),
            "manager_count": (d.get("league") or {}).get("manager_count"),
            "standings_top5": [
                {
                    "rank": m.get("rank"),
                    "name": m.get("name"),
                    "points": m.get("season_points"),
                    "team_value": m.get("team_value"),
                }
                for m in (d.get("standings") or [])[:5]
            ],
        },
    ),
    KickbaseSensorDescription(
        key="season_points",
        name="Gesamtpunkte",
        icon="mdi:counter",
        native_unit_of_measurement="Pkt",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: (d.get("me") or {}).get("season_points"),
    ),
    KickbaseSensorDescription(
        key="matchday_points",
        name="Spieltagspunkte",
        icon="mdi:scoreboard-outline",
        native_unit_of_measurement="Pkt",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("me") or {}).get("matchday_points"),
        attrs_fn=lambda d: {
            "matchday": (d.get("league") or {}).get("matchday"),
            "season": (d.get("league") or {}).get("season"),
        },
    ),
)

SQUAD_LINEUP_SENSORS: tuple[KickbaseSensorDescription, ...] = (
    KickbaseSensorDescription(
        key="squad_size",
        name="Kadergröße",
        icon="mdi:account-group",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("summary") or {}).get("count", 0),
        attrs_fn=lambda d: {
            "average_points": (d.get("summary") or {}).get("average_player_points"),
            "injured_or_suspended": (d.get("summary") or {}).get("injured_or_suspended_count"),
        },
    ),
    KickbaseSensorDescription(
        key="squad_24h_trend",
        name="Marktwert-Trend 24h",
        icon="mdi:trending-up",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("summary") or {}).get("total_24h_change", 0),
        attrs_fn=lambda d: {
            "rising_players": (d.get("summary") or {}).get("rising_count", 0),
            "falling_players": (d.get("summary") or {}).get("falling_count", 0),
            "total_profit_loss": (d.get("summary") or {}).get("total_profit_loss", 0),
            "total_season_diff": (d.get("summary") or {}).get("total_season_diff", 0),
        },
    ),
    KickbaseSensorDescription(
        key="lineup_formation",
        name="Aufstellung Formation",
        icon="mdi:soccer-field",
        value_fn=lambda d: (d.get("lineup") or {}).get("formation"),
        attrs_fn=lambda d: {
            "player_count": (d.get("lineup") or {}).get("player_count", 0),
            "confirmed_count": (d.get("lineup") or {}).get("confirmed_count", 0),
            "captain": (d.get("lineup") or {}).get("captain_name"),
            "issues": (d.get("lineup") or {}).get("issues", []),
            "players": [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "pos": p.get("position", {}).get("short"),
                    "status": p.get("status", {}).get("label_de"),
                }
                for p in (d.get("lineup") or {}).get("players", [])
            ],
        },
    ),
    KickbaseSensorDescription(
        key="lineup_lock_at",
        name="Aufstellungs-Deadline",
        icon="mdi:timer-sand",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: parse_iso_datetime((d.get("lineup") or {}).get("lock_at")),
        attrs_fn=lambda d: {"matchday": (d.get("lineup") or {}).get("matchday")},
    ),
)

MARKET_TRANSFERS_SENSORS: tuple[KickbaseSensorDescription, ...] = (
    KickbaseSensorDescription(
        key="market_count",
        name="Transfermarkt Spieler",
        icon="mdi:storefront-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("market_count", 0),
        attrs_fn=lambda d: {
            "expiring_soon": d.get("expiring_soon_count", 0),
            "scouted_on_market": d.get("scouted_on_market_count", 0),
            "top_players": [
                {
                    "name": p.get("name"),
                    "pos": p.get("position", {}).get("short"),
                    "mv": p.get("market_value"),
                    "price": p.get("price"),
                    "exs": p.get("expiry_seconds"),
                }
                for p in (d.get("market") or [])[:8]
            ],
        },
    ),
    KickbaseSensorDescription(
        key="scouted_count",
        name="Scout-Liste",
        icon="mdi:binoculars",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("scouted_count", 0),
        attrs_fn=lambda d: {
            "on_market_count": d.get("scouted_on_market_count", 0),
            "on_market_names": [p.get("name") for p in (d.get("scouted_on_market") or [])],
        },
    ),
    KickbaseSensorDescription(
        key="market_value_update_at",
        name="Nächstes Marktwert-Update",
        icon="mdi:update",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: parse_iso_datetime(d.get("market_value_update_at")),
    ),
)

LIVE_MATCHDAY_SENSORS: tuple[KickbaseSensorDescription, ...] = (
    KickbaseSensorDescription(
        key="current_matchday",
        name="Aktueller Spieltag",
        icon="mdi:calendar-today",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("current_matchday"),
        attrs_fn=lambda d: {
            "is_live": d.get("is_live", False),
            "live_match_count": d.get("live_match_count", 0),
        },
    ),
    KickbaseSensorDescription(
        key="live_points",
        name="Live-Punkte",
        icon="mdi:lightning-bolt",
        native_unit_of_measurement="Pkt",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("live_points", 0),
        attrs_fn=lambda d: {
            "live_rank": d.get("live_rank"),
            "is_live": d.get("is_live", False),
        },
    ),
)

FEED_ACHIEVEMENTS_SENSORS: tuple[KickbaseSensorDescription, ...] = (
    KickbaseSensorDescription(
        key="latest_activity",
        name="Letzte Liga-Aktivität",
        icon="mdi:rss",
        value_fn=lambda d: (
            ((d.get("latest_activity") or {}).get("type") or {}).get("label_de")
            or "Keine Aktivität"
        ),
        attrs_fn=lambda d: {
            "latest": d.get("latest_activity"),
            "recent_count": len(d.get("activities") or []),
        },
    ),
    KickbaseSensorDescription(
        key="achievements_earned",
        name="Erfolge freigeschaltet",
        icon="mdi:medal-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("earned_achievements_count", 0),
        attrs_fn=lambda d: {"total": d.get("total_achievements_count", 0)},
    ),
)

NEWS_SENSORS: tuple[KickbaseSensorDescription, ...] = (
    KickbaseSensorDescription(
        key="latest_news_headline",
        name="Letzte Bundesliga-News",
        icon="mdi:newspaper-variant-outline",
        value_fn=lambda d: (d.get("latest_headline") or "Keine News")[:255],
        attrs_fn=lambda d: {
            "stage_count": len(d.get("stage") or []),
        },
    ),
)

CHALLENGE_SENSORS: tuple[KickbaseSensorDescription, ...] = (
    KickbaseSensorDescription(
        key="challenge_division",
        name="Challenge Division",
        icon="mdi:shield-star-outline",
        value_fn=lambda d: (d.get("profile") or {}).get("division_name") or "Unbekannt",
        attrs_fn=lambda d: d.get("profile") or {},
    ),
    KickbaseSensorDescription(
        key="challenge_skill_points",
        name="Skill Points",
        icon="mdi:star-four-points",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: (d.get("profile") or {}).get("skill_points", 0),
        attrs_fn=lambda d: {
            "available_skill_points": (d.get("profile") or {}).get("available_skill_points", 0),
            "active_challenges": len(d.get("active_challenges") or []),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KickbaseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kickbase sensors modularly based on enabled modules and leagues."""
    runtime: KickbaseRuntimeData = entry.runtime_data
    account_data = runtime.account.data or {}
    user_info = account_data.get("user") or {}
    user_id = str(user_info.get("id") or entry.entry_id)
    user_name = str(user_info.get("name") or "Manager")

    entities: list[SensorEntity] = []

    # Account sensors
    account_device = build_account_device_info(user_id, user_name)
    for desc in ACCOUNT_SENSORS:
        entities.append(
            KickbaseCoordinatorSensor(
                coordinator=runtime.account,
                description=desc,
                unique_id=f"{entry.entry_id}_{desc.key}",
                device_info=account_device,
            )
        )

    # Global module sensors
    if runtime.news_predictions is not None and runtime.is_module_enabled(MODULE_NEWS_PREDICTIONS):
        for desc in NEWS_SENSORS:
            entities.append(
                KickbaseCoordinatorSensor(
                    coordinator=runtime.news_predictions,
                    description=desc,
                    unique_id=f"{entry.entry_id}_{desc.key}",
                    device_info=account_device,
                )
            )

    if runtime.challenges is not None and runtime.is_module_enabled(MODULE_CHALLENGES):
        ch_device = build_challenges_device_info(user_id)
        for desc in CHALLENGE_SENSORS:
            entities.append(
                KickbaseCoordinatorSensor(
                    coordinator=runtime.challenges,
                    description=desc,
                    unique_id=f"{entry.entry_id}_{desc.key}",
                    device_info=ch_device,
                )
            )

    # Per-league modular sensors
    enable_player_entities = bool(entry.options.get(CONF_ENABLE_PLAYER_ENTITIES, False))
    for lid, lset in runtime.leagues.items():
        league_device = build_league_device_info(
            lid,
            lset.league_name,
            (account_data.get("leagues") or {}).get(lid, {}).get("competition_name"),
        )

        if lset.overview is not None and runtime.is_module_enabled(MODULE_LEAGUE_OVERVIEW):
            for desc in LEAGUE_OVERVIEW_SENSORS:
                entities.append(
                    KickbaseCoordinatorSensor(
                        coordinator=lset.overview,
                        description=desc,
                        unique_id=f"{entry.entry_id}_{lid}_{desc.key}",
                        device_info=league_device,
                    )
                )

        if lset.squad_lineup is not None and runtime.is_module_enabled(MODULE_SQUAD_LINEUP):
            for desc in SQUAD_LINEUP_SENSORS:
                entities.append(
                    KickbaseCoordinatorSensor(
                        coordinator=lset.squad_lineup,
                        description=desc,
                        unique_id=f"{entry.entry_id}_{lid}_{desc.key}",
                        device_info=league_device,
                    )
                )
            if enable_player_entities and lset.squad_lineup.data:
                for player in lset.squad_lineup.data.get("squad") or []:
                    pid = player.get("id")
                    if pid:
                        entities.append(
                            KickbasePlayerSensor(
                                coordinator=lset.squad_lineup,
                                entry_id=entry.entry_id,
                                league_id=lid,
                                player_id=pid,
                                initial_name=player.get("full_name") or player.get("name") or pid,
                                device_info=league_device,
                            )
                        )

        if lset.market_transfers is not None and runtime.is_module_enabled(MODULE_MARKET_TRANSFERS):
            for desc in MARKET_TRANSFERS_SENSORS:
                entities.append(
                    KickbaseCoordinatorSensor(
                        coordinator=lset.market_transfers,
                        description=desc,
                        unique_id=f"{entry.entry_id}_{lid}_{desc.key}",
                        device_info=league_device,
                    )
                )

        if lset.live_matchday is not None and runtime.is_module_enabled(MODULE_LIVE_MATCHDAY):
            for desc in LIVE_MATCHDAY_SENSORS:
                entities.append(
                    KickbaseCoordinatorSensor(
                        coordinator=lset.live_matchday,
                        description=desc,
                        unique_id=f"{entry.entry_id}_{lid}_{desc.key}",
                        device_info=league_device,
                    )
                )

        if lset.feed_achievements is not None and runtime.is_module_enabled(MODULE_FEED_ACHIEVEMENTS):
            for desc in FEED_ACHIEVEMENTS_SENSORS:
                entities.append(
                    KickbaseCoordinatorSensor(
                        coordinator=lset.feed_achievements,
                        description=desc,
                        unique_id=f"{entry.entry_id}_{lid}_{desc.key}",
                        device_info=league_device,
                    )
                )

    async_add_entities(entities)


class KickbaseCoordinatorSensor(CoordinatorEntity, SensorEntity):
    """Generic sensor backed by a Kickbase DataUpdateCoordinator."""

    entity_description: KickbaseSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        *,
        coordinator: Any,
        description: KickbaseSensorDescription,
        unique_id: str,
        device_info: Any,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = unique_id
        self._attr_device_info = device_info

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        val = self.entity_description.value_fn(data)
        if isinstance(val, datetime):
            return val
        return val

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        if not isinstance(data, dict) or self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(data)


class KickbasePlayerSensor(CoordinatorEntity, SensorEntity):
    """Optional per-squad-player sensor exposing market value & full stats."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:account-star"

    def __init__(
        self,
        *,
        coordinator: Any,
        entry_id: str,
        league_id: str,
        player_id: str,
        initial_name: str,
        device_info: Any,
    ) -> None:
        super().__init__(coordinator)
        self._player_id = player_id
        self._attr_unique_id = f"{entry_id}_{league_id}_player_{player_id}"
        self._attr_name = f"Spieler {initial_name}"
        self._attr_device_info = device_info

    def _find_player(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        for p in data.get("squad") or []:
            if p.get("id") == self._player_id:
                return p
        return None

    @property
    def available(self) -> bool:
        return super().available and self._find_player() is not None

    @property
    def native_value(self) -> Any:
        player = self._find_player()
        return player.get("market_value") if player else None

    @property
    def entity_picture(self) -> str | None:
        player = self._find_player()
        return player.get("image") if player else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        player = self._find_player()
        if not player:
            return None
        return {
            "player_id": player.get("id"),
            "name": player.get("full_name") or player.get("name"),
            "position": (player.get("position") or {}).get("name_de"),
            "status": (player.get("status") or {}).get("label_de"),
            "market_value_24h_change": player.get("market_value_24h_change"),
            "market_value_since_buy": player.get("market_value_since_buy"),
            "market_value_trend": player.get("market_value_trend"),
            "total_points": player.get("total_points"),
            "average_points": player.get("average_points"),
            "in_starting_eleven": player.get("in_starting_eleven"),
        }
