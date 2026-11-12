"""Shared entity & device helpers for Kickbase."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN, INTEGRATION_NAME


def build_account_device_info(user_id: str, user_name: str) -> DeviceInfo:
    """Device info for the global Kickbase account."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"account_{user_id}")},
        name=f"{INTEGRATION_NAME} ({user_name})",
        manufacturer="Kickbase",
        model="Account & Global Modules",
        entry_type=DeviceEntryType.SERVICE,
    )


def build_league_device_info(
    league_id: str, league_name: str, competition_name: str | None = None
) -> DeviceInfo:
    """Device info for an individual Kickbase league."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"league_{league_id}")},
        name=f"Kickbase {league_name}",
        manufacturer="Kickbase",
        model=competition_name or "Bundesliga Liga",
        entry_type=DeviceEntryType.SERVICE,
    )


def build_challenges_device_info(user_id: str) -> DeviceInfo:
    """Device info for Kickbase Challenges & Lobby."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"challenges_{user_id}")},
        name="Kickbase Challenges",
        manufacturer="Kickbase",
        model="Challenge Lobby",
        entry_type=DeviceEntryType.SERVICE,
    )
