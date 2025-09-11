#!/usr/bin/env python3
"""Switch command processing module for HomeGlo."""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import time
from zoneinfo import ZoneInfo
import random

# Light controller imports removed - using consolidated determine_light_target instead


logger = logging.getLogger(__name__)


class SwitchCommandProcessor:
    """Processes switch button commands."""
    
    def __init__(self, websocket_client):
        """Initialize the switch command processor.
        
        Args:
            websocket_client: Reference to the HomeAssistantWebSocketClient instance
        """
        self.client = websocket_client
        self.simulated_time_offset = timedelta(hours=0)  # Track time simulation offset
        self.last_off_hold_time = 0  # Track last time off_hold was processed
        
    async def process_button_press(self, device_id: str, command: str, button: str):
        """Process a button press from a switch.
        
        Args:
            device_id: The device ID
            command: The command (e.g., 'on_press', 'off_press', 'up_press', 'down_press')
            button: The button identifier (e.g., 'on', 'off', 'up', 'down')
        """
        # Handle different button/command combinations
        """if button == "on" and command == "on_press":
            await self._handle_on_button_press(device_id)
        elif button == "off" and command == "off_press":
            await self._handle_off_button_press(device_id)
        elif button == "off" and command == "off_hold":
            await self._handle_off_button_hold(device_id)
        elif button == "off" and command == "off_release":
            await self._handle_off_button_release(device_id)
        elif button == "off" and command == "off_triple_press":
            await self._handle_off_triple_press(device_id)
        elif button == "up" and command == "up_press":
            await self._handle_up_button_press(device_id)
        elif button == "down" and command == "down_press":
            await self._handle_down_button_press(device_id)
        else:
            logger.info(f"Unhandled button press: device={device_id}, button={button}, command={command}")
        """

    async def _handle_off_triple_press(self, device_id: str):
        """Handle the OFF button triple press - set random RGB color.
        
        Args:
            device_id: The device ID that triggered the event
        """
        logger.info(f"Off button TRIPLE PRESSED on device: {device_id} - Setting random RGB color!")
        
        area_id = self.client.device_to_area_mapping.get(device_id)
        if not area_id:
            logger.warning(f"No area mapping found for device: {device_id}")
            return
        
        r = random.randint(0, 255)
        g = random.randint(0, 255)
        b = random.randint(0, 255)
        
        logger.info(f"Random RGB color for area {area_id}: R={r}, G={g}, B={b}")
        
        # Disable magic mode
        await self.client.disable_magic_mode(area_id, False)
        
        # Use the consolidated logic to determine target
        target_type, target_value = await self.client.determine_light_target(area_id)
        
        service_data = {
            "rgb_color": [r, g, b],
            "brightness_pct": 80,
            "transition": 0.5
        }
        
        target = {target_type: target_value}
        await self.client.call_service("light", "turn_on", service_data, target)
        
        logger.info(f"Set lights in area {area_id} to random RGB color: ({r}, {g}, {b})")
    
    async def _handle_off_button_press(self, device_id: str):
        """Handle the OFF button press - performs a Reset operation.
        
        Args:
            device_id: The device ID that triggered the event
        """
        logger.info(f"Off button pressed on device: {device_id}")
        
        # Get area for this device
        area_id = self.client.device_to_area_mapping.get(device_id)
        if not area_id:
            logger.warning(f"No area mapping found for device: {device_id}")
            return
        
        # Delegate to the Reset primitive
        await self.client.primitives.reset(area_id, f"switch_{device_id}")
            
    async def _handle_on_button_press(self, device_id: str):
        """Handle the ON button press with toggle functionality.
        
        Args:
            device_id: The device ID that triggered the event
        """
        logger.info(f"Top button (ON) pressed on device: {device_id}")
        
        # Get area for this device
        area_id = self.client.device_to_area_mapping.get(device_id)
        if not area_id:
            logger.warning(f"No area mapping found for device: {device_id}")
            logger.info(f"Known device mappings: {self.client.device_to_area_mapping}")
            return
        
        # Check if any lights are on in the area
        any_light_on = await self.client.any_lights_on_in_area(area_id)
        
        if any_light_on:
            # Turn off all lights in the area and disable HomeGlo (saves current offset)
            await self._turn_off_lights(area_id, device_id)
            await self.client.primitives.homeglo_off(area_id, f"switch_{device_id}")
        else:
            # Turn on lights with HomeGlo enabled (restores saved offset if available)
            await self.client.primitives.homeglo_on(area_id, f"switch_{device_id}")
            
    async def _handle_off_button_hold(self, device_id: str):
        """Handle the OFF button hold - simulate time moving forward by 1 hour.
        
        Args:
            device_id: The device ID that triggered the event
        """
        # Rate limiting - only process once per second
        current_time = time.time()
        time_since_last = current_time - self.last_off_hold_time
        if time_since_last < 2.0:
            logger.info(f"Skipping off_hold command - rate limited ({time_since_last:.2f}s since last command)")
            return
        
        self.last_off_hold_time = current_time
        logger.info(f"Off button HELD on device: {device_id} - Simulating time +1 hour")
        
        # Get area for this device
        area_id = self.client.device_to_area_mapping.get(device_id)
        if not area_id:
            logger.warning(f"No area mapping found for device: {device_id}")
            return
        
        # Increment simulated time by 1 hour
        self.simulated_time_offset += timedelta(hours=1)
        total_hours = int(self.simulated_time_offset.total_seconds() / 3600)
        logger.info(f"Time simulation: +{total_hours} hour(s) from current time")
        
        # Calculate what the lighting should be at the simulated time
        await self._set_lights_for_simulated_time(area_id, device_id)
        
    async def _handle_off_button_release(self, device_id: str):
        """Handle the OFF button release - reset time simulation.
        
        Args:
            device_id: The device ID that triggered the event
        """
        logger.info(f"Off button RELEASED on device: {device_id} - Resetting time simulation")
        
        # Reset simulated time offset
        self.simulated_time_offset = timedelta(hours=0)
        logger.info("Time simulation reset to current time")
        
        # Get area for this device
        area_id = self.client.device_to_area_mapping.get(device_id)
        if not area_id:
            logger.warning(f"No area mapping found for device: {device_id}")
            return
        
        # Set lights back to current time adaptive values
        await self._turn_on_lights_adaptive(area_id, device_id)
        
    async def _handle_up_button_press(self, device_id: str):
        """Handle the UP button press for dimming up.
        
        Args:
            device_id: The device ID that triggered the event
        """
        logger.info(f"Up button pressed on device: {device_id}")
        
        # Get area for this device
        area_id = self.client.device_to_area_mapping.get(device_id)
        if not area_id:
            logger.warning(f"No area mapping found for device: {device_id}")
            return
        
        # Delegate to primitives
        await self.client.primitives.step_up(area_id, f"switch_{device_id}")
        
    async def _handle_down_button_press(self, device_id: str):
        """Handle the DOWN button press for dimming down.
        
        Args:
            device_id: The device ID that triggered the event
        """
        logger.info(f"Down button pressed on device: {device_id}")
        
        # Get area for this device
        area_id = self.client.device_to_area_mapping.get(device_id)
        if not area_id:
            logger.warning(f"No area mapping found for device: {device_id}")
            return
        
        # Delegate to primitives
        await self.client.primitives.step_down(area_id, f"switch_{device_id}")
        
    async def _turn_off_lights(self, area_id: str, device_id: str):
        """Turn off all lights in an area.
        
        Args:
            area_id: The area ID to control
            device_id: The device ID that triggered this action
        """
        logger.info(f"Turning all lights OFF in area {area_id}")
        
        # Use the consolidated logic to determine target
        target_type, target_value = await self.client.determine_light_target(area_id)
        
        # Build service data
        service_data = {"transition": 1}
        
        # Build target
        target = {target_type: target_value}
        
        # Call the service
        await self.client.call_service("light", "turn_off", service_data, target)
        
        logger.info(f"Turned off all lights in area {area_id}")
        
    async def _turn_on_lights_adaptive(self, area_id: str, device_id: str):
        """Turn on all lights in an area with adaptive lighting.
        
        Args:
            area_id: The area ID to control
            device_id: The device ID that triggered this action
        """
        logger.info(f"Turning lights ON with adaptive settings in area {area_id}")
        
        # Get adaptive lighting values
        if not self.client.sun_data:
            logger.warning("No sun data available for adaptive lighting")
            # Fall back to default white light
            # Use the consolidated logic to determine target
            target_type, target_value = await self.client.determine_light_target(area_id)
            
            service_data = {
                "kelvin": 3500,
                "brightness_pct": 80,
                "transition": 1
            }
            
            target = {target_type: target_value}
            await self.client.call_service("light", "turn_on", service_data, target)
        else:
            # Use centralized method to get adaptive lighting values
            adaptive_values = await self.client.get_adaptive_lighting_for_area(area_id)
            # Use the centralized light control function
            await self.client.turn_on_lights_adaptive(area_id, adaptive_values, transition=1)
        logger.info(f"Turned on lights in area {area_id} with adaptive settings")
            
    async def _set_lights_for_simulated_time(self, area_id: str, device_id: str) -> None:
        """
        Push the lights in *area_id* to whatever they should look like at
        (now + self.simulated_time_offset).  Uses the same adaptive-lighting
        brain as a normal ON-press so the maths can never drift.
        
        Args:
            area_id: The area to control
            device_id: The device that triggered this action
        """
        # 1. work out the pretend "current" time -----------------------------
        tzinfo = ZoneInfo(getattr(self.client, "timezone", "UTC"))
        simulated_time = (datetime.now(tzinfo) + self.simulated_time_offset)
        logger.info("Setting lights for simulated time: %s",
                    simulated_time.strftime("%H:%M:%S"))

        # 2. sanity-check lat/lon --------------------------------------------
        if not hasattr(self.client, "latitude") or not hasattr(self.client, "longitude"):
            logger.warning("Latitude/longitude missing – cannot simulate daylight")
            return

        # 3. ask the brain for colour/brightness -----------------------------
        try:
            # Use centralized method with simulated time
            adaptive = await self.client.get_adaptive_lighting_for_area(area_id, current_time=simulated_time)
        except Exception:
            logger.exception("Adaptive-lighting calculation FAILED")
            return

        # 4. hammer the lights – no fade -------------------------------------
        await self.client.turn_on_lights_adaptive(area_id, adaptive, transition=1)
        logger.info("Lights in %s set for simulated time", area_id)
