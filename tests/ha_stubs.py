"""Lightweight Home Assistant / aiohttp / voluptuous stubs for local unit testing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
import socket
import sys
import tempfile
import time
import types
from typing import Any


class _NoSocketSelector:
    """Minimal selector replacement for socket-less unit test environments."""

    def select(self, timeout: float | None = None) -> list[Any]:
        if timeout is not None and timeout > 0:
            time.sleep(min(timeout, 0.01))
        return []

    def close(self) -> None:
        return None


class _NoSocketEventLoop(asyncio.BaseEventLoop):
    """Stdlib BaseEventLoop without socketpair self-pipe (for restricted sandboxes)."""

    def __init__(self) -> None:
        super().__init__()
        self._selector = _NoSocketSelector()

    def _write_to_self(self) -> None:
        return None

    def _process_events(self, event_list: list[Any]) -> None:
        return None

    def _close_self_pipe(self) -> None:
        return None

    def close(self) -> None:
        super().close()
        self._selector.close()


class _NoSocketEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    def new_event_loop(self) -> asyncio.AbstractEventLoop:
        return _NoSocketEventLoop()


def _ensure_working_asyncio_loop() -> None:
    """Use stock asyncio when loopback sockets work; otherwise fall back to _NoSocketEventLoop."""
    if isinstance(asyncio.get_event_loop_policy(), _NoSocketEventLoopPolicy):
        return
    srv = None
    cli = None
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.settimeout(0.05)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        cli = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cli.settimeout(0.05)
        cli.connect(("127.0.0.1", port))
        acc, _ = srv.accept()
        acc.close()
    except OSError:
        asyncio.set_event_loop_policy(_NoSocketEventLoopPolicy())
    finally:
        for s in (cli, srv):
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass


class FakeResponse:
    """Async context manager simulating an aiohttp.ClientResponse."""

    def __init__(
        self,
        status: int = 200,
        json_data: Any = None,
        text_data: str | None = None,
        bytes_data: bytes | None = None,
        headers: dict[str, str] | None = None,
        content_length: int | None = None,
    ) -> None:
        self.status = status
        self._json_data = json_data
        self._text_data = text_data
        self._bytes_data = bytes_data
        self.headers = headers if headers is not None else {"Content-Type": "application/json"}
        self.content_length = content_length

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def json(self, content_type: Any = None) -> Any:
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data

    async def text(self) -> str:
        if self._text_data is not None:
            return self._text_data
        return str(self._json_data or "")

    async def read(self) -> bytes:
        if self._bytes_data is not None:
            return self._bytes_data
        if self._text_data is not None:
            return self._text_data.encode("utf-8")
        return b""


class FakeClientSession:
    """Recorded aiohttp.ClientSession mock driven by route handlers."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._routes: dict[tuple[str, str], list[Any]] = {}
        self.default_handler: Any = None

    def add_route(self, method: str, path: str, response: Any) -> None:
        key = (method.upper(), path)
        self._routes.setdefault(key, []).append(response)

    def set_route(self, method: str, path: str, response: Any) -> None:
        key = (method.upper(), path)
        self._routes[key] = [response]

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: Any = None,
    ) -> Any:
        self.requests.append(
            {
                "method": method.upper(),
                "url": url,
                "params": params,
                "json": json,
                "headers": dict(headers or {}),
            }
        )
        # Match path suffix regardless of base URL
        matched_resp = None
        for (m, p), queue in self._routes.items():
            if m == method.upper() and url.endswith(p) and queue:
                item = queue.pop(0) if len(queue) > 1 else queue[0]
                matched_resp = item() if callable(item) else item
                break
        if matched_resp is not None:
            if isinstance(matched_resp, Exception):
                raise matched_resp
            return matched_resp
        if self.default_handler is not None:
            return self.default_handler(method, url, params=params, json=json, headers=headers)
        return FakeResponse(status=404, text_data="Not mocked")


def install_stubs() -> None:
    """Install minimal stubs only if packages are not installed in Python env."""
    _ensure_working_asyncio_loop()
    if "aiohttp" not in sys.modules:
        aiohttp = types.ModuleType("aiohttp")

        class ClientError(Exception):
            pass

        class ContentTypeError(ClientError):
            pass

        class ClientTimeout:
            def __init__(self, total: int = 20) -> None:
                self.total = total

        class ClientSession:
            async def request(self, *args: Any, **kwargs: Any) -> Any:
                raise NotImplementedError

        aiohttp.ClientError = ClientError
        aiohttp.ContentTypeError = ContentTypeError
        aiohttp.ClientTimeout = ClientTimeout
        aiohttp.ClientSession = ClientSession
        sys.modules["aiohttp"] = aiohttp

    if "voluptuous" not in sys.modules:
        vol = types.ModuleType("voluptuous")

        class Schema:
            def __init__(self, schema: Any) -> None:
                self.schema = schema

            def __call__(self, data: Any) -> Any:
                return data

        def _marker(key: Any, default: Any = None) -> Any:
            return key

        vol.Schema = Schema
        vol.Required = _marker
        vol.Optional = _marker
        vol.In = lambda vals: vals
        vol.Coerce = lambda tp: tp
        sys.modules["voluptuous"] = vol

    if "homeassistant" in sys.modules:
        return

    ha = types.ModuleType("homeassistant")
    sys.modules["homeassistant"] = ha

    # exceptions
    exc = types.ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        pass

    class ConfigEntryAuthFailed(HomeAssistantError):
        pass

    exc.HomeAssistantError = HomeAssistantError
    exc.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    sys.modules["homeassistant.exceptions"] = exc

    # const
    const = types.ModuleType("homeassistant.const")

    class Platform:
        SENSOR = "sensor"
        BINARY_SENSOR = "binary_sensor"
        CALENDAR = "calendar"
        IMAGE = "image"

    const.Platform = Platform
    sys.modules["homeassistant.const"] = const

    # core
    core = types.ModuleType("homeassistant.core")

    class EventBus:
        def __init__(self) -> None:
            self.events: list[tuple[str, dict[str, Any]]] = []

        def async_fire(self, event_type: str, event_data: dict[str, Any] | None = None) -> None:
            self.events.append((event_type, event_data or {}))

    class ServiceRegistry:
        def __init__(self) -> None:
            self.services: dict[tuple[str, str], Any] = {}

        def async_register(
            self,
            domain: str,
            service: str,
            handler: Any,
            schema: Any = None,
            supports_response: Any = None,
        ) -> None:
            self.services[(domain, service)] = handler

    class SupportsResponse:
        NONE = "none"
        OPTIONAL = "optional"
        ONLY = "only"

    class HttpComponent:
        def __init__(self) -> None:
            self.static_paths: list[Any] = []

        async def async_register_static_paths(self, configs: list[Any]) -> None:
            self.static_paths.extend(configs)

    class ConfigEntriesManager:
        def __init__(self) -> None:
            self._entries: list[Any] = []
            self.forwarded_platforms: list[tuple[str, list[Any]]] = []
            self.unloaded_platforms: list[tuple[str, list[Any]]] = []
            self.reloaded_ids: list[str] = []

        def add_entry(self, entry: Any) -> None:
            self._entries.append(entry)

        def async_entries(self, domain: str | None = None) -> list[Any]:
            return list(self._entries)

        def async_get_entry(self, entry_id: str) -> Any:
            return next((e for e in self._entries if e.entry_id == entry_id), None)

        async def async_forward_entry_setups(self, entry: Any, platforms: list[Any]) -> None:
            self.forwarded_platforms.append((entry.entry_id, list(platforms)))

        async def async_unload_platforms(self, entry: Any, platforms: list[Any]) -> bool:
            self.unloaded_platforms.append((entry.entry_id, list(platforms)))
            return True

        async def async_reload(self, entry_id: str) -> None:
            self.reloaded_ids.append(entry_id)

    class ConfigDirectory:
        def __init__(self, base_dir: Path | None = None) -> None:
            self._base = base_dir or Path(tempfile.mkdtemp(prefix="kb_ha_cfg_"))

        def path(self, *parts: str) -> str:
            return str(self._base.joinpath(*parts))

    class HomeAssistant:
        def __init__(self, config_dir: Path | None = None) -> None:
            self.data: dict[str, Any] = {}
            self.bus = EventBus()
            self.services = ServiceRegistry()
            self.http = HttpComponent()
            self.config_entries = ConfigEntriesManager()
            self.config = ConfigDirectory(config_dir)

        async def async_add_executor_job(self, target: Any, *args: Any) -> Any:
            return target(*args)

    class ServiceCall:
        def __init__(self, data: dict[str, Any] | None = None) -> None:
            self.data = data or {}

    def callback(fn: Any) -> Any:
        return fn

    core.HomeAssistant = HomeAssistant
    core.ServiceCall = ServiceCall
    core.SupportsResponse = SupportsResponse
    core.callback = callback
    sys.modules["homeassistant.core"] = core

    # config_entries
    ce = types.ModuleType("homeassistant.config_entries")

    class ConfigEntry:
        def __init__(
            self,
            *,
            entry_id: str = "entry_1",
            title: str = "Kickbase",
            data: dict[str, Any] | None = None,
            options: dict[str, Any] | None = None,
        ) -> None:
            self.entry_id = entry_id
            self.title = title
            self.data = data or {}
            self.options = options or {}
            self.runtime_data: Any = None
            self._unload_cbs: list[Any] = []
            self._update_listeners: list[Any] = []

        def __class_getitem__(cls, item: Any) -> Any:
            return cls

        def async_on_unload(self, cb: Any) -> None:
            self._unload_cbs.append(cb)

        def add_update_listener(self, listener: Any) -> Any:
            self._update_listeners.append(listener)
            return lambda: None

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs: Any) -> None:
            pass

        hass: Any = None
        context: dict[str, Any] = {}
        unique_id: str | None = None

        async def async_set_unique_id(self, unique_id: str) -> None:
            self.unique_id = unique_id

        def _abort_if_unique_id_configured(self) -> None:
            pass

        def async_show_form(
            self, *, step_id: str, data_schema: Any = None, errors: dict[str, str] | None = None
        ) -> dict[str, Any]:
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
            }

        def async_create_entry(
            self, *, title: str = "", data: dict[str, Any] | None = None, options: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            return {
                "type": "create_entry",
                "title": title,
                "data": data or {},
                "options": options or {},
            }

        def async_update_reload_and_abort(
            self, entry: ConfigEntry, *, data: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            if data is not None:
                entry.data = data
            return {"type": "abort", "reason": "reauth_successful"}

        def async_abort(self, *, reason: str) -> dict[str, Any]:
            return {"type": "abort", "reason": reason}

    class OptionsFlow:
        config_entry: ConfigEntry

        def async_show_form(
            self, *, step_id: str, data_schema: Any = None, errors: dict[str, str] | None = None
        ) -> dict[str, Any]:
            return {"type": "form", "step_id": step_id, "data_schema": data_schema, "errors": errors or {}}

        def async_create_entry(self, *, title: str = "", data: dict[str, Any] | None = None) -> dict[str, Any]:
            return {"type": "create_entry", "title": title, "data": data or {}}

    ce.ConfigEntry = ConfigEntry
    ce.ConfigFlow = ConfigFlow
    ce.OptionsFlow = OptionsFlow
    ce.ConfigFlowResult = dict
    sys.modules["homeassistant.config_entries"] = ce

    # helpers
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    sys.modules["homeassistant.helpers"] = helpers

    ev_mod = types.ModuleType("homeassistant.helpers.event")
    ev_mod.async_track_time_change = lambda hass, action, **kw: (lambda: None)
    helpers.event = ev_mod
    sys.modules["homeassistant.helpers.event"] = ev_mod

    uc = types.ModuleType("homeassistant.helpers.update_coordinator")

    class UpdateFailed(Exception):
        pass

    class DataUpdateCoordinator:
        def __init__(
            self,
            hass: Any,
            logger: Any,
            *,
            config_entry: Any = None,
            name: str = "",
            update_interval: Any = None,
        ) -> None:
            self.hass = hass
            self.logger = logger
            self.config_entry = config_entry
            self.name = name
            self.update_interval = update_interval
            self.data: Any = None
            self.last_update_success = True

        def __class_getitem__(cls, item: Any) -> Any:
            return cls

        async def _async_setup(self) -> None:
            return None

        async def _async_update_data(self) -> Any:
            raise NotImplementedError

        async def async_config_entry_first_refresh(self) -> None:
            await self._async_setup()
            self.data = await self._async_update_data()

        async def async_request_refresh(self) -> None:
            self.data = await self._async_update_data()

    class CoordinatorEntity:
        def __init__(self, coordinator: Any) -> None:
            self.coordinator = coordinator

        @property
        def available(self) -> bool:
            return bool(self.coordinator.last_update_success)

        def _handle_coordinator_update(self) -> None:
            pass

    uc.DataUpdateCoordinator = DataUpdateCoordinator
    uc.UpdateFailed = UpdateFailed
    uc.CoordinatorEntity = CoordinatorEntity
    sys.modules["homeassistant.helpers.update_coordinator"] = uc

    dr = types.ModuleType("homeassistant.helpers.device_registry")

    class DeviceEntryType:
        SERVICE = "service"

    @dataclass
    class DeviceInfo:
        identifiers: Any = None
        name: str = ""
        manufacturer: str = ""
        model: str = ""
        entry_type: Any = None

    dr.DeviceEntryType = DeviceEntryType
    dr.DeviceInfo = DeviceInfo
    sys.modules["homeassistant.helpers.device_registry"] = dr

    ep = types.ModuleType("homeassistant.helpers.entity_platform")
    ep.AddEntitiesCallback = Any
    sys.modules["homeassistant.helpers.entity_platform"] = ep

    cv_mod = types.ModuleType("homeassistant.helpers.config_validation")
    cv_mod.string = str
    cv_mod.boolean = bool
    sys.modules["homeassistant.helpers.config_validation"] = cv_mod

    aio_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    aio_client._session = None
    aio_client.async_get_clientsession = lambda hass: getattr(hass, "_test_session", None) or aio_client._session
    sys.modules["homeassistant.helpers.aiohttp_client"] = aio_client

    sel = types.ModuleType("homeassistant.helpers.selector")
    for name in (
        "BooleanSelector",
        "NumberSelector",
        "NumberSelectorConfig",
        "SelectOptionDict",
        "SelectSelector",
        "SelectSelectorConfig",
        "TextSelector",
        "TextSelectorConfig",
    ):
        setattr(sel, name, lambda *a, **kw: {"args": a, "kwargs": kw})
    sel.NumberSelectorMode = type("NumberSelectorMode", (), {"BOX": "box", "SLIDER": "slider"})
    sel.SelectSelectorMode = type(
        "SelectSelectorMode", (), {"LIST": "list", "DROPDOWN": "dropdown"}
    )
    sel.TextSelectorType = type(
        "TextSelectorType", (), {"EMAIL": "email", "PASSWORD": "password", "TEXT": "text"}
    )
    sys.modules["homeassistant.helpers.selector"] = sel

    # components
    comp = types.ModuleType("homeassistant.components")
    sys.modules["homeassistant.components"] = comp

    for sub in ("http", "frontend", "websocket_api", "sensor", "binary_sensor", "calendar", "image"):
        mod = types.ModuleType(f"homeassistant.components.{sub}")
        sys.modules[f"homeassistant.components.{sub}"] = mod
        setattr(comp, sub, mod)

    http_mod = sys.modules["homeassistant.components.http"]
    http_mod.StaticPathConfig = lambda **kw: kw

    fe_mod = sys.modules["homeassistant.components.frontend"]
    fe_mod.extra_js_urls = []
    fe_mod.panels = {}

    def _add_extra_js_url(hass: Any, url: str) -> None:
        fe_mod.extra_js_urls.append(url)

    def _register_panel(hass: Any, **kw: Any) -> None:
        fe_mod.panels[kw["frontend_url_path"]] = kw

    def _remove_panel(hass: Any, url_path: str) -> None:
        fe_mod.panels.pop(url_path, None)

    fe_mod.add_extra_js_url = _add_extra_js_url
    fe_mod.async_register_built_in_panel = _register_panel
    fe_mod.async_remove_panel = _remove_panel

    ws = sys.modules["homeassistant.components.websocket_api"]
    ws.ActiveConnection = Any
    ws.registered_commands = {}

    def _register_ws_cmd(hass: Any, fn: Any) -> None:
        ws.registered_commands[fn.__name__] = fn

    ws.async_register_command = _register_ws_cmd
    ws.websocket_command = lambda schema: (lambda fn: fn)
    ws.async_response = lambda fn: fn

    sens = sys.modules["homeassistant.components.sensor"]
    sens.SensorDeviceClass = type(
        "SensorDeviceClass", (), {"MONETARY": "monetary", "TIMESTAMP": "timestamp"}
    )
    sens.SensorStateClass = type(
        "SensorStateClass", (), {"TOTAL": "total", "MEASUREMENT": "measurement"}
    )

    class SensorEntity:
        pass

    @dataclass(frozen=True, kw_only=True)
    class SensorEntityDescription:
        key: str = ""
        name: str | None = None
        icon: str | None = None
        native_unit_of_measurement: str | None = None
        device_class: Any = None
        state_class: Any = None

    sens.SensorEntity = SensorEntity
    sens.SensorEntityDescription = SensorEntityDescription

    bs = sys.modules["homeassistant.components.binary_sensor"]
    bs.BinarySensorDeviceClass = type(
        "BinarySensorDeviceClass", (), {"PROBLEM": "problem", "RUNNING": "running"}
    )

    class BinarySensorEntity:
        pass

    @dataclass(frozen=True, kw_only=True)
    class BinarySensorEntityDescription:
        key: str = ""
        name: str | None = None
        icon: str | None = None
        device_class: Any = None

    bs.BinarySensorEntity = BinarySensorEntity
    bs.BinarySensorEntityDescription = BinarySensorEntityDescription

    cal = sys.modules["homeassistant.components.calendar"]

    class CalendarEntity:
        pass

    @dataclass
    class CalendarEvent:
        start: Any = None
        end: Any = None
        summary: str = ""
        description: str = ""

    cal.CalendarEntity = CalendarEntity
    cal.CalendarEvent = CalendarEvent

    img = sys.modules["homeassistant.components.image"]

    class ImageEntity:
        def __init__(self, hass: Any) -> None:
            self.hass = hass

    img.ImageEntity = ImageEntity
