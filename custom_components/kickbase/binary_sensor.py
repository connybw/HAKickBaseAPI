"""Binary sensor platform for Kickbase automation triggers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    MODULE_LEAGUE_OVERVIEW,
    MODULE_LIVE_MATCHDAY,
    MODULE_MARKET_TRANSFERS,
    MODULE_SQUAD_LINEUP,
)
from .entity import build_league_device_info

if TYPE_CHECKING:
    from . import KickbaseConfigEntry
    from .coordinators import KickbaseRuntimeData


@dataclass(frozen=True, kw_only=True)
class KickbaseBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a Kickbase binary sensor."""

    is_on_fn: Callable[[dict[str, Any]], bool]


OVERVIEW_BINARY_SENSORS: tuple[KickbaseBinarySensorDescription, ...] = (
    KickbaseBinarySensorDescription(
        key="budget_negative",
        name="Budget im Minus",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:cash-remove",
        is_on_fn=lambda d: bool((d.get("me") or {}).get("is_negative_budget", False)),
    ),
)

SQUAD_BINARY_SENSORS: tuple[KickbaseBinarySensorDescription, ...] = (
    KickbaseBinarySensorDescription(
        key="lineup_problem",
        name="Aufstellung unvollständig/Problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:alert-circle-outline",
        is_on_fn=lambda d: (
            ((d.get("lineup") or {}).get("player_count", 0) < 11)
            or ((d.get("lineup") or {}).get("issue_count", 0) > 0)
        ),
    ),
    KickbaseBinarySensorDescription(
        key="squad_value_rising",
        name="Kader-Marktwert steigt",
        icon="mdi:trending-up",
        is_on_fn=lambda d: ((d.get("summary") or {}).get("total_24h_change", 0) > 0),
    ),
)

MARKET_BINARY_SENSORS: tuple[KickbaseBinarySensorDescription, ...] = (
    KickbaseBinarySensorDescription(
        key="scouted_on_market",
        name="Scout-Spieler auf Transfermarkt",
        icon="mdi:binoculars",
        is_on_fn=lambda d: (d.get("scouted_on_market_count", 0) > 0),
    ),
)

LIVE_BINARY_SENSORS: tuple[KickbaseBinarySensorDescription, ...] = (
    KickbaseBinarySensorDescription(
        key="matchday_live",
        name="Spieltag Live",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:soccer",
        is_on_fn=lambda d: bool(d.get("is_live", False)),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KickbaseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kickbase binary sensors."""
    runtime: KickbaseRuntimeData = entry.runtime_data
    account_data = runtime.account.data or {}
    entities: list[BinarySensorEntity] = []

    for lid, lset in runtime.leagues.items():
        league_device = build_league_device_info(
            lid,
            lset.league_name,
            (account_data.get("leagues") or {}).get(lid, {}).get("competition_name"),
        )
        if lset.overview is not None and runtime.is_module_enabled(MODULE_LEAGUE_OVERVIEW):
            for desc in OVERVIEW_BINARY_SENSORS:
                entities.append(
                    KickbaseBinarySensor(
                        coordinator=lset.overview,
                        description=desc,
                        unique_id=f"{entry.entry_id}_{lid}_{desc.key}",
                        device_info=league_device,
                    )
                )
        if lset.squad_lineup is not None and runtime.is_module_enabled(MODULE_SQUAD_LINEUP):
            for desc in SQUAD_BINARY_SENSORS:
                entities.append(
                    KickbaseBinarySensor(
                        coordinator=lset.squad_lineup,
                        description=desc,
                        unique_id=f"{entry.entry_id}_{lid}_{desc.key}",
                        device_info=league_device,
                    )
                )
        if lset.market_transfers is not None and runtime.is_module_enabled(MODULE_MARKET_TRANSFERS):
            for desc in MARKET_BINARY_SENSORS:
                entities.append(
                    KickbaseBinarySensor(
                        coordinator=lset.market_transfers,
                        description=desc,
                        unique_id=f"{entry.entry_id}_{lid}_{desc.key}",
                        device_info=league_device,
                    )
                )
        if lset.live_matchday is not None and runtime.is_module_enabled(MODULE_LIVE_MATCHDAY):
            for desc in LIVE_BINARY_SENSORS:
                entities.append(
                    KickbaseBinarySensor(
                        coordinator=lset.live_matchday,
                        description=desc,
                        unique_id=f"{entry.entry_id}_{lid}_{desc.key}",
                        device_info=league_device,
                    )
                )

    async_add_entities(entities)


class KickbaseBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Kickbase binary sensor."""

    entity_description: KickbaseBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        *,
        coordinator: Any,
        description: KickbaseBinarySensorDescription,
        unique_id: str,
        device_info: Any,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = unique_id
        self._attr_device_info = device_info

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        return self.entity_description.is_on_fn(data)
