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
        self.latitude = None  # Home Assistant latitude
        self.longitude = None  # Home Assistant longitude
        self.timezone = None  # Home Assistant timezone
        self.periodic_update_task = None  # Task for periodic light updates
        self.magic_mode_areas = set()  # Track which areas are in magic mode
        self.magic_mode_time_offsets = {}  # Track time offsets for dimming along curve
        self.cached_states = {}  # Cache of entity states
        self.last_states_update = None  # Timestamp of last states update
        
        # Color mode configuration - defaults to XY
        color_mode_str = os.getenv("COLOR_MODE", "xy")
        try:
            self.color_mode = ColorMode[color_mode_str]
        except KeyError:
            logger.warning(f"Invalid COLOR_MODE '{color_mode_str}', defaulting to XY")
            self.color_mode = ColorMode.XY
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
        
    async def call_service(self, domain: str, service: str, service_data: Dict[str, Any]) -> int:
        """Call a Home Assistant service.
        
        Args:
            domain: Service domain (e.g., 'light')
            service: Service name (e.g., 'turn_on')
            service_data: Service parameters
            
        Returns:
            Message ID of the service call
        """
        message_id = self._get_next_message_id()
        
        # If area_id is provided and we have a ZHA group entity for that area, use it instead
        if "area_id" in service_data and domain == "light":
            area_id = service_data["area_id"]
            # Try to find a ZHA group entity for this area
            light_entity = self.area_to_light_entity.get(area_id)
            if light_entity:
                logger.info(f"Using ZHA group entity {light_entity} instead of area_id {area_id}")
                # Replace area_id with entity_id
                service_data = service_data.copy()  # Don't modify original
                del service_data["area_id"]
                service_data["entity_id"] = light_entity
        
        service_msg = {
            "id": message_id,
            "type": "call_service",
            "domain": domain,
            "service": service,
            "service_data": service_data
        }

        logger.info(f"Sending service call: {domain}.{service} (id: {message_id})")
        await self.websocket.send(json.dumps(service_msg))
        logger.info(f"Called service: {domain}.{service} (id: {message_id})")
        
        return message_id
        
    async def turn_on_lights_adaptive(self, area_id: str, adaptive_values: Dict[str, Any], transition: int = 1) -> None:
        """Turn on lights with adaptive values using the configured color mode.
        
        Args:
            area_id: The area ID to control lights in
            adaptive_values: Adaptive lighting values from get_adaptive_lighting
            transition: Transition time in seconds (default 1)
        """
        # Build the base service data
        service_data = {
            "area_id": area_id,
            "brightness_pct": adaptive_values['brightness'],
            "transition": transition
        }
        
        # Add color data based on the configured color mode
        if self.color_mode == ColorMode.KELVIN:
            service_data["kelvin"] = adaptive_values['kelvin']
            logger.info(f"Turning on lights in {area_id}: {adaptive_values['kelvin']}K @ {adaptive_values['brightness']}%")
        elif self.color_mode == ColorMode.RGB:
            rgb = adaptive_values['rgb']
            service_data["rgb_color"] = rgb
            logger.info(f"Turning on lights in {area_id}: RGB({rgb[0]},{rgb[1]},{rgb[2]}) @ {adaptive_values['brightness']}%")
        elif self.color_mode == ColorMode.XY:
            xy = adaptive_values['xy']
            service_data["xy_color"] = xy
            logger.info(f"Turning on lights in {area_id}: XY({xy[0]:.4f},{xy[1]:.4f}) @ {adaptive_values['brightness']}%")
        
        await self.call_service("light", "turn_on", service_data)
        
    async def get_states(self) -> int:
        """Get all entity states.
        
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
        
    async def get_device_registry(self) -> int:
        """Get device registry information.
        
        Returns:
            Message ID of the request
        """
        message_id = self._get_next_message_id()
        
        device_msg = {
            "id": message_id,
            "type": "config/device_registry/list"
        }
        
        await self.websocket.send(json.dumps(device_msg))
        logger.info(f"Requested device registry (id: {message_id})")
        
        return message_id
        
    async def get_config(self) -> int:
        """Get Home Assistant configuration.
        
        Returns:
            Message ID of the request
        """
        message_id = self._get_next_message_id()
        
        config_msg = {
            "id": message_id,
            "type": "get_config"
        }
        
        await self.websocket.send(json.dumps(config_msg))
        logger.info(f"Requested config (id: {message_id})")
        
        return message_id
        
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
    
    def enable_magic_mode(self, area_id: str):
        """Enable magic mode for an area.
        
        Args:
            area_id: The area ID to enable magic mode for
        """
        self.magic_mode_areas.add(area_id)
        self.magic_mode_time_offsets[area_id] = 0  # Reset time offset
        logger.info(f"Magic mode enabled for area {area_id}")
    
    async def disable_magic_mode(self, area_id: str, flash: bool = True):
        """Disable magic mode for an area and optionally flash lights to indicate.
        
        Args:
            area_id: The area ID to disable magic mode for
            flash: Whether to flash lights to indicate magic mode is disabled
        """
        # Check if magic mode was actually enabled
        was_enabled = area_id in self.magic_mode_areas
        
        self.magic_mode_areas.discard(area_id)
        self.magic_mode_time_offsets.pop(area_id, None)  # Remove time offset
        
        if not was_enabled:
            logger.info(f"Magic mode already disabled for area {area_id}")
            return
            
        logger.info(f"Magic mode disabled for area {area_id}")
        
        # Flash lights to indicate magic mode is off (if requested)
        if flash:
            lights_in_area = await self.get_lights_in_area(area_id)
            any_light_on = any(light.get("state") == "on" for light in lights_in_area)
            
            if any_light_on:
                logger.info(f"Flashing lights to indicate magic mode disabled for area {area_id}")
                
                # Quick dim to 30%
                await self.call_service("light", "turn_on", {
                    "area_id": area_id,
                    "brightness_pct": 30,
                    "transition": 0.2
                })
                
                # Brief pause
                await asyncio.sleep(0.3)
                
                # Back to full brightness
                await self.call_service("light", "turn_on", {
                    "area_id": area_id,
                    "brightness_pct": 100,
                    "transition": 0.2
                })
    
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
        
        # Detect environment and set appropriate data directory
        if os.path.exists("/data"):
            # Running in Home Assistant
            data_dir = "/data"
        else:
            # Running in development - use local .data directory
            data_dir = os.path.join(os.path.dirname(__file__), ".data")
            if not os.path.exists(data_dir):
                os.makedirs(data_dir, exist_ok=True)
                logger.info(f"Development mode: using {data_dir} for configuration")
        
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
            # Extract curve parameters if present
            morning_bri_params = {}
            morning_cct_params = {}
            evening_bri_params = {}
            evening_cct_params = {}

            for key in ["mid", "steep", "decay", "gain", "offset"]:
                k = f"morning_bri_{key}"
                if k in merged_config:
                    morning_bri_params[key] = merged_config[k]
            for key in ["mid", "steep", "decay", "gain", "offset"]:
                k = f"morning_cct_{key}"
                if k in merged_config:
                    morning_cct_params[key] = merged_config[k]
            for key in ["mid", "steep", "decay", "gain", "offset"]:
                k = f"evening_bri_{key}"
                if k in merged_config:
                    evening_bri_params[key] = merged_config[k]
            for key in ["mid", "steep", "decay", "gain", "offset"]:
                k = f"evening_cct_{key}"
                if k in merged_config:
                    evening_cct_params[key] = merged_config[k]

            if morning_bri_params:
                curve_params["morning_bri_params"] = morning_bri_params
            if morning_cct_params:
                curve_params["morning_cct_params"] = morning_cct_params
            if evening_bri_params:
                curve_params["evening_bri_params"] = evening_bri_params
            if evening_cct_params:
                curve_params["evening_cct_params"] = evening_cct_params
        except Exception as e:
            logger.debug(f"Could not parse curve parameters from merged config: {e}")
        
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
            
            # Handle state changes
            elif event_type == "state_changed":
                entity_id = event_data.get("entity_id")
                new_state = event_data.get("new_state", {})
                old_state = event_data.get("old_state", {})
                
                # Update cached state
                if entity_id and isinstance(new_state, dict):
                    self.cached_states[entity_id] = new_state
                    
                    # Check if this is a ZHA group light entity
                    if entity_id.startswith("light."):
                        attributes = new_state.get("attributes", {})
                        friendly_name = attributes.get("friendly_name", "")
                        
                        if "light_" in entity_id.lower() or "light_" in friendly_name.lower():
                            area_name = None
                            
                            if "light_" in entity_id.lower():
                                parts = entity_id.lower().split("light_")
                                if len(parts) >= 2:
                                    area_name = parts[-1]
                            
                            if not area_name and "light_" in friendly_name.lower():
                                parts = friendly_name.lower().split("light_")
                                if len(parts) >= 2:
                                    area_name = parts[-1].strip()
                            
                            if area_name:
                                self.area_to_light_entity[area_name] = entity_id
                                logger.debug(f"Updated ZHA group mapping: {area_name} -> {entity_id}")
                
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
                            logger.info(f"Mapped device {device_id} ({name}, {model}) to area {area_id}")
                    
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
                        
                        # Detect ZHA group light entities (Light_AREA pattern)
                        if entity_id.startswith("light."):
                            # Check both entity_id and friendly_name for Light_ pattern
                            friendly_name = attributes.get("friendly_name", "")
                            
                            # Debug log all light entities
                            logger.debug(f"Light entity: {entity_id}, friendly_name: {friendly_name}")
                            
                            # Check if Light_ appears in either entity_id or friendly_name
                            if "light_" in entity_id.lower() or "light_" in friendly_name.lower():
                                # Try to extract area name
                                area_name = None
                                
                                # First try from entity_id
                                if "light_" in entity_id.lower():
                                    parts = entity_id.lower().split("light_")
                                    if len(parts) >= 2:
                                        area_name = parts[-1]  # Get everything after last "light_"
                                
                                # If not found, try from friendly_name
                                if not area_name and "light_" in friendly_name.lower():
                                    parts = friendly_name.lower().split("light_")
                                    if len(parts) >= 2:
                                        area_name = parts[-1].strip()
                                
                                if area_name:
                                    self.area_to_light_entity[area_name] = entity_id
                                    logger.info(f"Found ZHA group light entity: {entity_id} (name: {friendly_name}) for area: {area_name}")
                    
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
                        for area, entity in self.area_to_light_entity.items():
                            logger.info(f"  - Area: {area} -> Entity: {entity}")
                        logger.info("="*40)
                    else:
                        logger.warning("No ZHA group light entities found (looking for 'Light_' pattern)")
            
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
                    
                # Get initial states to populate mappings and sun data
                await self.get_states()
                
                # Get device registry to map devices to areas
                await self.get_device_registry()
                
                # Get Home Assistant configuration (lat/lng/tz)
                await self.get_config()
                
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
