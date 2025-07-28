#!/usr/bin/env python3
"""Home Assistant WebSocket client - listens for events."""

import asyncio
import json
import logging
import os
import sys
from typing import Dict, Any, List

import websockets
from websockets.client import WebSocketClientProtocol

from switch import SwitchCommandProcessor

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
        self.switch_processor = SwitchCommandProcessor(self)  # Initialize switch processor
        self.latitude = None  # Home Assistant latitude
        self.longitude = None  # Home Assistant longitude
        self.timezone = None  # Home Assistant timezone
        
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
        
        service_msg = {
            "id": message_id,
            "type": "call_service",
            "domain": domain,
            "service": service,
            "service_data": service_data
        }
        
        await self.websocket.send(json.dumps(service_msg))
        logger.info(f"Called service: {domain}.{service} (id: {message_id})")
        
        return message_id
        
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
        
        # Get current states to find lights in the area
        message_id = self._get_next_message_id()
        
        states_msg = {
            "id": message_id,
            "type": "get_states"
        }
        
        await self.websocket.send(json.dumps(states_msg))
        
        # Wait for response (with timeout)
        timeout = 5  # seconds
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                message = await asyncio.wait_for(self.websocket.recv(), timeout=0.1)
                msg = json.loads(message)
                
                if msg.get("id") == message_id and msg.get("type") == "result":
                    result = msg.get("result", [])
                    
                    # Filter for light entities in the specified area
                    for entity in result:
                        entity_id = entity.get("entity_id", "")
                        if entity_id.startswith("light."):
                            attributes = entity.get("attributes", {})
                            # Check if entity belongs to the area
                            # Note: area_id might be in device registry, not directly in state
                            # We'll need to match via device_id if available
                            device_id = attributes.get("device_id")
                            
                            # For now, we'll get all lights and filter later
                            # In a real implementation, we'd need to cross-reference with device registry
                            lights.append({
                                "entity_id": entity_id,
                                "state": entity.get("state"),
                                "attributes": attributes
                            })
                    
                    break
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error getting lights in area: {e}")
                break
        
        # Filter lights by area using area registry
        area_lights = []
        for light in lights:
            # This is a simplified check - in production, we'd need to properly
            # cross-reference with area registry and device registry
            # For now, we'll return all lights and let the service call handle area filtering
            area_lights.append(light)
        
        return area_lights
        
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
            
            logger.info(f"Event received: {event_type}")
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
                button = args.get('button')
                
                if device_id and command and button:
                    await self.handle_zha_switch_press(device_id, command, button)
            
            # Handle state changes
            elif event_type == "state_changed":
                entity_id = event_data.get("entity_id")
                new_state = event_data.get("new_state", {})
                old_state = event_data.get("old_state", {})
                
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
                    else:
                        logger.warning("No switches found in device registry")
                
                # Check if this is states data
                elif isinstance(first_item, dict) and "entity_id" in first_item:
                    # This is states data
                    for state in result:
                        entity_id = state.get("entity_id", "")
                        attributes = state.get("attributes", {})
                        
                        # Store initial sun data
                        if entity_id == "sun.sun":
                            self.sun_data = attributes
                            logger.info(f"Initial sun data: elevation={self.sun_data.get('elevation')}")
            
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