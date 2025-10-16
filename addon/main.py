#!/usr/bin/env python3
"""Home Assistant WebSocket client - listens for events."""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional, Sequence, Union

import websockets
from websockets.client import WebSocketClientProtocol

from ha_blueprint_manager import BlueprintAutomationManager

from primitives import MagicLightPrimitives
from brain import (
    get_adaptive_lighting,
    ColorMode,
    DEFAULT_MAX_DIM_STEPS,
    DEFAULT_MIN_BRIGHTNESS,
    DEFAULT_MAX_BRIGHTNESS,
)
from light_controller import (
    LightControllerFactory,
    MultiProtocolController,
    LightCommand,
    Protocol
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HomeAssistantWebSocketClient:
    """WebSocket client for Home Assistant."""
    
    def __init__(self, host: str, port: int, access_token: str, use_ssl: bool = False):
        """Initialize the client.
        
        Args:
            host: Home Assistant host
            port: Home Assistant port
            access_token: Long-lived access token
            use_ssl: Whether to use SSL/TLS
        """
        self.host = host
        self.port = port
        self.access_token = access_token
        self.use_ssl = use_ssl
        self.websocket: WebSocketClientProtocol = None
        self.message_id = 1
        self.sun_data = {}  # Store latest sun data
        self.area_to_light_entity = {}  # Map area aliases to their grouped light entity
        self.area_group_map: Dict[str, Dict[str, str]] = {}  # Normalized area key -> {"zha_group": entity, "hue_group": entity, ...}
        self.group_entity_info: Dict[str, Dict[str, Any]] = {}  # Metadata for grouped light entities
        self.primitives = MagicLightPrimitives(self)  # Initialize primitives handler
        self.light_controller = None  # Will be initialized after websocket connection
        self.latitude = None  # Home Assistant latitude
        self.longitude = None  # Home Assistant longitude
        self.timezone = None  # Home Assistant timezone
        self.periodic_update_task = None  # Task for periodic light updates
        self.magic_mode_areas = set()  # Track which areas are in magic mode
        self.magic_mode_time_offsets = {}  # Track time offsets for dimming along curve
        self.magic_mode_brightness_offsets = {}  # Track brightness adjustments (percentage) along the curve
        self.cached_states = {}  # Cache of entity states
        self.last_states_update = None  # Timestamp of last states update
        self.area_parity_cache = {}  # Cache of area ZHA parity status

        # Restore previously persisted magic mode state (if any)
        self._load_magic_mode_state()

        manage_blueprints_env = os.getenv("MANAGE_MAGICLIGHT_BLUEPRINTS", "true").lower()
        self.manage_blueprints = manage_blueprints_env not in ("false", "0", "no")
        self.blueprint_manager = BlueprintAutomationManager(self, enabled=self.manage_blueprints)

        # Brightness curve configuration (populated from supervisor/designer config)
        self.max_dim_steps = DEFAULT_MAX_DIM_STEPS
        self.min_brightness = DEFAULT_MIN_BRIGHTNESS
        self.max_brightness = DEFAULT_MAX_BRIGHTNESS
        
        # Color mode configuration - defaults to KELVIN (CT)
        color_mode_str = os.getenv("COLOR_MODE", "kelvin").lower()
        try:
            # Try to get by value (lowercase) first
            self.color_mode = ColorMode(color_mode_str)
        except ValueError:
            # Try uppercase enum name as fallback
            try:
                self.color_mode = ColorMode[color_mode_str.upper()]
            except KeyError:
                logger.warning(f"Invalid COLOR_MODE '{color_mode_str}', defaulting to KELVIN")
                self.color_mode = ColorMode.KELVIN
        logger.info(f"Using color mode: {self.color_mode.value}")
        
        # Note: Gamma parameters have been replaced with morning/evening curve parameters in brain.py
        # The new curve system provides separate control for morning and evening transitions
        
        
    @property
    def websocket_url(self) -> str:
        """Get the WebSocket URL."""
        # Check if a full URL is provided via environment variable
        url_from_env = os.getenv("HA_WEBSOCKET_URL")
        if url_from_env:
            return url_from_env
        
        # Otherwise construct from host/port
        protocol = "wss" if self.use_ssl else "ws"
        return f"{protocol}://{self.host}:{self.port}/api/websocket"
        
    def _get_next_message_id(self) -> int:
        """Get the next message ID."""
        current_id = self.message_id
        self.message_id += 1
        return current_id
    
    def _normalize_area_key(self, value: Optional[str]) -> Optional[str]:
        """Normalize area identifiers to a lowercase underscore-delimited key."""
        if not value or not isinstance(value, str):
            return None
        normalized = value.strip().lower().replace("-", "_")
        normalized = normalized.replace(" ", "_")
        while "__" in normalized:
            normalized = normalized.replace("__", "_")
        return normalized or None

    def _register_area_group_entity(
        self,
        entity_id: str,
        *,
        area_name: Optional[str],
        area_id: Optional[str],
        group_type: str,
    ) -> None:
        """Register a grouped light entity for fast lookup by area aliases."""
        if not entity_id or not entity_id.startswith("light."):
            return

        # Track metadata about the entity
        display_name = area_name or area_id or entity_id
        self.group_entity_info[entity_id] = {
            "type": group_type,
            "area": display_name,
            "area_id": area_id,
            "area_name": area_name,
        }

        # Store normalized mapping for selection logic
        canonical_key = self._normalize_area_key(area_id or area_name)
        if canonical_key:
            area_entry = self.area_group_map.setdefault(canonical_key, {})
            area_entry[group_type] = entity_id

        # Build alias variations to continue supporting legacy lookups
        alias_candidates = set()
        for raw in (area_id, area_name):
            if raw and isinstance(raw, str):
                trimmed = raw.strip()
                if not trimmed:
                    continue
                alias_candidates.add(trimmed)
                alias_candidates.add(trimmed.replace("-", " "))

        # Include canonical key so callers who already rely on lowercase ids still work
        if canonical_key:
            alias_candidates.add(canonical_key)

        for candidate in alias_candidates:
            if not candidate:
                continue
            variants = {
                candidate,
                candidate.lower(),
                candidate.replace("_", " "),
                candidate.replace("_", " ").lower(),
                candidate.replace(" ", "_"),
                candidate.replace(" ", "_").lower(),
            }
            for variant in variants:
                if variant:
                    self.area_to_light_entity[variant] = entity_id

    def _update_area_group_mapping(
        self,
        entity_id: str,
        friendly_name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update grouped light mappings for ZHA Magic groups and Hue rooms."""
        if not entity_id or not entity_id.startswith("light."):
            return

        attributes = attributes or {}
        friendly_name = friendly_name or ""
        friendly_lower = friendly_name.lower()
        entity_lower = entity_id.lower()

        # Detect Hue grouped light entities exposed by the Hue integration
        is_hue_group = False
        hue_flags = [
            attributes.get("is_hue_group"),
            attributes.get("is_hue_grouped_light"),
            attributes.get("is_hue_grouped"),
            attributes.get("is_group"),
        ]
        for flag in hue_flags:
            if isinstance(flag, bool) and flag:
                is_hue_group = True
                break
            if isinstance(flag, str) and flag.strip().lower() in {"true", "1", "yes", "on"}:
                is_hue_group = True
                break

        if not is_hue_group:
            hue_resource = attributes.get("hue_resource_type") or attributes.get("type")
            if isinstance(hue_resource, str) and hue_resource.lower() in {"grouped_light", "room"}:
                is_hue_group = True

        if not is_hue_group:
            icon = attributes.get("icon")
            if isinstance(icon, str) and "bulb-group" in icon:
                is_hue_group = True

        if not is_hue_group:
            hue_group_id = attributes.get("hue_group") or attributes.get("hue_group_id")
            if hue_group_id:
                is_hue_group = True

        if is_hue_group:
            area_id = attributes.get("area_id")
            area_name = friendly_name or attributes.get("name")
            self._register_area_group_entity(
                entity_id,
                area_name=area_name,
                area_id=area_id,
                group_type="hue_group",
            )
            logger.debug(f"Registered Hue grouped light '{entity_id}' for area '{area_name or area_id}'")
            return

        # Detect Magic_ ZHA group entities
        if "magic_" not in entity_lower and "magic_" not in friendly_lower:
            return

        area_name = None

        # Try to extract from friendly_name first (preserving case)
        if "Magic_" in friendly_name:
            parts = friendly_name.split("Magic_")
            if len(parts) >= 2:
                area_name = parts[-1].strip()
        elif "magic_" in friendly_lower:
            idx = friendly_lower.index("magic_")
            area_name = friendly_name[idx + 6:].strip()

        # If not found in friendly_name, try entity_id
        if not area_name and "magic_" in entity_lower:
            idx = entity_lower.index("magic_")
            area_name = entity_id[idx + 6:]
            area_name = area_name.replace("light.", "")

        if area_name:
            self._register_area_group_entity(
                entity_id,
                area_name=area_name,
                area_id=None,
                group_type="zha_group",
            )
            logger.debug(f"Registered Magic ZHA group '{entity_id}' for area '{area_name}'")

    # Backwards compatibility for tests and legacy callers
    def _update_zha_group_mapping(self, entity_id: str, friendly_name: str) -> None:
        """Legacy wrapper maintained for compatibility with older tests."""
        self._update_area_group_mapping(entity_id, friendly_name, None)

    def _get_fallback_group_entity(self, area_id: str) -> Optional[str]:
        """Return the first grouped entity mapped to any alias of the given area."""
        if not area_id or not isinstance(area_id, str):
            return None

        candidates = [
            area_id,
            area_id.lower(),
            area_id.replace("_", " "),
            area_id.replace("_", " ").lower(),
            area_id.replace(" ", "_"),
            area_id.replace(" ", "_").lower(),
        ]

        seen = set()
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            entity = self.area_to_light_entity.get(candidate)
            if entity:
                return entity
        return None
    async def authenticate(self) -> bool:
        """Authenticate with Home Assistant."""
        try:
            # Wait for auth_required message
            auth_required = await self.websocket.recv()
            auth_msg = json.loads(auth_required)
            
            if auth_msg["type"] != "auth_required":
                logger.error(f"Unexpected message type: {auth_msg['type']}")
                return False
                
            # Send authentication
            await self.websocket.send(json.dumps({
                "type": "auth",
                "access_token": self.access_token
            }))
            
            # Wait for auth result
            auth_result = await self.websocket.recv()
            result_msg = json.loads(auth_result)
            
            if result_msg["type"] == "auth_ok":
                logger.info("Successfully authenticated with Home Assistant")
                return True
            else:
                logger.error(f"Authentication failed: {result_msg}")
                return False
                
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False
            
    async def subscribe_events(self, event_type: str = None) -> int:
        """Subscribe to events.
        
        Args:
            event_type: Specific event type to subscribe to, or None for all events
            
        Returns:
            Message ID of the subscription request
        """
        message_id = self._get_next_message_id()
        
        subscribe_msg = {
            "id": message_id,
            "type": "subscribe_events"
        }
        
        if event_type:
            subscribe_msg["event_type"] = event_type
            
        await self.websocket.send(json.dumps(subscribe_msg))
        logger.info(f"Subscribed to events (id: {message_id}, type: {event_type or 'all'})")
        
        return message_id
        
    async def call_service(self, domain: str, service: str, service_data: Dict[str, Any], target: Optional[Dict[str, Any]] = None) -> int:
        """Call a Home Assistant service.
        
        Args:
            domain: Service domain (e.g., 'light')
            service: Service name (e.g., 'turn_on')
            service_data: Service parameters
            
        Returns:
            Message ID of the service call
        """
        message_id = self._get_next_message_id()
        
        # Handle target parameter separately from service_data
        final_target = target or {}
        final_service_data = service_data.copy() if service_data else {}
        
        # Extract area_id or entity_id from service_data if present (legacy support)
        if "area_id" in final_service_data:
            final_target["area_id"] = final_service_data.pop("area_id")
        if "entity_id" in final_service_data:
            final_target["entity_id"] = final_service_data.pop("entity_id")
        
        # Note: ZHA group vs area-based control is now handled in turn_on_lights_adaptive
        # based on whether the area has ZHA parity (all lights are ZHA)
        # This call_service method remains generic and doesn't auto-substitute
        
        service_msg = {
            "id": message_id,
            "type": "call_service",
            "domain": domain,
            "service": service
        }
        
        if final_service_data:
            service_msg["service_data"] = final_service_data
        if final_target:
            service_msg["target"] = final_target

        logger.debug(f"Sending service call: {domain}.{service} (id: {message_id})")
        await self.websocket.send(json.dumps(service_msg))
        logger.debug(f"Called service: {domain}.{service} (id: {message_id})")
        
        return message_id
        
    async def determine_light_target(self, area_id: str) -> tuple[str, Any]:
        """Determine the best target for controlling lights in an area.
        
        This consolidates the logic for deciding whether to use:
        - ZHA group entity (if all lights are ZHA)
        - Area-based control (if any non-ZHA lights exist)
        
        Args:
            area_id: The area ID to control
            
        Returns:
            Tuple of (target_type, target_value) where:
            - target_type is "entity_id" or "area_id"
            - target_value is the entity/area ID to use
        """
        normalized_key = self._normalize_area_key(area_id)
        group_candidates = self.area_group_map.get(normalized_key, {}) if normalized_key else {}

        hue_entity = group_candidates.get("hue_group")
        zha_entity = group_candidates.get("zha_group")

        # Fall back to legacy lookup table if we did not find a candidate above
        fallback_entity = self._get_fallback_group_entity(area_id)
        if fallback_entity:
            meta = self.group_entity_info.get(fallback_entity, {})
            group_type = meta.get("type")

            if not hue_entity and group_type == "hue_group":
                hue_entity = fallback_entity
            elif not zha_entity and group_type == "zha_group":
                zha_entity = fallback_entity
            elif not group_type and not zha_entity:
                # Legacy compatibility for tests that set area_to_light_entity manually
                zha_entity = fallback_entity

        has_parity = self.area_parity_cache.get(area_id, False)

        if hue_entity:
            logger.debug(f"✓ Using Hue grouped light entity '{hue_entity}' for area '{area_id}'")
            return "entity_id", hue_entity

        if zha_entity:
            if has_parity:
                logger.debug(f"✓ Using ZHA group entity '{zha_entity}' for area '{area_id}' (all lights are ZHA)")
                return "entity_id", zha_entity
            logger.debug(f"⚠ Area '{area_id}' has non-ZHA lights, using area-based control for full coverage")
        
        logger.info(f"Using area-based control for area '{area_id}'")
        return "area_id", area_id
    
    async def turn_on_lights_adaptive(
        self,
        area_id: str,
        adaptive_values: Dict[str, Any],
        transition: int = 1,
        *,
        include_color: bool = True,
    ) -> None:
        """Turn on lights with adaptive values using the light controller.
        
        Args:
            area_id: The area ID to control lights in
            adaptive_values: Adaptive lighting values from get_adaptive_lighting
            transition: Transition time in seconds (default 1)
            include_color: Whether to include color data when turning on lights
        """
        # Determine the best target for this area
        target_type, target_value = await self.determine_light_target(area_id)
        
        # Build service data
        service_data = {
            "transition": transition
        }
        
        # Add brightness
        if 'brightness' in adaptive_values:
            service_data["brightness_pct"] = adaptive_values['brightness']
        
        # Add color data based on the configured color mode
        if include_color and self.color_mode == ColorMode.KELVIN and 'kelvin' in adaptive_values:
            service_data["kelvin"] = adaptive_values['kelvin']
        elif include_color and self.color_mode == ColorMode.RGB and 'rgb' in adaptive_values:
            service_data["rgb_color"] = adaptive_values['rgb']
        elif include_color and self.color_mode == ColorMode.XY and 'xy' in adaptive_values:
            service_data["xy_color"] = adaptive_values['xy']

        # Build target
        target = {target_type: target_value}

        # Debug log exactly what we're sending
        logger.info(f"MagicLight sending light.turn_on with data: {service_data}, target: {target}")

        # Call the service
        await self.call_service("light", "turn_on", service_data, target)
        
    async def get_states(self) -> List[Dict[str, Any]]:
        """Get all entity states.
        
        Returns:
            List of entity states, or empty list if failed
        """
        logger.info("Requesting all entity states...")
        result = await self.send_message_wait_response({"type": "get_states"})
        
        if result and isinstance(result, list):
            # Update cache
            self.cached_states.clear()
            for state in result:
                entity_id = state.get("entity_id", "")
                if entity_id:
                    self.cached_states[entity_id] = state
                    
                    # Extract sun data while we're here
                    if entity_id == "sun.sun":
                        self.sun_data = state.get("attributes", {})
                        logger.debug(f"Found sun data: elevation={self.sun_data.get('elevation')}")
            
            logger.info(f"✓ Loaded {len(result)} entity states")
            return result
        
        logger.error(f"Failed to get states or invalid response: {type(result)}")
        return list(self.cached_states.values()) if self.cached_states else []
    
    async def request_states(self) -> int:
        """Request all entity states (legacy method for initialization).
        
        Returns:
            Message ID of the request
        """
        message_id = self._get_next_message_id()
        
        states_msg = {
            "id": message_id,
            "type": "get_states"
        }
        
        await self.websocket.send(json.dumps(states_msg))
        logger.info(f"Requested states (id: {message_id})")
        
        return message_id
        
        
    async def get_config(self) -> bool:
        """Get Home Assistant configuration and wait for response.
        
        Returns:
            True if config was successfully loaded, False otherwise
        """
        logger.info("Requesting Home Assistant configuration...")
        result = await self.send_message_wait_response({"type": "get_config"})
        
        if result and isinstance(result, dict):
            if "latitude" in result and "longitude" in result:
                self.latitude = result.get("latitude")
                self.longitude = result.get("longitude")
                self.timezone = result.get("time_zone")
                logger.info(f"✓ Loaded HA location: lat={self.latitude}, lon={self.longitude}, tz={self.timezone}")
                
                # Set environment variables for brain.py to use as defaults
                if self.latitude:
                    os.environ["HASS_LATITUDE"] = str(self.latitude)
                if self.longitude:
                    os.environ["HASS_LONGITUDE"] = str(self.longitude)
                if self.timezone:
                    os.environ["HASS_TIME_ZONE"] = self.timezone
                    
                return True
            else:
                logger.warning(f"⚠ Config response missing location data: {result.keys()}")
        else:
            logger.error(f"Failed to get config or invalid response type: {type(result)}")
            
        return False
        
    
    def _get_data_directory(self) -> str:
        """Get the appropriate data directory based on environment.
        
        Returns:
            Path to the data directory
        """
        if os.path.exists("/data"):
            # Running in Home Assistant
            return "/data"
        else:
            # Running in development - use local .data directory
            data_dir = os.path.join(os.path.dirname(__file__), ".data")
            os.makedirs(data_dir, exist_ok=True)
            return data_dir

    def _get_state_file_path(self) -> str:
        """Return the path used for persisting magic mode state."""
        return os.path.join(self._get_data_directory(), "magic_mode_state.json")

    def _load_magic_mode_state(self) -> None:
        """Load previously saved magic mode state from disk."""

        path = self._get_state_file_path()

        if not os.path.exists(path):
            logger.debug("No persisted magic mode state found at %s", path)
            return

        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception as err:  # noqa: B902 - broad to avoid crash on malformed file
            logger.warning("Failed to load magic mode state from %s: %s", path, err)
            return

        restored_areas: set[str] = set()

        raw_areas = data.get("magic_mode_areas") or data.get("areas") or []
        if isinstance(raw_areas, list):
            restored_areas = {str(area) for area in raw_areas if isinstance(area, str) and area.strip()}

        raw_time_offsets = data.get("time_offsets") or {}
        if isinstance(raw_time_offsets, dict):
            for area, value in raw_time_offsets.items():
                area_key = str(area)
                try:
                    # Persisted values may be floats or ints; coerce to float for consistency
                    offset_value = float(value)
                except (TypeError, ValueError):
                    logger.debug("Skipping invalid time offset for area %s: %s", area_key, value)
                    continue
                self.magic_mode_time_offsets[area_key] = offset_value

        raw_brightness_offsets = data.get("brightness_offsets") or {}
        if isinstance(raw_brightness_offsets, dict):
            for area, value in raw_brightness_offsets.items():
                area_key = str(area)
                try:
                    brightness_offset = float(value)
                except (TypeError, ValueError):
                    logger.debug("Skipping invalid brightness offset for area %s: %s", area_key, value)
                    continue
                self.magic_mode_brightness_offsets[area_key] = brightness_offset

        if restored_areas:
            for area in restored_areas:
                self.magic_mode_time_offsets.setdefault(area, 0.0)
                self.magic_mode_brightness_offsets.setdefault(area, 0.0)
            self.magic_mode_areas.update(restored_areas)
            logger.info(
                "Restored magic mode state for %d area(s): %s",
                len(restored_areas),
                ", ".join(sorted(restored_areas)),
            )
        else:
            logger.debug("Magic mode state file contained no active areas")

    def save_magic_mode_state(self) -> None:
        """Persist the current magic mode state to disk."""

        path = self._get_state_file_path()

        state_payload = {
            "magic_mode_areas": sorted(self.magic_mode_areas),
            "time_offsets": {area: float(value) for area, value in self.magic_mode_time_offsets.items()},
            "brightness_offsets": {
                area: float(value) for area, value in self.magic_mode_brightness_offsets.items()
            },
        }

        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(state_payload, file, indent=2, sort_keys=True)
        except Exception as err:  # noqa: B902 - broad to avoid crashing the add-on
            logger.error("Failed to save magic mode state to %s: %s", path, err)

    
    def _update_color_mode_from_config(self, merged_config: Dict[str, Any]):
        """Update color mode from configuration if available.
        
        Args:
            merged_config: Dictionary containing configuration from options.json and designer_config.json
        """
        if 'color_mode' in merged_config:
            color_mode_str = str(merged_config['color_mode']).lower()
            try:
                # Try to get by value (lowercase) first
                new_color_mode = ColorMode(color_mode_str)
                if new_color_mode != self.color_mode:
                    logger.info(f"Updating color mode from config: {self.color_mode.value} -> {new_color_mode.value}")
                    self.color_mode = new_color_mode
            except ValueError:
                # Try uppercase enum name as fallback
                try:
                    new_color_mode = ColorMode[color_mode_str.upper()]
                    if new_color_mode != self.color_mode:
                        logger.info(f"Updating color mode from config: {self.color_mode.value} -> {new_color_mode.value}")
                        self.color_mode = new_color_mode
                except KeyError:
                    logger.warning(f"Invalid color_mode '{color_mode_str}' in config, keeping current: {self.color_mode.value}")
    

    async def any_lights_on_in_area(
        self,
        area_id_or_list: Union[str, Sequence[str]]
    ) -> bool:
        """Return True if any lights are on in the given area(s).

        Accepts a single area id/name/slug OR a list of them.
        Uses HA's template engine (no manual area registry lookup).
        """

        # Normalize to list[str]
        if isinstance(area_id_or_list, str):
            areas: list[str] = [area_id_or_list]
        else:
            areas = [a for a in area_id_or_list if isinstance(a, str)]

        if not areas:
            logger.warning("[template] no area_id provided")
            return False

        for area_id in areas:
            # Fast path: known group entity for this key
            normalized_key = self._normalize_area_key(area_id)
            light_entity_id = None
            if normalized_key and normalized_key in self.area_group_map:
                candidates = self.area_group_map[normalized_key]
                light_entity_id = candidates.get("hue_group") or candidates.get("zha_group")
            if not light_entity_id:
                light_entity_id = self._get_fallback_group_entity(area_id)
            if light_entity_id:
                state = self.cached_states.get(light_entity_id, {}).get("state")
                logger.info(f"[group_fastpath] {light_entity_id=} {area_id=} state={state}")
                if state in ("on", "off"):
                    if state == "on":
                        return True
                    continue  # go next area

            # Ask HA via template: does this area have ANY light.* that is 'on'?
            template = (
                f"{{{{ expand(area_entities('{area_id}')) "
                f"| selectattr('entity_id', 'match', '^light\\\\.') "
                f"| selectattr('state', 'eq', 'on') "
                f"| list | count > 0 }}}}"
            )
            logger.debug(f"[template] area={area_id} jinja={template}")

            resp = await self.send_message_wait_response(
                {
                    "type": "render_template",
                    "template": template,
                    "report_errors": True,
                    "timeout": 10,
                },
                full_envelope=True,
            )

            if isinstance(resp, dict) and resp.get("type") == "result" and resp.get("success", False):
                inner = resp.get("result") or {}
                rendered = inner.get("result")
                area_on = (
                    rendered if isinstance(rendered, bool)
                    else (str(rendered).strip().lower() in ("true", "1", "yes", "on"))
                )
                if area_on:
                    return True
            else:
                logger.warning(f"[template] failed for area={area_id}: {resp!r} (treating as off)")

        # None of the areas had lights on
        return False
    
    def enable_magic_mode(self, area_id: str):
        """Enable magic mode for an area.

        Args:
            area_id: The area ID to enable magic mode for
        """
        self.magic_mode_areas.add(area_id)

        # Use existing offset if available, otherwise set to 0
        if area_id not in self.magic_mode_time_offsets:
            self.magic_mode_time_offsets[area_id] = 0
            logger.info(f"Magic mode enabled for area {area_id}, offset set to 0")
        else:
            logger.info(f"Magic mode enabled for area {area_id}, keeping existing offset: {self.magic_mode_time_offsets[area_id]} minutes")

        # Initialize brightness adjustment storage if needed
        if area_id not in self.magic_mode_brightness_offsets:
            self.magic_mode_brightness_offsets[area_id] = 0.0

        self.save_magic_mode_state()
    
    async def disable_magic_mode(self, area_id: str):
        """Disable magic mode for an area.

        Args:
            area_id: The area ID to disable magic mode for
        """
        # Check if magic mode was actually enabled
        was_enabled = area_id in self.magic_mode_areas

        # Remove from magic mode areas but keep the offset in magic_mode_time_offsets
        self.magic_mode_areas.discard(area_id)

        # Debug logging to confirm area removal
        logger.info(f"Removed area {area_id} from magic_mode_areas. Current magic areas: {list(self.magic_mode_areas)}")

        if not was_enabled:
            logger.info(f"Magic mode already disabled for area {area_id}")
            return

        logger.info(f"Magic mode disabled for area {area_id}")
        self.save_magic_mode_state()
    
    def get_brightness_step_pct(self) -> float:
        """Return the configured brightness step size in percent."""
        steps = max(1, int(self.max_dim_steps) if self.max_dim_steps else DEFAULT_MAX_DIM_STEPS)
        return 100.0 / steps

    def get_brightness_bounds(self) -> tuple[int, int]:
        """Return the configured min/max brightness bounds."""
        return int(self.min_brightness), int(self.max_brightness)

    async def get_adaptive_lighting_for_area(
        self,
        area_id: str,
        current_time: Optional[datetime] = None,
        apply_time_offset: bool = True,
        apply_brightness_adjustment: bool = True,
    ) -> Dict[str, Any]:
        """Get adaptive lighting values for a specific area.
        
        This is the centralized method that should be used for all adaptive lighting calculations.
        
        Args:
            area_id: The area ID to get lighting values for
            current_time: Optional datetime to use for calculations (for time simulation)
            apply_time_offset: Whether to apply the magic mode time offset
            
        Returns:
            Dict containing adaptive lighting values
        """
        # Apply magic mode time offset if applicable
        if apply_time_offset and area_id in self.magic_mode_time_offsets:
            offset_minutes = self.magic_mode_time_offsets[area_id]
            if offset_minutes != 0:
                from datetime import timedelta
                from zoneinfo import ZoneInfo
                
                # Get current time or use provided time
                if current_time is None:
                    tzinfo = ZoneInfo(self.timezone) if self.timezone else None
                    current_time = datetime.now(tzinfo)
                
                # Apply the offset
                current_time = current_time + timedelta(minutes=offset_minutes)
                logger.info(f"Applying time offset of {offset_minutes} minutes for area {area_id}")
        
        # Load curve parameters by merging supervisor options and designer overrides
        curve_params = {}
        merged_config: Dict[str, Any] = {}
        
        data_dir = self._get_data_directory()
        
        # Load configs from appropriate directory
        for filename in ["options.json", "designer_config.json"]:
            path = os.path.join(data_dir, filename)
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        part = json.load(f)
                        if isinstance(part, dict):
                            merged_config.update(part)
                except Exception as e:
                    logger.debug(f"Could not load config from {path}: {e}")

        # Keep merged config available to other components
        try:
            self.config = merged_config
        except Exception:
            pass

        # Update color mode from configuration if available
        self._update_color_mode_from_config(merged_config)

        try:
            # Extract simplified curve parameters if present
            # Using the new parameter names from designer.html
            config_params = {}
            
            # Morning parameters (up)
            for key in ["mid_bri_up", "steep_bri_up", "mid_cct_up", "steep_cct_up"]:
                if key in merged_config:
                    config_params[key] = merged_config[key]
            
            # Evening parameters (dn)
            for key in ["mid_bri_dn", "steep_bri_dn", "mid_cct_dn", "steep_cct_dn"]:
                if key in merged_config:
                    config_params[key] = merged_config[key]
            
            # Mirror and gamma parameters
            for key in ["mirror_up", "mirror_dn", "gamma_ui", "max_dim_steps"]:
                if key in merged_config:
                    config_params[key] = merged_config[key]
            
            # Add config parameters to curve_params
            if config_params:
                curve_params["config"] = config_params
                
        except Exception as e:
            logger.debug(f"Could not parse curve parameters from merged config: {e}")
        
        # Add min/max values to curve parameters
        # These can come from environment variables or the merged config
        if 'min_color_temp' in merged_config:
            curve_params['min_color_temp'] = int(merged_config['min_color_temp'])
        elif os.getenv('MIN_COLOR_TEMP'):
            curve_params['min_color_temp'] = int(os.getenv('MIN_COLOR_TEMP'))
            
        if 'max_color_temp' in merged_config:
            curve_params['max_color_temp'] = int(merged_config['max_color_temp'])
        elif os.getenv('MAX_COLOR_TEMP'):
            curve_params['max_color_temp'] = int(os.getenv('MAX_COLOR_TEMP'))
            
        if 'min_brightness' in merged_config:
            curve_params['min_brightness'] = int(merged_config['min_brightness'])
        elif os.getenv('MIN_BRIGHTNESS'):
            curve_params['min_brightness'] = int(os.getenv('MIN_BRIGHTNESS'))
            
        if 'max_brightness' in merged_config:
            curve_params['max_brightness'] = int(merged_config['max_brightness'])
        elif os.getenv('MAX_BRIGHTNESS'):
            curve_params['max_brightness'] = int(os.getenv('MAX_BRIGHTNESS'))

        # Update cached brightness configuration for quick access elsewhere
        if 'max_dim_steps' in merged_config:
            try:
                self.max_dim_steps = int(merged_config['max_dim_steps']) or DEFAULT_MAX_DIM_STEPS
            except (TypeError, ValueError):
                logger.debug(f"Invalid max_dim_steps '{merged_config.get('max_dim_steps')}', keeping {self.max_dim_steps}")

        if 'min_brightness' in curve_params:
            self.min_brightness = curve_params['min_brightness']
        if 'max_brightness' in curve_params:
            self.max_brightness = curve_params['max_brightness']

        # Store curve parameters for dimming calculations
        self.curve_params = curve_params

        # Get adaptive lighting values with new morning/evening curves
        lighting_values = get_adaptive_lighting(
            latitude=self.latitude,
            longitude=self.longitude,
            timezone=self.timezone,
            current_time=current_time,
            **curve_params
        )
        
        # Log the calculation
        logger.info(f"Adaptive lighting for area {area_id}: {lighting_values['kelvin']}K, {lighting_values['brightness']}%")

        lighting_values = dict(lighting_values)

        if apply_brightness_adjustment:
            brightness_offset = self.magic_mode_brightness_offsets.get(area_id, 0.0)
            if brightness_offset:
                min_bri, max_bri = self.get_brightness_bounds()
                span = max(0, max_bri - min_bri)

                if span > 0:
                    adjustment = span * (brightness_offset / 100.0)
                    adjusted = lighting_values['brightness'] + adjustment
                    adjusted = max(min_bri, min(max_bri, adjusted))

                    if abs(adjusted - lighting_values['brightness']) > 1e-6:
                        logger.info(
                            f"Applying brightness offset for {area_id}: base {lighting_values['brightness']}% -> "
                            f"{adjusted}% (offset {brightness_offset:+.2f}%)"
                        )
                    lighting_values['brightness'] = int(round(adjusted))
                else:
                    logger.debug(
                        f"Brightness span is zero for area {area_id}; skipping offset adjustment"
                    )

        if 'brightness' in lighting_values:
            lighting_values['brightness'] = int(round(lighting_values['brightness']))

        return lighting_values
    
    async def update_lights_in_magic_mode(self, area_id: str):
        """Update lights in an area with adaptive lighting if in magic mode.
        
        Args:
            area_id: The area ID to update
        """
        try:
            # Only update if area is in magic mode
            if area_id not in self.magic_mode_areas:
                logger.debug(f"Area {area_id} not in magic mode, skipping update")
                return
            
            # Get adaptive lighting values using centralized method
            lighting_values = await self.get_adaptive_lighting_for_area(area_id)
            
            # Use the centralized light control function
            await self.turn_on_lights_adaptive(area_id, lighting_values, transition=2)
            
        except Exception as e:
            logger.error(f"Error updating lights in area {area_id}: {e}")
    
    async def reset_offsets_at_solar_midnight(self, last_check: Optional[datetime]) -> Optional[datetime]:
        """Reset all manual offsets to 0 at solar midnight.
        
        Args:
            last_check: The last time we checked for solar midnight
            
        Returns:
            The updated last check time
        """
        if not (self.latitude and self.longitude and self.timezone):
            return last_check
            
        from datetime import timedelta
        from zoneinfo import ZoneInfo
        from astral import LocationInfo
        from astral.sun import sun
        
        # Get current time in the correct timezone
        tzinfo = ZoneInfo(self.timezone)
        now = datetime.now(tzinfo)
        
        # Calculate solar events for today
        loc = LocationInfo(latitude=self.latitude, longitude=self.longitude, timezone=self.timezone)
        solar_events = sun(loc.observer, date=now.date(), tzinfo=tzinfo)
        solar_noon = solar_events["noon"]
        
        # Calculate solar midnight (12 hours from solar noon)
        if solar_noon.hour >= 12:
            solar_midnight = solar_noon - timedelta(hours=12)
        else:
            solar_midnight = solar_noon + timedelta(hours=12)
        
        # Initialize last check if needed
        if last_check is None:
            return now
            
        # Check if we've passed solar midnight since last check
        if last_check < solar_midnight <= now:
            # We've crossed solar midnight - reset all offsets
            logger.info(f"Solar midnight reached at {solar_midnight.strftime('%H:%M:%S')} - resetting all manual offsets to 0")
            
            # Reset all tracked offsets (time and brightness)
            areas_with_offsets = list(
                set(self.magic_mode_time_offsets.keys())
                | set(self.magic_mode_brightness_offsets.keys())
            )

            state_changed = False
            for area_id in areas_with_offsets:
                # Reset current offset
                old_offset = self.magic_mode_time_offsets.get(area_id, 0)
                if old_offset != 0:
                    logger.info(f"Resetting offset for area {area_id}: {old_offset} -> 0 minutes")
                    self.magic_mode_time_offsets[area_id] = 0
                    state_changed = True

                # Reset brightness adjustment for the new solar day
                brightness_offset = self.magic_mode_brightness_offsets.get(area_id, 0.0)
                if abs(brightness_offset) > 1e-6:
                    logger.info(
                        f"Resetting brightness offset for area {area_id}: {brightness_offset:+.2f}% -> 0%"
                    )
                    self.magic_mode_brightness_offsets[area_id] = 0.0
                    state_changed = True

                # Update lights in this area if it's in magic mode
                if area_id in self.magic_mode_areas:
                    await self.update_lights_in_magic_mode(area_id)

            if state_changed:
                self.save_magic_mode_state()
            
            return now
        elif now.date() != last_check.date():
            # New day - update last check
            return now
            
        return last_check
    
    async def periodic_light_updater(self):
        """Periodically update lights in areas that have magic mode enabled."""
        last_solar_midnight_check = None

        while True:
            try:
                # Wait for 60 seconds
                await asyncio.sleep(60)

                # Check if we should reset offsets at solar midnight
                last_solar_midnight_check = await self.reset_offsets_at_solar_midnight(last_solar_midnight_check)

                # Get all areas in magic mode
                magic_areas = list(self.magic_mode_areas)

                if not magic_areas:
                    logger.debug("No areas in magic mode for periodic update")
                    continue

                logger.info(f"Running periodic light update for {len(magic_areas)} areas in magic mode")
                logger.info(f"Areas in magic mode: {magic_areas}")

                # Update lights in all magic mode areas
                for area_id in magic_areas:
                    logger.info(f"Updating lights in magic mode area: {area_id}")
                    await self.update_lights_in_magic_mode(area_id)

            except asyncio.CancelledError:
                logger.info("Periodic light updater cancelled")
                break
            except Exception as e:
                logger.error(f"Error in periodic light updater: {e}")
                # Continue running even if there's an error
        
    async def refresh_area_parity_cache(self, areas_data: dict = None):
        """Refresh the cache of area ZHA parity status.
        
        This should be called during initialization and when areas/devices change.
        
        Args:
            areas_data: Pre-loaded areas data to avoid duplicate queries (optional)
        """
        try:
            if not self.light_controller:
                return
                
            zigbee_controller = self.light_controller.controllers.get(Protocol.ZIGBEE)
            if not zigbee_controller:
                return
            
            # Use provided areas data or fetch new
            if areas_data:
                areas = areas_data
            else:
                # Get all areas with their light information
                areas = await zigbee_controller.get_areas()
            
            # Clear and rebuild the cache
            self.area_parity_cache.clear()
            
            for area_id, area_info in areas.items():
                area_name = area_info.get('name', '')
                
                # Skip the Magic_Zigbee_Groups area - it's just for organizing group entities
                if area_name == 'Magic_Zigbee_Groups':
                    continue
                    
                zha_lights = area_info.get('zha_lights', [])
                non_zha_lights = area_info.get('non_zha_lights', [])
                
                # Area has parity if it has ZHA lights and no non-ZHA lights
                has_parity = len(zha_lights) > 0 and len(non_zha_lights) == 0
                self.area_parity_cache[area_id] = has_parity
                
                if has_parity:
                    logger.info(f"Area '{area_info['name']}' has ZHA parity ({len(zha_lights)} ZHA lights)")
                elif non_zha_lights:
                    logger.info(f"Area '{area_info['name']}' lacks ZHA parity ({len(zha_lights)} ZHA, {len(non_zha_lights)} non-ZHA)")
                    
            logger.info(f"Refreshed area parity cache for {len(self.area_parity_cache)} areas")
            
        except Exception as e:
            logger.error(f"Failed to refresh area parity cache: {e}")
    
    async def sync_zha_groups(self):
        """Helper method to sync ZHA groups with all areas."""
        try:
            logger.info("=" * 60)
            logger.info("Starting ZHA group sync process")
            logger.info("=" * 60)

            zigbee_controller = self.light_controller.controllers.get(Protocol.ZIGBEE)
            if zigbee_controller:
                # Sync ZHA groups with all areas (no longer limited to areas with switches)
                success, areas = await zigbee_controller.sync_zha_groups_with_areas()
                if success:
                    logger.info("ZHA group sync completed")
                    # Refresh parity cache using the areas data we already have
                    await self.refresh_area_parity_cache(areas_data=areas)
            else:
                logger.warning("ZigBee controller not available for group sync")

            logger.info("=" * 60)
            logger.info("ZHA group sync process complete")
            logger.info("=" * 60)
        except Exception as e:
            logger.error(f"Failed to sync ZHA groups: {e}")
    
    
    async def handle_message(self, message: Dict[str, Any]):
        """Handle incoming messages."""
        msg_type = message.get("type")
        
        if msg_type == "event":
            event = message.get("event", {})
            event_type = event.get("event_type", "unknown")
            event_data = event.get("data", {})
            
            logger.debug(f"Event received: {event_type}")
            
            # Log more details for call_service events
            if event_type == "call_service":
                logger.debug(f"Service called: {event_data.get('domain')}.{event_data.get('service')} with data: {event_data.get('service_data')}")
            
            # logger.debug(f"Event data: {json.dumps(event_data, indent=2)}")
            
            # Handle custom magiclight service calls
            if event_type == "call_service" and event_data.get("domain") == "magiclight":
                service = event_data.get("service")
                service_data = event_data.get("service_data", {})
                
                if service == "step_up":
                    area_id = service_data.get("area_id")
                    logger.info(f"Received magiclight.step_up service call for area: {area_id}")
                    
                    # Handle both single area (string) and multiple areas (list)
                    if area_id:
                        area_list = area_id if isinstance(area_id, list) else [area_id]
                        for area in area_list:
                            logger.info(f"Processing step_up for area: {area}")
                            await self.primitives.step_up(area, "service_call")
                    else:
                        logger.warning("step_up called without area_id")
                        
                elif service == "step_down":
                    area_id = service_data.get("area_id")
                    logger.info(f"Received magiclight.step_down service call for area: {area_id}")
                    
                    # Handle both single area (string) and multiple areas (list)
                    if area_id:
                        area_list = area_id if isinstance(area_id, list) else [area_id]
                        for area in area_list:
                            logger.info(f"Processing step_down for area: {area}")
                            await self.primitives.step_down(area, "service_call")
                    else:
                        logger.warning("step_down called without area_id")
                        
                elif service == "reset":
                    area_id = service_data.get("area_id")
                    logger.info(f"Received magiclight.reset service call for area: {area_id}")
                    
                    # Handle both single area (string) and multiple areas (list)
                    if area_id:
                        area_list = area_id if isinstance(area_id, list) else [area_id]
                        for area in area_list:
                            logger.info(f"Processing reset for area: {area}")
                            await self.primitives.reset(area, "service_call")
                    else:
                        logger.warning("reset called without area_id")

                elif service == "dim_up":
                    area_id = service_data.get("area_id")
                    logger.info(f"Received magiclight.dim_up service call for area: {area_id}")

                    if area_id:
                        area_list = area_id if isinstance(area_id, list) else [area_id]
                        for area in area_list:
                            logger.info(f"Processing dim_up for area: {area}")
                            await self.primitives.dim_up(area, "service_call")
                    else:
                        logger.warning("dim_up called without area_id")

                elif service == "dim_down":
                    area_id = service_data.get("area_id")
                    logger.info(f"Received magiclight.dim_down service call for area: {area_id}")

                    if area_id:
                        area_list = area_id if isinstance(area_id, list) else [area_id]
                        for area in area_list:
                            logger.info(f"Processing dim_down for area: {area}")
                            await self.primitives.dim_down(area, "service_call")
                    else:
                        logger.warning("dim_down called without area_id")

                elif service == "magiclight_on":
                    area_id = service_data.get("area_id")
                    logger.info(f"Received magiclight.magiclight_on service call for area: {area_id}")
                    
                    # Handle both single area (string) and multiple areas (list)
                    if area_id:
                        area_list = area_id if isinstance(area_id, list) else [area_id]
                        for area in area_list:
                            logger.info(f"Processing magiclight_on for area: {area}")
                            await self.primitives.magiclight_on(area, "service_call")
                    else:
                        logger.warning("magiclight_on called without area_id")
                        
                elif service == "magiclight_off":
                    area_id = service_data.get("area_id")
                    logger.info(f"Received magiclight.magiclight_off service call for area: {area_id}")
                    
                    # Handle both single area (string) and multiple areas (list)
                    if area_id:
                        area_list = area_id if isinstance(area_id, list) else [area_id]
                        for area in area_list:
                            logger.info(f"Processing magiclight_off for area: {area}")
                            await self.primitives.magiclight_off(area, "service_call")
                    else:
                        logger.warning("magiclight_off called without area_id")
                        
                elif service == "magiclight_toggle":
                    area_id = service_data.get("area_id")
                    logger.info(f"Received magiclight.magiclight_toggle service call for area: {area_id}")
                    
                    # Handle both single area (string) and multiple areas (list)
                    if area_id:
                        area_list = area_id if isinstance(area_id, list) else [area_id]
                        # For toggle, we need to check ALL areas together to make a single decision
                        await self.primitives.magiclight_toggle_multiple(area_list, "service_call")
                    else:
                        logger.warning("magiclight_toggle called without area_id")
            
            
            # Handle device registry updates (when devices are added/removed/modified)
            elif event_type == "device_registry_updated":
                action = event_data.get("action")
                device_id = event_data.get("device_id")

                logger.info(f"Device registry updated: action={action}, device_id={device_id}")

                # Trigger resync if a device was added, removed, or updated
                if action in ["create", "update", "remove"]:
                    await self.sync_zha_groups()  # This includes parity cache refresh
            
            # Handle area registry updates (when areas are added/removed/modified)
            elif event_type == "area_registry_updated":
                action = event_data.get("action")
                area_id = event_data.get("area_id")
                
                logger.info(f"Area registry updated: action={action}, area_id={area_id}")
                
                # Always resync on area changes
                await self.sync_zha_groups()  # This includes parity cache refresh
            
            # Handle entity registry updates (when entities change areas)
            elif event_type == "entity_registry_updated":
                action = event_data.get("action")
                entity_id = event_data.get("entity_id")
                changes = event_data.get("changes", {})
                
                # Check if area_id changed
                if "area_id" in changes:
                    old_area = changes["area_id"].get("old_value")
                    new_area = changes["area_id"].get("new_value")
                    logger.info(f"Entity {entity_id} moved from area {old_area} to {new_area}")
                    await self.sync_zha_groups()  # This includes parity cache refresh
            
            # Handle state changes
            elif event_type == "state_changed":
                entity_id = event_data.get("entity_id")
                new_state = event_data.get("new_state", {})
                old_state = event_data.get("old_state", {})
                
                # Update cached state
                if entity_id and isinstance(new_state, dict):
                    self.cached_states[entity_id] = new_state
                    
                    # Check if this is a ZHA group light entity TODO: THIS IS VERY EXHAUSTIVE
                    if entity_id.startswith("light."):
                        attributes = new_state.get("attributes", {})
                        friendly_name = attributes.get("friendly_name", "")
                        self._update_area_group_mapping(entity_id, friendly_name, attributes)
                
                # Update sun data if it's the sun entity
                if entity_id == "sun.sun" and isinstance(new_state, dict):
                    self.sun_data = new_state.get("attributes", {})
                    logger.info(f"Updated sun data: elevation={self.sun_data.get('elevation')}")
                
                
                #if isinstance(new_state, dict):
                #    logger.info(f"State changed: {entity_id} -> {new_state.get('state')}")
                #else:
                #    logger.info(f"State changed: {entity_id} -> {new_state}")
                
        elif msg_type == "result":
            success = message.get("success", False)
            msg_id = message.get("id")
            result = message.get("result")
            
            # Handle states result
            if result and isinstance(result, list) and len(result) > 0:
                first_item = result[0]
                # Check if this is states data
                if isinstance(first_item, dict) and "entity_id" in first_item:
                    # This is states data - update our cache
                    self.cached_states.clear()
                    for state in result:
                        entity_id = state.get("entity_id", "")
                        self.cached_states[entity_id] = state
                        
                        attributes = state.get("attributes", {})
                        
                        # Store initial sun data
                        if entity_id == "sun.sun":
                            self.sun_data = attributes
                            logger.info(f"Initial sun data: elevation={self.sun_data.get('elevation')}")
                        
                        # Detect ZHA group light entities (Magic_AREA pattern)
                        if entity_id.startswith("light."):
                            # Check both entity_id and friendly_name for Magic_ pattern
                            friendly_name = attributes.get("friendly_name", "")
                            
                            # Debug log all light entities
                            logger.debug(f"Light entity: {entity_id}, friendly_name: {friendly_name}")
                            
                            # Use the centralized method to update ZHA group mapping
                            self._update_area_group_mapping(entity_id, friendly_name, attributes)
                    
                    self.last_states_update = asyncio.get_event_loop().time()
                    logger.info(f"Cached {len(self.cached_states)} entity states")
                    
                    # Log ALL light entities for debugging
                    all_lights = []
                    for entity_id, state in self.cached_states.items():
                        if entity_id.startswith("light."):
                            friendly_name = state.get("attributes", {}).get("friendly_name", "")
                            all_lights.append((entity_id, friendly_name))
                    
                    if all_lights:
                        logger.info("=== All Light Entities Found ===")
                        for entity_id, name in all_lights:
                            logger.info(f"  - {entity_id}: {name}")
                        logger.info("="*40)
                    
                    # Log discovered grouped light entities
                    if self.group_entity_info:
                        logger.info("=== Discovered Grouped Light Entities ===")
                        for entity_id, info in self.group_entity_info.items():
                            group_type = info.get("type", "unknown")
                            area_label = info.get("area") or info.get("area_id") or info.get("area_name") or "unknown"
                            logger.info(f"  - {entity_id} [{group_type}] -> Area: '{area_label}'")
                        logger.info(f"Total: {len(self.group_entity_info)} grouped entities mapped to areas")
                        logger.info("=" * 50)
                    else:
                        logger.warning("No grouped light entities discovered (Magic_ ZHA or Hue rooms)")
            
            # Handle config result
            elif result and isinstance(result, dict):
                # Check if this is config data
                if "latitude" in result and "longitude" in result:
                    self.latitude = result.get("latitude")
                    self.longitude = result.get("longitude")
                    self.timezone = result.get("time_zone")
                    logger.info(f"Home Assistant location: lat={self.latitude}, lon={self.longitude}, tz={self.timezone}")
                    
                    # Set environment variables for brain.py to use as defaults
                    if self.latitude:
                        os.environ["HASS_LATITUDE"] = str(self.latitude)
                    if self.longitude:
                        os.environ["HASS_LONGITUDE"] = str(self.longitude)
                    if self.timezone:
                        os.environ["HASS_TIME_ZONE"] = self.timezone
            
            logger.debug(f"Result for message {msg_id}: {'success' if success else 'failed'}")
            
        else:
            logger.debug(f"Received message type: {msg_type}")
            
    async def send_message_wait_response(
    self,
    message: Dict[str, Any],
    *,
    full_envelope: bool = False,
) -> Optional[Dict[str, Any]]:
        if not self.websocket:
            logger.error("WebSocket not connected")
            return None

        message["id"] = self._get_next_message_id()
        msg_id = message["id"]

        try:
            await self.websocket.send(json.dumps(message))
        except Exception as e:
            logger.error(f"WebSocket send failed for id={msg_id}: {e}")
            return None

        overall_timeout = 10.0
        deadline = asyncio.get_event_loop().time() + overall_timeout
        need_event_followup = False
        is_render_template = (message.get("type") == "render_template")

        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                logger.error(f"Timeout waiting for response to message id={msg_id}")
                return None

            try:
                frame = await asyncio.wait_for(self.websocket.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                logger.error(f"Timeout waiting for response to message id={msg_id}")
                return None
            except Exception as e:
                logger.error(f"Error waiting for response to id={msg_id}: {e}")
                return None

            try:
                data = json.loads(frame)
            except Exception:
                logger.debug(f"Ignoring non-JSON frame while waiting for id={msg_id}: {frame!r}")
                continue

            # Ignore unrelated frames (e.g., other subscriptions)
            if data.get("id") != msg_id:
                continue

            # Case A: render_template sends a 'result' (often null) then an 'event' with the real value
            if is_render_template:
                if data.get("type") == "result":
                    # If success but result is null, expect an event next
                    if data.get("success", False) and data.get("result") is None:
                        need_event_followup = True
                        # don't return yet; keep looping for the event
                        continue
                    # Some HA versions may put the value here; handle normally below
                elif data.get("type") == "event":
                    # Synthesize a normal envelope from the event for caller convenience
                    event = data.get("event") or {}
                    if full_envelope:
                        return {
                            "id": msg_id,
                            "type": "result",
                            "success": True,
                            "result": {"result": event.get("result")},
                            "event": event,  # keep original if caller wants extra info
                        }
                    # legacy mode
                    return {"result": event.get("result")}

            # Case B: normal command or render_template that already included the result
            if full_envelope:
                return data

            # Legacy behavior: return only inner result on success; None otherwise
            if data.get("type") == "result" and data.get("success", False):
                return data.get("result")

            err = data.get("error")
            if err:
                logger.error(f"Error response to id={msg_id}: {err}")
                return None
    
    async def listen(self):
        """Main listener loop."""
        try:
            logger.info(f"Connecting to {self.websocket_url}")
            
            async with websockets.connect(self.websocket_url) as websocket:
                self.websocket = websocket
                
                # Authenticate
                if not await self.authenticate():
                    logger.error("Failed to authenticate")
                    return
                    
                # Initialize light controller with websocket client
                self.light_controller = MultiProtocolController(self)
                self.light_controller.add_controller(Protocol.ZIGBEE)
                self.light_controller.add_controller(Protocol.HOMEASSISTANT)
                logger.info("Initialized multi-protocol light controller")
                    
                # Get initial states to populate mappings and sun data
                logger.info("Loading initial entity states...")
                states = await self.get_states()
                
                if not states:
                    logger.error("Failed to load initial states! No states returned.")
                else:
                    logger.info(f"Successfully loaded {len(states)} entity states")
                    
                    # Count light entities
                    light_count = sum(1 for s in states if s.get("entity_id", "").startswith("light."))
                    logger.info(f"Found {light_count} light entities")
                    
                    # Process states to extract grouped light mappings
                    for state in states:
                        entity_id = state.get("entity_id", "")
                        if entity_id.startswith("light."):
                            attributes = state.get("attributes", {})
                            friendly_name = attributes.get("friendly_name", "")
                            self._update_area_group_mapping(entity_id, friendly_name, attributes)
                    
                    grouped_count = len(self.group_entity_info)
                    if grouped_count > 0:
                        logger.info(f"✓ Found {grouped_count} grouped light entities (Hue rooms or Magic ZHA groups)")
                    else:
                        logger.warning("⚠ No grouped light entities detected (no Hue rooms or Magic_ ZHA groups found)")
                
                
                # Get Home Assistant configuration (lat/lng/tz)
                config_loaded = await self.get_config()
                if not config_loaded:
                    logger.warning("⚠ Failed to load Home Assistant configuration - adaptive lighting may not work correctly")
                
                # Sync ZHA groups with all areas (includes parity cache refresh)
                await self.sync_zha_groups()

                # Ensure managed blueprint automations are in place before event processing
                if self.manage_blueprints:
                    await self.blueprint_manager.reconcile_now("startup")
                else:
                    await self.blueprint_manager.remove_blueprint_files("startup-disabled")
                    await self.blueprint_manager.purge_managed_automations("startup-disabled")

                # Subscribe to all events
                await self.subscribe_events()
                
                # Start periodic light updater
                self.periodic_update_task = asyncio.create_task(self.periodic_light_updater())
                logger.info("Started periodic light updater (runs every 60 seconds)")
                
                # Listen for messages
                logger.info("Listening for events...")
                async for message in websocket:
                    try:
                        msg = json.loads(message)
                        await self.handle_message(msg)
                    except json.JSONDecodeError:
                        logger.error(f"Failed to decode message: {message}")
                    except Exception as e:
                        logger.error(f"Error handling message: {e}")
                        
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            # Cancel periodic updater if running
            if self.periodic_update_task and not self.periodic_update_task.done():
                self.periodic_update_task.cancel()
                try:
                    await self.periodic_update_task
                except asyncio.CancelledError:
                    pass
            await self.blueprint_manager.shutdown()
            self.websocket = None
            
    async def run(self):
        """Run the client with automatic reconnection."""
        reconnect_interval = 5
        
        while True:
            try:
                await self.listen()
            except KeyboardInterrupt:
                logger.info("Interrupted by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                
            logger.info(f"Reconnecting in {reconnect_interval} seconds...")
            await asyncio.sleep(reconnect_interval)


def main():
    """Main entry point."""
    # Get configuration from environment variables
    host = os.getenv("HA_HOST", "localhost")
    port = int(os.getenv("HA_PORT", "8123"))
    token = os.getenv("HA_TOKEN")
    use_ssl = os.getenv("HA_USE_SSL", "false").lower() == "true"
    
    
    if not token:
        logger.error("HA_TOKEN environment variable is required")
        logger.info("Please set HA_TOKEN with your Home Assistant long-lived access token")
        sys.exit(1)
        
    # Create and run client
    client = HomeAssistantWebSocketClient(host, port, token, use_ssl)
    
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()
