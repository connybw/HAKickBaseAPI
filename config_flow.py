"""Config flow and options flow for the Kickbase integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import KickbaseApi, KickbaseAuthError, KickbaseError
from .const import (
    ALL_MODULES,
    CONF_DEFAULT_COMPETITION_ID,
    CONF_EMAIL,
    CONF_ENABLE_PLAYER_ENTITIES,
    CONF_ENABLE_SIDEBAR_PANEL,
    CONF_LEAGUES,
    CONF_MARKET_VALUE_TIMEFRAME,
    CONF_MODULES,
    CONF_PASSWORD,
    CONF_PRIMARY_LEAGUE,
    CONF_SCAN_INTERVALS,
    DEFAULT_COMPETITION_ID,
    DEFAULT_ENABLED_MODULES,
    DEFAULT_INTERVALS,
    DEFAULT_MARKET_VALUE_TIMEFRAME,
    DOMAIN,
    MAX_POLL_INTERVAL_SECONDS,
    MIN_POLL_INTERVAL_SECONDS,
    MODULE_CHALLENGES,
    MODULE_FEED_ACHIEVEMENTS,
    MODULE_LEAGUE_OVERVIEW,
    MODULE_LIVE_MATCHDAY,
    MODULE_MARKET_TRANSFERS,
    MODULE_NEWS_PREDICTIONS,
    MODULE_SQUAD_LINEUP,
)

_LOGGER = logging.getLogger(__name__)

MODULE_LABELS_DE: dict[str, str] = {
    MODULE_LEAGUE_OVERVIEW: "Liga, Tabelle, Budget & Battles",
    MODULE_SQUAD_LINEUP: "Kader & Aufstellung (Spielfeld)",
    MODULE_MARKET_TRANSFERS: "Transfermarkt & Scout-Liste",
    MODULE_LIVE_MATCHDAY: "Live-Spieltag, Bundesliga & Events",
    MODULE_FEED_ACHIEVEMENTS: "Aktivitäten-Feed & Erfolge",
    MODULE_NEWS_PREDICTIONS: "News & Voraussichtliche Aufstellungen",
    MODULE_CHALLENGES: "Kickbase Challenges & Division Lobby",
}


class KickbaseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kickbase."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str = ""
        self._password: str = ""
        self._user_id: str = ""
        self._user_name: str = ""
        self._available_leagues: list[dict[str, str]] = []
        self._selected_leagues: list[str] = []
        self._reauth_entry: ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return KickbaseOptionsFlow()

    async def _async_validate_credentials(
        self, email: str, password: str
    ) -> tuple[str, str, list[dict[str, str]]]:
        """Validate Kickbase credentials and return user_id, name, and leagues."""
        session = async_get_clientsession(self.hass)
        api = KickbaseApi(session, email, password)
        login_data = await api.async_login(force=True)
        user_obj = login_data.get("u", {})
        user_id = str(user_obj.get("id") or user_obj.get("i") or email.lower())
        user_name = user_obj.get("name") or email

        leagues: list[dict[str, str]] = []
        seen: set[str] = set()
        try:
            sel = await api.leagues.get_selection()
            for item in (sel.get("it") or []) if isinstance(sel, dict) else []:
                lid = str(item.get("i", ""))
                if lid and lid not in seen:
                    seen.add(lid)
                    leagues.append(
                        {"id": lid, "name": item.get("n") or f"Liga {lid}"}
                    )
        except KickbaseError:
            pass

        for item in login_data.get("srvl") or []:
            lid = str(item.get("id") or item.get("i") or "")
            if lid and lid not in seen:
                seen.add(lid)
                leagues.append(
                    {"id": lid, "name": item.get("name") or item.get("n") or f"Liga {lid}"}
                )

        return user_id, user_name, leagues

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Authenticate with Kickbase email & password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]
            try:
                user_id, user_name, leagues = await self._async_validate_credentials(
                    email, password
                )
            except KickbaseAuthError:
                errors["base"] = "invalid_auth"
            except KickbaseError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during Kickbase login")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_id)
                self._abort_if_unique_id_configured()
                self._email = email
                self._password = password
                self._user_id = user_id
                self._user_name = user_name
                self._available_leagues = leagues
                if leagues:
                    return await self.async_step_leagues()
                return await self.async_step_modules()

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="email")
                ),
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(
                        type=TextSelectorType.PASSWORD, autocomplete="current-password"
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_leagues(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: Select leagues to monitor."""
        errors: dict[str, str] = {}
        league_options = [
            SelectOptionDict(value=lg["id"], label=f"{lg['name']} ({lg['id']})")
            for lg in self._available_leagues
        ]
        all_ids = [lg["id"] for lg in self._available_leagues]

        if user_input is not None:
            selected = user_input.get(CONF_LEAGUES) or []
            if not selected:
                errors[CONF_LEAGUES] = "select_at_least_one_league"
            else:
                self._selected_leagues = selected
                return await self.async_step_modules()

        schema = vol.Schema(
            {
                vol.Required(CONF_LEAGUES, default=all_ids): SelectSelector(
                    SelectSelectorConfig(
                        options=league_options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="leagues", data_schema=schema, errors=errors)

    async def async_step_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: Choose modular data packages, UI panel, and entity granularity."""
        selected_league_options = [
            SelectOptionDict(value=lg["id"], label=lg["name"])
            for lg in self._available_leagues
            if lg["id"] in self._selected_leagues
        ]
        default_primary = (
            self._selected_leagues[0] if self._selected_leagues else ""
        )

        module_options = [
            SelectOptionDict(value=m, label=MODULE_LABELS_DE.get(m, m))
            for m in ALL_MODULES
        ]

        if user_input is not None:
            options_payload = {
                CONF_LEAGUES: self._selected_leagues,
                CONF_PRIMARY_LEAGUE: user_input.get(CONF_PRIMARY_LEAGUE, default_primary),
                CONF_MODULES: user_input.get(CONF_MODULES, DEFAULT_ENABLED_MODULES),
                CONF_ENABLE_SIDEBAR_PANEL: user_input.get(CONF_ENABLE_SIDEBAR_PANEL, True),
                CONF_ENABLE_PLAYER_ENTITIES: user_input.get(CONF_ENABLE_PLAYER_ENTITIES, False),
                CONF_MARKET_VALUE_TIMEFRAME: int(
                    user_input.get(CONF_MARKET_VALUE_TIMEFRAME, DEFAULT_MARKET_VALUE_TIMEFRAME)
                ),
                CONF_DEFAULT_COMPETITION_ID: DEFAULT_COMPETITION_ID,
                CONF_SCAN_INTERVALS: dict(DEFAULT_INTERVALS),
            }
            return self.async_create_entry(
                title=f"Kickbase ({self._user_name})",
                data={
                    CONF_EMAIL: self._email,
                    CONF_PASSWORD: self._password,
                },
                options=options_payload,
            )

        schema_dict: dict[Any, Any] = {}
        if selected_league_options:
            schema_dict[
                vol.Required(CONF_PRIMARY_LEAGUE, default=default_primary)
            ] = SelectSelector(
                SelectSelectorConfig(
                    options=selected_league_options,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        schema_dict[
            vol.Required(CONF_MODULES, default=DEFAULT_ENABLED_MODULES)
        ] = SelectSelector(
            SelectSelectorConfig(
                options=module_options,
                multiple=True,
                mode=SelectSelectorMode.LIST,
            )
        )
        schema_dict[vol.Required(CONF_ENABLE_SIDEBAR_PANEL, default=True)] = BooleanSelector()
        schema_dict[vol.Required(CONF_ENABLE_PLAYER_ENTITIES, default=False)] = BooleanSelector()
        schema_dict[
            vol.Required(
                CONF_MARKET_VALUE_TIMEFRAME,
                default=str(DEFAULT_MARKET_VALUE_TIMEFRAME),
            )
        ] = SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value="30", label="30 Tage"),
                    SelectOptionDict(value="92", label="92 Tage (3 Monate)"),
                    SelectOptionDict(value="180", label="180 Tage (6 Monate)"),
                    SelectOptionDict(value="365", label="365 Tage (1 Jahr)"),
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        )

        return self.async_show_form(
            step_id="modules",
            data_schema=vol.Schema(schema_dict),
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when Kickbase credentials fail."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        self._email = entry_data.get(CONF_EMAIL, "")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm updated credentials during reauth."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]
            try:
                await self._async_validate_credentials(email, password)
            except KickbaseAuthError:
                errors["base"] = "invalid_auth"
            except KickbaseError:
                errors["base"] = "cannot_connect"
            else:
                if self._reauth_entry:
                    return self.async_update_reload_and_abort(
                        self._reauth_entry,
                        data={CONF_EMAIL: email, CONF_PASSWORD: password},
                    )
                return self.async_abort(reason="reauth_successful")

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL, default=self._email): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL)
                ),
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=schema, errors=errors
        )


class KickbaseOptionsFlow(OptionsFlow):
    """Options flow allowing modular toggling & interval tuning after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage modular features, leagues, and polling intervals."""
        opts = dict(self.config_entry.options)
        runtime = getattr(self.config_entry, "runtime_data", None)

        discovered_leagues: list[dict[str, str]] = []
        if runtime and getattr(runtime, "account", None) and runtime.account.data:
            for lid, linfo in (runtime.account.data.get("leagues") or {}).items():
                discovered_leagues.append(
                    {"id": lid, "name": linfo.get("name", f"Liga {lid}")}
                )
        if not discovered_leagues:
            for lid in opts.get(CONF_LEAGUES, []):
                discovered_leagues.append({"id": lid, "name": f"Liga {lid}"})

        if user_input is not None:
            intervals = dict(opts.get(CONF_SCAN_INTERVALS) or DEFAULT_INTERVALS)
            for mod in ALL_MODULES:
                key = f"interval_{mod}"
                if key in user_input:
                    intervals[mod] = int(user_input[key])

            selected_leagues = user_input.get(CONF_LEAGUES, opts.get(CONF_LEAGUES, []))
            primary = user_input.get(CONF_PRIMARY_LEAGUE, opts.get(CONF_PRIMARY_LEAGUE, ""))
            if selected_leagues and primary not in selected_leagues:
                primary = selected_leagues[0]

            new_options = {
                CONF_LEAGUES: selected_leagues,
                CONF_PRIMARY_LEAGUE: primary,
                CONF_MODULES: user_input.get(CONF_MODULES, DEFAULT_ENABLED_MODULES),
                CONF_ENABLE_SIDEBAR_PANEL: user_input.get(CONF_ENABLE_SIDEBAR_PANEL, True),
                CONF_ENABLE_PLAYER_ENTITIES: user_input.get(CONF_ENABLE_PLAYER_ENTITIES, False),
                CONF_MARKET_VALUE_TIMEFRAME: int(
                    user_input.get(
                        CONF_MARKET_VALUE_TIMEFRAME, DEFAULT_MARKET_VALUE_TIMEFRAME
                    )
                ),
                CONF_DEFAULT_COMPETITION_ID: opts.get(
                    CONF_DEFAULT_COMPETITION_ID, DEFAULT_COMPETITION_ID
                ),
                CONF_SCAN_INTERVALS: intervals,
            }
            return self.async_create_entry(title="", data=new_options)

        league_options = [
            SelectOptionDict(value=lg["id"], label=f"{lg['name']} ({lg['id']})")
            for lg in discovered_leagues
        ]
        module_options = [
            SelectOptionDict(value=m, label=MODULE_LABELS_DE.get(m, m))
            for m in ALL_MODULES
        ]
        current_intervals = opts.get(CONF_SCAN_INTERVALS) or DEFAULT_INTERVALS
        interval_selector = NumberSelector(
            NumberSelectorConfig(
                min=MIN_POLL_INTERVAL_SECONDS,
                max=MAX_POLL_INTERVAL_SECONDS,
                step=30,
                unit_of_measurement="s",
                mode=NumberSelectorMode.BOX,
            )
        )

        schema_dict: dict[Any, Any] = {}
        if league_options:
            schema_dict[
                vol.Required(
                    CONF_LEAGUES,
                    default=opts.get(CONF_LEAGUES, [lg["id"] for lg in discovered_leagues]),
                )
            ] = SelectSelector(
                SelectSelectorConfig(
                    options=league_options,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )
            schema_dict[
                vol.Required(
                    CONF_PRIMARY_LEAGUE,
                    default=opts.get(CONF_PRIMARY_LEAGUE, discovered_leagues[0]["id"]),
                )
            ] = SelectSelector(
                SelectSelectorConfig(
                    options=league_options,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )

        schema_dict[
            vol.Required(CONF_MODULES, default=opts.get(CONF_MODULES, DEFAULT_ENABLED_MODULES))
        ] = SelectSelector(
            SelectSelectorConfig(
                options=module_options,
                multiple=True,
                mode=SelectSelectorMode.LIST,
            )
        )
        schema_dict[
            vol.Required(
                CONF_ENABLE_SIDEBAR_PANEL,
                default=opts.get(CONF_ENABLE_SIDEBAR_PANEL, True),
            )
        ] = BooleanSelector()
        schema_dict[
            vol.Required(
                CONF_ENABLE_PLAYER_ENTITIES,
                default=opts.get(CONF_ENABLE_PLAYER_ENTITIES, False),
            )
        ] = BooleanSelector()
        schema_dict[
            vol.Required(
                CONF_MARKET_VALUE_TIMEFRAME,
                default=str(opts.get(CONF_MARKET_VALUE_TIMEFRAME, DEFAULT_MARKET_VALUE_TIMEFRAME)),
            )
        ] = SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value="30", label="30 Tage"),
                    SelectOptionDict(value="92", label="92 Tage (3 Monate)"),
                    SelectOptionDict(value="180", label="180 Tage (6 Monate)"),
                    SelectOptionDict(value="365", label="365 Tage (1 Jahr)"),
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        )

        for mod in ALL_MODULES:
            schema_dict[
                vol.Required(
                    f"interval_{mod}",
                    default=int(current_intervals.get(mod, DEFAULT_INTERVALS[mod])),
                )
            ] = interval_selector

        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema_dict))
