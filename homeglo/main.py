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

from brain import get_adaptive_lighting_from_sun

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
        
    @property
    def websocket_url(self) -> str:
        """Get the WebSocket URL."""
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
        
    async def handle_zha_switch_press(self, device_id: str, command: str, button: str):
        """Handle ZHA switch button press.
        
        Args:
            device_id: The device ID from ZHA
            command: The command (e.g., 'on_press')
            button: The button identifier (e.g., 'on')
        """
        # Check if it's a top button press (button 'on' with command 'on_press')
        if button == "on" and command == "on_press":
            logger.info(f"Top button pressed on ZHA device: {device_id}")
            
            # Get area for this device
            area_id = self.device_to_area_mapping.get(device_id)
            if not area_id:
                logger.warning(f"No area mapping found for device: {device_id}")
                logger.info(f"Known device mappings: {self.device_to_area_mapping}")
                return
                
            # Get adaptive lighting values
            if not self.sun_data:
                logger.warning("No sun data available for adaptive lighting")
                return
                
            logger.info("=== Adaptive Lighting Calculation ===")
            logger.info(f"Sun elevation: {self.sun_data.get('elevation', 'N/A')}°")
            logger.info(f"Sun azimuth: {self.sun_data.get('azimuth', 'N/A')}°")
            logger.info(f"Next sunrise: {self.sun_data.get('next_rising', 'N/A')}")
            logger.info(f"Next sunset: {self.sun_data.get('next_setting', 'N/A')}")
            
            adaptive_values = get_adaptive_lighting_from_sun(self.sun_data)
            
            logger.info(f"Calculated sun position: {adaptive_values['sun_position']:.3f} (-1 to 1)")
            logger.info(f"Color temperature: {adaptive_values['color_temp']}K")
            logger.info(f"Brightness: {adaptive_values['brightness']}%")
            logger.info(f"RGB values: {adaptive_values['rgb']}")
            logger.info(f"XY coordinates: {adaptive_values['xy']}")
            logger.info("===================================")
            
            # Turn on all lights in the area with adaptive values
            service_data = {
                "area_id": area_id,
                "kelvin": adaptive_values['color_temp'],
                "brightness_pct": adaptive_values['brightness'],
                "transition": 1  # 1 second transition
            }
            
            await self.call_service("light", "turn_on", service_data)
            logger.info(f"Turned on lights in area {area_id} with adaptive settings")
    
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
                #logger.info(f"Command: {event_data.get('command')}")
                #logger.info(f"Args: {event_data.get('args')}")
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