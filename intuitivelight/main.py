#!/usr/bin/env python3
"""Home Assistant WebSocket client - listens for events."""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional

import websockets
from websockets.client import WebSocketClientProtocol

from switch import SwitchCommandProcessor
from brain import get_adaptive_lighting, ColorMode
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
        self.switch_to_area_mapping = {}  # Will be populated from HA
        self.device_to_area_mapping = {}  # Map device IDs to areas
        self.area_to_light_entity = {}  # Map areas to their ZHA group light entities
        self.switch_processor = SwitchCommandProcessor(self)  # Initialize switch processor
        self.light_controller = None  # Will be initialized after websocket connection
        self.latitude = None  # Home Assistant latitude
        self.longitude = None  # Home Assistant longitude
        self.timezone = None  # Home Assistant timezone
        self.periodic_update_task = None  # Task for periodic light updates
        self.magic_mode_areas = set()  # Track which areas are in magic mode
        self.magic_mode_time_offsets = {}  # Track time offsets for dimming along curve
        self.saved_time_offsets = {}  # Saved time offsets when lights are turned off
        self.cached_states = {}  # Cache of entity states
        self.last_states_update = None  # Timestamp of last states update
        self.area_parity_cache = {}  # Cache of area ZHA parity status
        
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
        
        # Load saved time offsets on startup
        self.load_saved_offsets()
        
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
    
    def _update_zha_group_mapping(self, entity_id: str, friendly_name: str) -> None:
        """Update the ZHA group mapping for a light entity if it matches the Glo_ pattern.
        
        Args:
            entity_id: The entity ID
            friendly_name: The friendly name of the entity
        """
        # Debug log all light entities during initial load
        if entity_id.startswith("light."):
            logger.debug(f"Checking light entity: {entity_id}, friendly_name: '{friendly_name}'")
        
        if "glo_" not in entity_id.lower() and "glo_" not in friendly_name.lower():
            return
        
        # logger.info(f"Found potential ZHA group: entity_id='{entity_id}', friendly_name='{friendly_name}'")
            
        area_name = None
        
        # Try to extract from friendly_name first (preserving case)
        if "Glo_" in friendly_name:
            parts = friendly_name.split("Glo_")
            if len(parts) >= 2:
                area_name = parts[-1].strip()
        elif "glo_" in friendly_name.lower():
            # Fallback to case-insensitive extraction
            idx = friendly_name.lower().index("glo_")
            area_name = friendly_name[idx + 4:].strip()
        
        # If not found in friendly_name, try entity_id
        if not area_name:
            if "glo_" in entity_id.lower():
                idx = entity_id.lower().index("glo_")
                area_name = entity_id[idx + 4:]
                # Remove "light." prefix if it leaked in
                area_name = area_name.replace("light.", "")
        
        if area_name:
            # Store multiple variations for flexible matching:
            # 1. Exact area name as extracted
            self.area_to_light_entity[area_name] = entity_id
            # 2. Lowercase version
            self.area_to_light_entity[area_name.lower()] = entity_id
            # 3. With underscores replaced by spaces (common HA pattern)
            area_with_spaces = area_name.replace("_", " ")
            self.area_to_light_entity[area_with_spaces] = entity_id
            self.area_to_light_entity[area_with_spaces.lower()] = entity_id
            # 4. With spaces replaced by underscores (another common pattern)
            area_with_underscores = area_name.replace(" ", "_")
            self.area_to_light_entity[area_with_underscores] = entity_id
            self.area_to_light_entity[area_with_underscores.lower()] = entity_id
            
            # logger.info(f"Mapped ZHA group '{entity_id}' (name: {friendly_name}) to area variations: {area_name}, {area_name.lower()}, {area_with_spaces}, {area_with_underscores}")
        
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

        logger.info(f"Sending service call: {domain}.{service} (id: {message_id})")
        await self.websocket.send(json.dumps(service_msg))
        logger.info(f"Called service: {domain}.{service} (id: {message_id})")
        
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
        # Check if we have a ZHA group entity for this area
        light_entity = self.area_to_light_entity.get(area_id) or \
                      self.area_to_light_entity.get(area_id.lower())
        
        # Check cached parity status
        has_parity = self.area_parity_cache.get(area_id, False)
        
        # If we have a ZHA group entity and parity, use the group
        if light_entity and has_parity:
            logger.info(f"✓ Using ZHA group entity '{light_entity}' for area '{area_id}' (all lights are ZHA)")
            return "entity_id", light_entity
        elif light_entity and not has_parity:
            logger.info(f"⚠ Area '{area_id}' has non-ZHA lights, using area-based control for full coverage")
        
        # Default to area-based control
        logger.info(f"Using area-based control for area '{area_id}'")
        return "area_id", area_id
    
    async def turn_on_lights_adaptive(self, area_id: str, adaptive_values: Dict[str, Any], transition: int = 1) -> None:
        """Turn on lights with adaptive values using the light controller.
        
        Args:
            area_id: The area ID to control lights in
            adaptive_values: Adaptive lighting values from get_adaptive_lighting
            transition: Transition time in seconds (default 1)
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
        if self.color_mode == ColorMode.KELVIN and 'kelvin' in adaptive_values:
            service_data["kelvin"] = adaptive_values['kelvin']
        elif self.color_mode == ColorMode.RGB and 'rgb' in adaptive_values:
            service_data["rgb_color"] = adaptive_values['rgb']
        elif self.color_mode == ColorMode.XY and 'xy' in adaptive_values:
            service_data["xy_color"] = adaptive_values['xy']
        
        # Build target
        target = {target_type: target_value}
        
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
        
    async def get_device_registry(self) -> Dict[str, str]:
        """Get device registry information and wait for switches to be mapped.
        
        Returns:
            Dictionary mapping device IDs to area IDs for switches
        """
        result = await self.send_message_wait_response({"type": "config/device_registry/list"})
        
        if result and isinstance(result, list):
            # Process device registry to find switches
            for device in result:
                device_id = device.get("id")
                area_id = device.get("area_id")
                name = (device.get("name_by_user") or "")
                model = device.get("model", "")
                
                if device_id and area_id and "switch" in name.lower():
                    self.device_to_area_mapping[device_id] = area_id
                    logger.info(f"Mapped device {device_id} ({name}, {model}) to area {area_id}")
            
            # Log summary of discovered switches
            if self.device_to_area_mapping:
                logger.info("=== Discovered Switches ===")
                logger.info(f"Found {len(self.device_to_area_mapping)} switches:")
                for dev_id, area in self.device_to_area_mapping.items():
                    logger.info(f"  - Device ID: {dev_id} -> Area: {area}")
                logger.info("=========================")
                
                areas_with_switches = set(self.device_to_area_mapping.values())
                logger.info(f"Found {len(areas_with_switches)} areas with switches")
            else:
                logger.warning("No switches found in device registry")
        
        return self.device_to_area_mapping
        
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
        
    async def get_lights_in_area(self, area_id: str) -> List[Dict[str, Any]]:
        """Get all light entities in a specific area with their current states.
        
        Args:
            area_id: The area ID to query
            
        Returns:
            List of light entities with their states
        """
        lights = []
        
        # First check if we have a ZHA group entity for this area
        light_entity_id = self.area_to_light_entity.get(area_id)
        if light_entity_id:
            # Use cached state if available
            if light_entity_id in self.cached_states:
                entity = self.cached_states[light_entity_id]
                logger.debug(f"Using cached ZHA group entity state for {light_entity_id}")
                return [{
                    "entity_id": light_entity_id,
                    "state": entity.get("state"),
                    "attributes": entity.get("attributes", {})
                }]
        
        # Fallback to getting all states if no ZHA group entity
        # Get current states
        message_id = self._get_next_message_id()
        states_msg = {
            "id": message_id,
            "type": "get_states"
        }
        
        await self.websocket.send(json.dumps(states_msg))
        
        # Wait for response
        timeout = 5  # seconds
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                message = await asyncio.wait_for(self.websocket.recv(), timeout=0.1)
                msg = json.loads(message)
                
                if msg.get("id") == message_id and msg.get("type") == "result":
                    result = msg.get("result", [])
                    
                    # If we have a ZHA group entity, only return that
                    if light_entity_id:
                        for entity in result:
                            if entity.get("entity_id") == light_entity_id:
                                return [{
                                    "entity_id": light_entity_id,
                                    "state": entity.get("state"),
                                    "attributes": entity.get("attributes", {})
                                }]
                    
                    # Otherwise get all light entities (fallback behavior)
                    for entity in result:
                        entity_id = entity.get("entity_id", "")
                        if entity_id.startswith("light."):
                            lights.append({
                                "entity_id": entity_id,
                                "state": entity.get("state"),
                                "attributes": entity.get("attributes", {})
                            })
                    
                    break
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error getting light states: {e}")
                break
        
        return lights
        
    async def get_areas_with_switches(self) -> List[str]:
        """Get all areas that have devices with 'Switch' in the friendly name.
        
        Returns:
            List of area IDs
        """
        areas_with_switches = set()
        
        # Get all areas from device mapping
        for device_id, area_id in self.device_to_area_mapping.items():
            if area_id:
                areas_with_switches.add(area_id)
        
        return list(areas_with_switches)
    
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
    
    def load_saved_offsets(self):
        """Load saved time offsets from disk."""
        try:
            data_dir = self._get_data_directory()
            offsets_file = os.path.join(data_dir, "saved_offsets.json")
            if os.path.exists(offsets_file):
                with open(offsets_file, 'r') as f:
                    self.saved_time_offsets = json.load(f)
                    logger.info(f"Loaded saved time offsets: {self.saved_time_offsets}")
            else:
                logger.info("No saved time offsets found")
        except Exception as e:
            logger.warning(f"Failed to load saved time offsets: {e}")
            
    def save_offsets(self):
        """Save time offsets to disk."""
        try:
            data_dir = self._get_data_directory()
            offsets_file = os.path.join(data_dir, "saved_offsets.json")
            with open(offsets_file, 'w') as f:
                json.dump(self.saved_time_offsets, f)
                logger.debug(f"Saved time offsets: {self.saved_time_offsets}")
        except Exception as e:
            logger.warning(f"Failed to save time offsets: {e}")
    
    def enable_magic_mode(self, area_id: str, restore_offset: bool = False):
        """Enable magic mode for an area.
        
        Args:
            area_id: The area ID to enable magic mode for
            restore_offset: Whether to restore saved time offset if available
        """
        self.magic_mode_areas.add(area_id)
        
        # Restore saved offset if available, otherwise reset to 0
        if restore_offset and area_id in self.saved_time_offsets:
            self.magic_mode_time_offsets[area_id] = self.saved_time_offsets[area_id]
            logger.info(f"Magic mode enabled for area {area_id}, restored offset: {self.saved_time_offsets[area_id]} minutes")
        else:
            self.magic_mode_time_offsets[area_id] = 0  # Reset time offset
            logger.info(f"Magic mode enabled for area {area_id}, offset reset to 0")
    
    async def disable_magic_mode(self, area_id: str, save_offset: bool = True):
        """Disable magic mode for an area.
        
        Args:
            area_id: The area ID to disable magic mode for
            save_offset: Whether to save the current time offset for later restoration
        """
        # Check if magic mode was actually enabled
        was_enabled = area_id in self.magic_mode_areas
        
        # Save the current offset before removing it
        if save_offset and area_id in self.magic_mode_time_offsets:
            self.saved_time_offsets[area_id] = self.magic_mode_time_offsets[area_id]
            logger.info(f"Saved time offset for area {area_id}: {self.saved_time_offsets[area_id]} minutes")
            self.save_offsets()  # Persist to disk
        
        self.magic_mode_areas.discard(area_id)
        self.magic_mode_time_offsets.pop(area_id, None)  # Remove time offset
        
        if not was_enabled:
            logger.info(f"Magic mode already disabled for area {area_id}")
            return
            
        logger.info(f"Magic mode disabled for area {area_id}")
    
    async def get_adaptive_lighting_for_area(self, area_id: str, current_time: Optional[datetime] = None, apply_time_offset: bool = True) -> Dict[str, Any]:
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

        # Keep merged config available to other components (e.g., switch)
        try:
            self.config = merged_config
        except Exception:
            pass

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
        
        # Store curve parameters for use in switch dimming calculations
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
            
            # Reset all area offsets
            areas_with_offsets = list(self.magic_mode_time_offsets.keys())
            for area_id in areas_with_offsets:
                old_offset = self.magic_mode_time_offsets.get(area_id, 0)
                if old_offset != 0:
                    logger.info(f"Resetting offset for area {area_id}: {old_offset} -> 0 minutes")
                    self.magic_mode_time_offsets[area_id] = 0
                    
                    # Update lights in this area if it's in magic mode
                    if area_id in self.magic_mode_areas:
                        await self.update_lights_in_magic_mode(area_id)
            
            return now
        elif now.date() != last_check.date():
            # New day - update last check
            return now
            
        return last_check
    
    async def periodic_light_updater(self):
        """Periodically update lights in areas with switches."""
        last_solar_midnight_check = None
        
        while True:
            try:
                # Wait for 60 seconds
                await asyncio.sleep(60)
                
                # Check if we should reset offsets at solar midnight
                last_solar_midnight_check = await self.reset_offsets_at_solar_midnight(last_solar_midnight_check)
                
                # Get all areas with switches
                areas = await self.get_areas_with_switches()
                
                if not areas:
                    logger.debug("No areas with switches found for periodic update")
                    continue
                
                logger.info(f"Running periodic light update for {len(areas)} areas with switches")
                
                # Update lights only in areas that are in magic mode
                for area_id in areas:
                    if area_id in self.magic_mode_areas:
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
                
                # Skip the Glo_Zigbee_Groups area - it's just for organizing group entities
                if area_name == 'Glo_Zigbee_Groups':
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
    
    async def sync_zha_groups(self, refresh_devices: bool = True):
        """Helper method to sync ZHA groups with areas.
        
        Args:
            refresh_devices: Whether to refresh the device registry first (default True).
                            Set to False during startup when registry was just loaded.
        """
        try:
            logger.info("=" * 60)
            logger.info("Starting ZHA group sync process")
            logger.info("=" * 60)
            
            # Refresh device registry first (unless already done)
            if refresh_devices:
                await self.get_device_registry()
            
            zigbee_controller = self.light_controller.controllers.get(Protocol.ZIGBEE)
            if zigbee_controller:
                areas_with_switches = set(self.device_to_area_mapping.values())
                if areas_with_switches:
                    logger.info(f"Found {len(areas_with_switches)} areas with switches")
                    success, areas = await zigbee_controller.sync_zha_groups_with_areas(areas_with_switches)
                    if success:
                        logger.info("ZHA group sync completed")
                        # Refresh parity cache using the areas data we already have
                        await self.refresh_area_parity_cache(areas_data=areas)
                else:
                    logger.warning("No areas with switches found")
            else:
                logger.warning("ZigBee controller not available for group sync")
            
            logger.info("=" * 60)
            logger.info("ZHA group sync process complete")
            logger.info("=" * 60)
        except Exception as e:
            logger.error(f"Failed to sync ZHA groups: {e}")
    
    async def handle_zha_switch_press(self, device_id: str, command: str, button: str):
        """Handle ZHA switch button press.
        
        Args:
            device_id: The device ID from ZHA
            command: The command (e.g., 'on_press')
            button: The button identifier (e.g., 'on')
        """
        # Delegate to switch processor
        await self.switch_processor.process_button_press(device_id, command, button)
    
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
                logger.info(f"Service called: {event_data.get('domain')}.{event_data.get('service')} with data: {event_data.get('service_data')}")
            
            logger.debug(f"Event data: {json.dumps(event_data, indent=2)}")
            
            # Handle ZHA events
            if event_type == "zha_event":
                #logger.info("=== ZHA Event Received ===")
                #logger.info(f"Device ID: {event_data.get('device_id')}")
                #logger.info(f"Device IEEE: {event_data.get('device_ieee')}")
                #logger.info(f"Unique ID: {event_data.get('unique_id')}")
                #logger.info(f"Endpoint ID: {event_data.get('endpoint_id')}")
                #logger.info(f"Cluster ID: {event_data.get('cluster_id')}")
                logger.info(f"Command: {event_data.get('command')}")
                logger.info(f"Args: {event_data.get('args')}")
                #logger.info(f"Params: {event_data.get('params')}")
                #logger.info(f"Full ZHA data: {json.dumps(event_data, indent=2)}")
                logger.info("========================")
                
                # Handle switch button presses
                device_id = event_data.get('device_id')
                command = event_data.get('command')
                args = event_data.get('args', {})
                
                # Skip raw "step" commands - we'll handle the processed button events instead
                if command == "step":
                    logger.info(f"Ignoring raw step command from device {device_id}")
                    return
                
                # Check if args is a dict before trying to get button
                button = None
                if isinstance(args, dict):
                    button = args.get('button')
                
                if device_id and command and button:
                    await self.handle_zha_switch_press(device_id, command, button)
            
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
                        self._update_zha_group_mapping(entity_id, friendly_name)
                
                # Update sun data if it's the sun entity
                if entity_id == "sun.sun" and isinstance(new_state, dict):
                    self.sun_data = new_state.get("attributes", {})
                    logger.info(f"Updated sun data: elevation={self.sun_data.get('elevation')}")
                
                # Handle switch button presses - look for entities with "Switch" label
                if isinstance(new_state, dict):
                    attributes = new_state.get("attributes", {})
                    friendly_name = attributes.get("name_by_user", "")
                    
                    if "Switch" in friendly_name:
                        new_state_value = new_state.get("state")
                        old_state_value = old_state.get("state") if old_state and isinstance(old_state, dict) else None
                        
                        # Detect button press (state change to a press state)
                        if new_state_value in ["on_press", "initial_press"] and old_state_value != new_state_value:
                            logger.info(f"Switch button press detected via state change: {entity_id} -> {new_state_value}")
                
                #if isinstance(new_state, dict):
                #    logger.info(f"State changed: {entity_id} -> {new_state.get('state')}")
                #else:
                #    logger.info(f"State changed: {entity_id} -> {new_state}")
                
        elif msg_type == "result":
            success = message.get("success", False)
            msg_id = message.get("id")
            result = message.get("result")
            
            # Handle device registry result
            if result and isinstance(result, list) and len(result) > 0:
                # Check if this is device registry data
                first_item = result[0]
                if isinstance(first_item, dict) and "id" in first_item and "area_id" in first_item:
                    # This is device registry data
                    for device in result:
                        #logger.info(f"{device}")
                        device_id = device.get("id")
                        area_id = device.get("area_id")
                        name = (device.get("name_by_user") or "")
                        model = device.get("model", "")
                        
                        if device_id and area_id and "switch" in name.lower():
                            self.device_to_area_mapping[device_id] = area_id
                            logger.info(f"Mapped switch device {device_id} ({name}, {model}) to area '{area_id}'")
                    
                    # Log summary of discovered switches
                    if self.device_to_area_mapping:
                        logger.info("=== Discovered Switches ===")
                        logger.info(f"Found {len(self.device_to_area_mapping)} switches:")
                        for dev_id, area in self.device_to_area_mapping.items():
                            logger.info(f"  - Device ID: {dev_id} -> Area: {area}")
                        logger.info("=========================")
                        
                        # Don't automatically enable magic mode - let it be controlled by switch presses
                        areas_with_switches = set(self.device_to_area_mapping.values())
                        logger.info(f"Found {len(areas_with_switches)} areas with switches")
                        
                        # Note: Parity checking now happens dynamically in turn_on_lights_adaptive
                        logger.info("=== Switch -> Light Control Method ===")
                        logger.info(f"Areas with switches will use either ZHA group (if all lights are ZHA)")
                        logger.info(f"or area-based control (if any non-ZHA lights present)")
                        logger.info("="*50)
                    else:
                        logger.warning("No switches found in device registry")
                
                # Check if this is states data
                elif isinstance(first_item, dict) and "entity_id" in first_item:
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
                        
                        # Detect ZHA group light entities (Glo_AREA pattern)
                        if entity_id.startswith("light."):
                            # Check both entity_id and friendly_name for Glo_ pattern
                            friendly_name = attributes.get("friendly_name", "")
                            
                            # Debug log all light entities
                            logger.debug(f"Light entity: {entity_id}, friendly_name: {friendly_name}")
                            
                            # Use the centralized method to update ZHA group mapping
                            self._update_zha_group_mapping(entity_id, friendly_name)
                    
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
                    
                    # Log discovered ZHA group entities
                    if self.area_to_light_entity:
                        logger.info("=== Discovered ZHA Group Light Entities ===")
                        # Get unique entity mappings (since we store multiple area variations)
                        unique_entities = {}
                        for area, entity in self.area_to_light_entity.items():
                            if entity not in unique_entities:
                                unique_entities[entity] = []
                            unique_entities[entity].append(area)
                        
                        for entity, areas in unique_entities.items():
                            # Show primary area name (first non-lowercase one)
                            primary_area = next((a for a in areas if not a.islower()), areas[0])
                            logger.info(f"  - ZHA Group: {entity} -> Area: '{primary_area}' (+ {len(areas)-1} variations)")
                        
                        logger.info(f"Total: {len(unique_entities)} ZHA groups mapped to areas")
                        logger.info("="*50)
                    else:
                        logger.warning("No ZHA group light entities found (looking for 'Glo_' pattern)")
            
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
            
            logger.info(f"Result for message {msg_id}: {'success' if success else 'failed'}")
            
        else:
            logger.debug(f"Received message type: {msg_type}")
            
    async def send_message_wait_response(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send a message and wait for its specific response.
        
        Args:
            message: The message to send (without id)
            
        Returns:
            The result from the response, or None if failed
        """
        if not self.websocket:
            logger.error("WebSocket not connected")
            return None
            
        # Add message ID
        message["id"] = self._get_next_message_id()
        msg_id = message["id"]
        
        # Send the message
        await self.websocket.send(json.dumps(message))
        
        # Wait for response with timeout
        timeout = 10  # seconds
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                response = await asyncio.wait_for(self.websocket.recv(), timeout=1.0)
                data = json.loads(response)
                
                if data.get("id") == msg_id:
                    if data["type"] == "result":
                        return data.get("result")
                    elif data.get("error"):
                        logger.error(f"Error response: {data['error']}")
                        return None
                        
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error waiting for response: {e}")
                return None
                
        logger.error(f"Timeout waiting for response to message {msg_id}")
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
                    
                    # Process states to extract ZHA group mappings
                    for state in states:
                        entity_id = state.get("entity_id", "")
                        if entity_id.startswith("light."):
                            attributes = state.get("attributes", {})
                            friendly_name = attributes.get("friendly_name", "")
                            self._update_zha_group_mapping(entity_id, friendly_name)
                    
                    unique_groups = len(set(self.area_to_light_entity.values()))
                    if unique_groups > 0:
                        logger.info(f"✓ Found {unique_groups} ZHA groups")
                    else:
                        logger.warning("⚠ No ZHA groups found (looking for 'Glo_' pattern in light names)")
                
                # Get device registry to map devices to areas (now waits for completion)
                device_mapping = await self.get_device_registry()
                
                # Get Home Assistant configuration (lat/lng/tz)
                config_loaded = await self.get_config()
                if not config_loaded:
                    logger.warning("⚠ Failed to load Home Assistant configuration - adaptive lighting may not work correctly")
                
                # Sync ZHA groups with areas that have switches (includes parity cache refresh)
                # Don't refresh devices since we just loaded them
                await self.sync_zha_groups(refresh_devices=False)
                
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
