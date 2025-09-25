"""MagicLight standalone test harness.

This harness lets you exercise the custom integration service handlers and the
add-on primitives without a running Home Assistant instance. It spins up the
real `MagicLightPrimitives` and `HomeAssistantWebSocketClient` (subclassed to
stub network calls) so you can observe exactly which service payloads the
add-on would send.

Example usage:
    python tools/magiclight_harness.py step_up kitchen --magic-mode --lights-on --max-steps 24

The script can also be imported by tests to drive more structured scenarios.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import pathlib
import sys
import types
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Tuple, Union

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ADDON_ROOT = REPO_ROOT / "addon"
if str(ADDON_ROOT) not in sys.path:
    sys.path.insert(0, str(ADDON_ROOT))


def _install_test_stubs() -> None:
    """Provide minimal modules when Home Assistant/voluptuous aren't installed."""

    if "voluptuous" not in sys.modules:
        vol_mod = types.ModuleType("voluptuous")

        class Schema:
            def __init__(self, schema_def: Any) -> None:
                self.schema_def = schema_def

            def __call__(self, value: Dict[str, Any]) -> Dict[str, Any]:
                return value

        class Required:
            def __init__(self, key: Any) -> None:
                self.key = key

            def __hash__(self) -> int:
                return hash(self.key)

            def __eq__(self, other: Any) -> bool:
                return isinstance(other, Required) and other.key == self.key

        def Any(*_: Any) -> Callable[[Any], Any]:
            def validator(value: Any) -> Any:
                return value

            return validator

        vol_mod.Schema = Schema
        vol_mod.Required = Required
        vol_mod.Any = Any
        sys.modules["voluptuous"] = vol_mod

    if "homeassistant" not in sys.modules:
        ha_mod = types.ModuleType("homeassistant")
        ha_mod.__path__ = []  # type: ignore[attr-defined]
        sys.modules["homeassistant"] = ha_mod
    else:
        ha_mod = sys.modules["homeassistant"]

    if "homeassistant.core" not in sys.modules:
        core_mod = types.ModuleType("homeassistant.core")

        class HomeAssistant:  # pragma: no cover - simple stub
            def __init__(self) -> None:
                self.data: Dict[str, Any] = {}
                self.services: Any = None

        class ServiceCall:  # pragma: no cover - simple stub
            def __init__(self, data: Dict[str, Any] | None = None) -> None:
                self.data = data or {}

        core_mod.HomeAssistant = HomeAssistant
        core_mod.ServiceCall = ServiceCall
        sys.modules["homeassistant.core"] = core_mod
        setattr(ha_mod, "core", core_mod)

    if "homeassistant.config_entries" not in sys.modules:
        config_entries_mod = types.ModuleType("homeassistant.config_entries")

        class ConfigEntry:  # pragma: no cover - simple stub
            def __init__(self, entry_id: str = "test", data: Dict[str, Any] | None = None, title: str = "MagicLight Harness") -> None:
                self.entry_id = entry_id
                self.data = data or {}
                self.title = title

        config_entries_mod.ConfigEntry = ConfigEntry
        sys.modules["homeassistant.config_entries"] = config_entries_mod
        setattr(ha_mod, "config_entries", config_entries_mod)

    if "homeassistant.helpers" not in sys.modules:
        helpers_mod = types.ModuleType("homeassistant.helpers")
        helpers_mod.__path__ = []  # type: ignore[attr-defined]
        sys.modules["homeassistant.helpers"] = helpers_mod
        setattr(ha_mod, "helpers", helpers_mod)
    else:
        helpers_mod = sys.modules["homeassistant.helpers"]

    if "homeassistant.helpers.config_validation" not in sys.modules:
        cv_mod = types.ModuleType("homeassistant.helpers.config_validation")

        def string(value: Any) -> str:
            return value if isinstance(value, str) else str(value)

        cv_mod.string = string
        sys.modules["homeassistant.helpers.config_validation"] = cv_mod
        setattr(helpers_mod, "config_validation", cv_mod)

    if "homeassistant.helpers.typing" not in sys.modules:
        typing_mod = types.ModuleType("homeassistant.helpers.typing")
        typing_mod.ConfigType = Dict[str, Any]
        sys.modules["homeassistant.helpers.typing"] = typing_mod
        setattr(helpers_mod, "typing", typing_mod)

    if "astral" not in sys.modules:
        astral_mod = types.ModuleType("astral")

        class LocationInfo:
            def __init__(self, name: str = "", region: str = "", timezone: str = "UTC", latitude: float = 0.0, longitude: float = 0.0) -> None:
                self.name = name
                self.region = region
                self.timezone = timezone
                self.latitude = latitude
                self.longitude = longitude
                self.observer = types.SimpleNamespace(latitude=latitude, longitude=longitude)

        astral_mod.LocationInfo = LocationInfo
        sys.modules["astral"] = astral_mod
    else:
        astral_mod = sys.modules["astral"]

    if "astral.sun" not in sys.modules:
        sun_mod = types.ModuleType("astral.sun")
        from datetime import datetime, timedelta, timezone

        def sun(observer: Any, date: Any = None, tzinfo: Any = None) -> Dict[str, Any]:
            tz = tzinfo or datetime.now().astimezone().tzinfo or timezone.utc
            current_date = date or datetime.now(tz).date()
            base = datetime.combine(current_date, datetime.min.time(), tz) + timedelta(hours=6)
            return {
                "sunrise": base - timedelta(hours=1),
                "sunset": base + timedelta(hours=6),
                "noon": base,
                "dawn": base - timedelta(hours=2),
                "dusk": base + timedelta(hours=7),
            }

        def elevation(observer: Any, date_time: Any) -> float:  # pragma: no cover - constant stub
            return 45.0

        sun_mod.sun = sun
        sun_mod.elevation = elevation
        sys.modules["astral.sun"] = sun_mod
        setattr(astral_mod, "sun", sun_mod)

    if "websockets" not in sys.modules:
        websockets_mod = types.ModuleType("websockets")

        async def _not_connected(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("websockets not available in harness")

        websockets_mod.connect = _not_connected

        client_mod = types.ModuleType("websockets.client")

        class WebSocketClientProtocol:  # pragma: no cover - placeholder stub
            pass

        client_mod.WebSocketClientProtocol = WebSocketClientProtocol
        websockets_mod.client = client_mod
        sys.modules["websockets"] = websockets_mod
        sys.modules["websockets.client"] = client_mod


_install_test_stubs()

import custom_components.magiclight as magiclight_integration
from custom_components.magiclight.const import (
    ATTR_AREA_ID,
    DOMAIN,
    SERVICE_DIM_DOWN,
    SERVICE_DIM_UP,
    SERVICE_MAGICLIGHT_OFF,
    SERVICE_MAGICLIGHT_ON,
    SERVICE_MAGICLIGHT_TOGGLE,
    SERVICE_RESET,
    SERVICE_STEP_DOWN,
    SERVICE_STEP_UP,
)

from addon.main import HomeAssistantWebSocketClient
from addon.brain import DEFAULT_MAX_DIM_STEPS


_LOGGER = logging.getLogger(__name__)

ServiceHandler = Callable[["FakeServiceCall"], Awaitable[None]]
ServiceListener = Callable[["FakeServiceCall"], Awaitable[None]]


@dataclass
class FakeServiceCall:
    """Lightweight substitute for Home Assistant's ServiceCall."""

    domain: str
    service: str
    data: Dict[str, Any]


class FakeServiceRegistry:
    """In-memory service registry that mimics hass.services."""

    def __init__(self) -> None:
        self._services: Dict[Tuple[str, str], Tuple[ServiceHandler, Callable[[Dict[str, Any]], Dict[str, Any]] | None]] = {}
        self._listeners: List[ServiceListener] = []

    def async_register(
        self,
        domain: str,
        service: str,
        handler: ServiceHandler,
        schema: Callable[[Dict[str, Any]], Dict[str, Any]] | None = None,
    ) -> None:
        _LOGGER.debug("Registered service %s.%s", domain, service)
        self._services[(domain, service)] = (handler, schema)

    def async_remove(self, domain: str, service: str) -> None:
        _LOGGER.debug("Removed service %s.%s", domain, service)
        self._services.pop((domain, service), None)

    def add_listener(self, listener: ServiceListener) -> None:
        self._listeners.append(listener)

    async def async_call(self, domain: str, service: str, data: Dict[str, Any]) -> FakeServiceCall:
        key = (domain, service)
        if key not in self._services:
            raise ValueError(f"Service {domain}.{service} is not registered")

        handler, schema = self._services[key]
        call_data = data.copy()
        if schema is not None:
            call_data = schema(call_data)
        call = FakeServiceCall(domain=domain, service=service, data=call_data)

        _LOGGER.debug("Invoking service handler for %s.%s with %s", domain, service, call_data)
        await handler(call)

        for listener in self._listeners:
            await listener(call)

        return call


class FakeHomeAssistant:
    """Minimal stand-in for Home Assistant core object."""

    def __init__(self) -> None:
        self.data: Dict[str, Any] = {}
        self.services = FakeServiceRegistry()


SERVICE_TO_METHOD = {
    SERVICE_STEP_UP: "step_up",
    SERVICE_STEP_DOWN: "step_down",
    SERVICE_DIM_UP: "dim_up",
    SERVICE_DIM_DOWN: "dim_down",
    SERVICE_RESET: "reset",
    SERVICE_MAGICLIGHT_ON: "magiclight_on",
    SERVICE_MAGICLIGHT_OFF: "magiclight_off",
    SERVICE_MAGICLIGHT_TOGGLE: "magiclight_toggle",
}


class HarnessClient(HomeAssistantWebSocketClient):
    """Subclass of the real websocket client with HA/network interactions stubbed."""

    DEFAULT_LAT = 37.7749
    DEFAULT_LON = -122.4194
    DEFAULT_TZ = "UTC"

    def __init__(self, *, max_dim_steps: int = DEFAULT_MAX_DIM_STEPS) -> None:
        super().__init__(host="stub", port=0, access_token="harness", use_ssl=False)

        # Never connect in the harness
        self.websocket = None

        # Configure adaptive lighting defaults
        self.max_dim_steps = max_dim_steps
        self.config = {"max_dim_steps": max_dim_steps}
        self.curve_params = {}
        self.latitude = self.DEFAULT_LAT
        self.longitude = self.DEFAULT_LON
        self.timezone = self.DEFAULT_TZ
        os.environ.setdefault("HASS_LATITUDE", str(self.latitude))
        os.environ.setdefault("HASS_LONGITUDE", str(self.longitude))
        os.environ.setdefault("HASS_TIME_ZONE", self.timezone)

        # Local state tracking for harness assertions
        self._action_log: List[Dict[str, Any]] = []
        self._area_state: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Local helpers
    # ------------------------------------------------------------------
    def _ensure_area(self, area_id: str) -> Dict[str, Any]:
        return self._area_state.setdefault(
            area_id,
            {
                "is_on": False,
                "brightness": 50.0,
                "kelvin": 3000,
            },
        )

    def _log(self, action: str, **details: Any) -> None:
        event = {"action": action, **details}
        _LOGGER.info("Harness action: %s", event)
        self._action_log.append(event)

    def consume_action_log(self) -> List[Dict[str, Any]]:
        actions = list(self._action_log)
        self._action_log.clear()
        return actions

    # ------------------------------------------------------------------
    # Configuration utilities
    # ------------------------------------------------------------------
    def configure_area(
        self,
        area_id: str,
        *,
        magic_mode: bool = False,
        lights_on: bool = False,
        time_offset: float = 0.0,
        brightness: int | None = None,
        kelvin: int | None = None,
    ) -> None:
        state = self._ensure_area(area_id)
        state["is_on"] = lights_on
        if brightness is not None:
            state["brightness"] = float(brightness)
        if kelvin is not None:
            state["kelvin"] = kelvin

        if magic_mode:
            self.enable_magic_mode(area_id)
        else:
            self.magic_mode_areas.discard(area_id)

        if time_offset:
            self.magic_mode_time_offsets[area_id] = time_offset
        else:
            self.magic_mode_time_offsets.pop(area_id, None)

        if area_id not in self.magic_mode_brightness_offsets:
            self.magic_mode_brightness_offsets[area_id] = 0.0

    # ------------------------------------------------------------------
    # Overrides that interface with Home Assistant
    # ------------------------------------------------------------------
    async def determine_light_target(self, area_id: str) -> Tuple[str, Any]:
        return "area_id", area_id

    async def any_lights_on_in_area(self, area_id_or_list: Union[str, Iterable[str]]) -> bool:
        areas = [area_id_or_list] if isinstance(area_id_or_list, str) else list(area_id_or_list)
        return any(self._ensure_area(area).get("is_on", False) for area in areas)

    async def call_service(
        self,
        domain: str,
        service: str,
        service_data: Dict[str, Any],
        target: Dict[str, Any],
    ) -> None:
        area_value = target.get("area_id") or target.get("entity_id")
        if isinstance(area_value, list):
            affected = area_value
        elif area_value is not None:
            affected = [area_value]
        else:
            affected = []

        for area_id in affected:
            state = self._ensure_area(area_id)
            if domain == "light" and service == "turn_on":
                if "brightness_step_pct" in service_data:
                    step = float(service_data["brightness_step_pct"])
                    state["brightness"] = max(1.0, min(100.0, state["brightness"] + step))
                if "brightness_pct" in service_data:
                    state["brightness"] = max(1.0, min(100.0, float(service_data["brightness_pct"])))
                if "kelvin" in service_data:
                    state["kelvin"] = int(service_data["kelvin"])
                if "rgb_color" in service_data:
                    state["rgb"] = tuple(service_data["rgb_color"])
                if "xy_color" in service_data:
                    state["xy"] = tuple(service_data["xy_color"])
                state["is_on"] = True
            elif domain == "light" and service == "turn_off":
                state["is_on"] = False

        # Log direct brightness adjustments (skip adaptive turn_on duplicates)
        if not (
            domain == "light"
            and service == "turn_on"
            and "brightness_pct" in service_data
        ):
            self._log(
                "call_service",
                domain=domain,
                service=service,
                service_data=service_data,
                target=target,
                affected_areas=affected,
            )

    async def turn_on_lights_adaptive(
        self,
        area_id: str,
        adaptive_values: Dict[str, Any],
        transition: int = 1,
        *,
        include_color: bool = True,
    ) -> None:
        await super().turn_on_lights_adaptive(
            area_id,
            adaptive_values,
            transition,
            include_color=include_color,
        )

        state = self._ensure_area(area_id)
        applied: Dict[str, Any] = {
            "brightness": round(state.get("brightness", 0.0), 2),
        }
        if include_color:
            for key in ("kelvin", "rgb", "xy"):
                if key in state:
                    applied[key] = state[key]
        else:
            applied["color_skipped"] = True

        self._log(
            "turn_on_lights_adaptive",
            area_id=area_id,
            requested_values=dict(adaptive_values),
            applied_values=applied,
            transition=transition,
            include_color=include_color,
        )


class MagicLightHarness:
    """Coordinates the fake hass core and the harness websocket client."""

    def __init__(self, *, max_dim_steps: int = DEFAULT_MAX_DIM_STEPS) -> None:
        self.hass = FakeHomeAssistant()
        self.client = HarnessClient(max_dim_steps=max_dim_steps)
        self._setup_complete = False

        self.hass.services.add_listener(self._forward_to_primitives)

    async def setup(self) -> None:
        if not self._setup_complete:
            await magiclight_integration.async_setup(self.hass, {})
            self._setup_complete = True

    def configure_area(self, *args: Any, **kwargs: Any) -> None:
        self.client.configure_area(*args, **kwargs)

    async def trigger_service(self, service: str, area_payload: Union[str, List[str]]) -> List[Dict[str, Any]]:
        if not self._setup_complete:
            await self.setup()

        data = {ATTR_AREA_ID: area_payload}
        await self.hass.services.async_call(DOMAIN, service, data)
        return self.client.consume_action_log()

    async def _forward_to_primitives(self, call: FakeServiceCall) -> None:
        method_name = SERVICE_TO_METHOD.get(call.service)
        if method_name is None:
            _LOGGER.warning("No primitive mapped for service %s", call.service)
            return

        primitives = self.client.primitives
        method = getattr(primitives, method_name)
        area_value = call.data[ATTR_AREA_ID]
        source = "test_harness"

        if call.service == SERVICE_MAGICLIGHT_TOGGLE and isinstance(area_value, list):
            await primitives.magiclight_toggle_multiple(area_value, source=source)
            return

        if isinstance(area_value, list):
            for area in area_value:
                await method(area, source=source)
        else:
            await method(area_value, source=source)


# ----------------------------------------------------------------------------
# CLI entry point
# ----------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Exercise MagicLight primitives without Home Assistant")
    parser.add_argument(
        "service",
        choices=sorted(SERVICE_TO_METHOD.keys()),
        help="MagicLight service to invoke",
    )
    parser.add_argument(
        "areas",
        nargs="+",
        help="Area ID(s) to target. Multiple values simulate list payloads",
    )
    parser.add_argument(
        "--magic-mode",
        action="store_true",
        help="Pre-enable magic mode for the supplied areas",
    )
    parser.add_argument(
        "--lights-on",
        action="store_true",
        help="Start with the lights on in the supplied areas",
    )
    parser.add_argument(
        "--time-offset",
        type=float,
        default=0.0,
        help="Initial TimeLocation offset (minutes) for the areas",
    )
    parser.add_argument(
        "--brightness",
        type=int,
        help="Initial brightness percentage",
    )
    parser.add_argument(
        "--kelvin",
        type=int,
        help="Initial color temperature (kelvin)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=DEFAULT_MAX_DIM_STEPS,
        help="Number of dimming steps for MagicLight curve calculations",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser


def _format_actions(actions: List[Dict[str, Any]]) -> str:
    if not actions:
        return "(no actions recorded)"

    lines = []
    for idx, action in enumerate(actions, start=1):
        payload = ", ".join(f"{key}={value}" for key, value in action.items() if key != "action")
        lines.append(f"{idx}. {action['action']} -> {payload}")
    return "\n".join(lines)


async def _run_from_cli(args: argparse.Namespace) -> None:
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    harness = MagicLightHarness(max_dim_steps=args.max_steps)
    await harness.setup()

    for area in args.areas:
        harness.configure_area(
            area,
            magic_mode=args.magic_mode,
            lights_on=args.lights_on,
            time_offset=args.time_offset,
            brightness=args.brightness,
            kelvin=args.kelvin,
        )

    area_payload: Union[str, List[str]] = args.areas[0] if len(args.areas) == 1 else args.areas
    actions = await harness.trigger_service(args.service, area_payload)
    print(_format_actions(actions))


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()
    asyncio.run(_run_from_cli(args))


if __name__ == "__main__":
    main()
