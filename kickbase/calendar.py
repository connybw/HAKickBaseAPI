"""Calendar platform for Kickbase matchdays and lineup deadlines."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api.models import parse_iso_datetime
from .entity import build_league_device_info

if TYPE_CHECKING:
    from . import KickbaseConfigEntry
    from .coordinators import KickbaseRuntimeData, LeagueCoordinatorSet


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KickbaseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kickbase calendar entities per league."""
    runtime: KickbaseRuntimeData = entry.runtime_data
    account_data = runtime.account.data or {}
    entities: list[CalendarEntity] = []

    for lid, lset in runtime.leagues.items():
        if lset.live_matchday is None and lset.squad_lineup is None:
            continue
        league_device = build_league_device_info(
            lid,
            lset.league_name,
            (account_data.get("leagues") or {}).get(lid, {}).get("competition_name"),
        )
        entities.append(
            KickbaseLeagueCalendar(
                entry_id=entry.entry_id,
                league_set=lset,
                device_info=league_device,
            )
        )

    async_add_entities(entities)


class KickbaseLeagueCalendar(CoordinatorEntity, CalendarEntity):
    """Calendar combining lineup lock deadlines and competition fixtures."""

    _attr_has_entity_name = True
    _attr_name = "Spielplan & Deadlines"
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        *,
        entry_id: str,
        league_set: LeagueCoordinatorSet,
        device_info: Any,
    ) -> None:
        primary_coord = league_set.live_matchday or league_set.squad_lineup
        super().__init__(primary_coord)
        self._lset = league_set
        self._attr_unique_id = f"{entry_id}_{league_set.league_id}_calendar"
        self._attr_device_info = device_info

    def _build_events(self) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []

        # 1. Lineup lock deadline
        if self._lset.squad_lineup and isinstance(self._lset.squad_lineup.data, dict):
            lineup = self._lset.squad_lineup.data.get("lineup") or {}
            lock_dt = parse_iso_datetime(lineup.get("lock_at"))
            if lock_dt is not None:
                md = lineup.get("matchday") or "?"
                events.append(
                    CalendarEvent(
                        start=lock_dt - timedelta(minutes=15),
                        end=lock_dt,
                        summary=f"Kickbase Aufstellungs-Deadline (Spieltag {md})",
                        description=(
                            f"Formation: {lineup.get('formation', '?')} | "
                            f"Spieler: {lineup.get('player_count', 0)}/11"
                        ),
                    )
                )

        # 2. Matchday fixtures
        if self._lset.live_matchday and isinstance(self._lset.live_matchday.data, dict):
            for md_block in self._lset.live_matchday.data.get("all_matchdays") or []:
                day_num = md_block.get("day")
                for match in md_block.get("matches") or []:
                    start_dt = parse_iso_datetime(match.get("date"))
                    if start_dt is None:
                        continue
                    t1 = match.get("team1_name") or match.get("team1_short")
                    t2 = match.get("team2_name") or match.get("team2_short")
                    score = ""
                    if match.get("status") in ("live", "finished", "half_time"):
                        score = f" ({match.get('team1_goals', 0)}:{match.get('team2_goals', 0)})"
                    events.append(
                        CalendarEvent(
                            start=start_dt,
                            end=start_dt + timedelta(minutes=110),
                            summary=f"[ST {day_num}] {t1} vs. {t2}{score}",
                            description=f"Status: {match.get('status')}",
                        )
                    )

        events.sort(key=lambda e: e.start)
        return events

    @property
    def event(self) -> CalendarEvent | None:
        now = datetime.now().astimezone()
        for ev in self._build_events():
            if ev.end >= now:
                return ev
        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        return [
            ev
            for ev in self._build_events()
            if ev.end >= start_date and ev.start <= end_date
        ]
