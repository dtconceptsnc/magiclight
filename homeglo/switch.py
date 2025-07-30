#!/usr/bin/env python3
"""Switch command processing module for HomeGlo."""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import time
from brain import get_adaptive_lighting
from zoneinfo import ZoneInfo


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
        """Process a button press from a ZHA switch.
        
        Args:
            device_id: The device ID from ZHA
            command: The command (e.g., 'on_press', 'off_press', 'up_press', 'down_press')
            button: The button identifier (e.g., 'on', 'off', 'up', 'down')
        """
        # Handle different button/command combinations
        if button == "on" and command == "on_press":
            await self._handle_on_button_press(device_id)
        elif button == "off" and command == "off_press":
            await self._handle_off_button_press(device_id)
        elif button == "off" and command == "off_hold":
            await self._handle_off_button_hold(device_id)
        elif button == "off" and command == "off_release":
            await self._handle_off_button_release(device_id)
        elif button == "up" and command == "up_press":
            await self._handle_up_button_press(device_id)
        elif button == "down" and command == "down_press":
            await self._handle_down_button_press(device_id)
        else:
            logger.info(f"Unhandled button press: device={device_id}, button={button}, command={command}")
    
    async def _handle_off_button_press(self, device_id: str):
        """Handle the OFF button press - turn off lights and disable magic mode.
        
        Args:
            device_id: The device ID that triggered the event
        """
        logger.info(f"Off button pressed on ZHA device: {device_id}")
        
        # Get area for this device
        area_id = self.client.device_to_area_mapping.get(device_id)
        if not area_id:
            logger.warning(f"No area mapping found for device: {device_id}")
            return
        
        # Turn off lights and disable magic mode
        await self._turn_off_lights(area_id)
        self.client.disable_magic_mode(area_id)
            
    async def _handle_on_button_press(self, device_id: str):
        """Handle the ON button press with toggle functionality.
        
        Args:
            device_id: The device ID that triggered the event
        """
        logger.info(f"Top button (ON) pressed on ZHA device: {device_id}")
        
        # Get area for this device
        area_id = self.client.device_to_area_mapping.get(device_id)
        if not area_id:
            logger.warning(f"No area mapping found for device: {device_id}")
            logger.info(f"Known device mappings: {self.client.device_to_area_mapping}")
            return
        
        # Check if any lights are on in the area
        lights_in_area = await self.client.get_lights_in_area(area_id)
        
        # Check if any lights are on
        any_light_on = False
        for light in lights_in_area:
            if light.get("state") == "on":
                any_light_on = True
                break
        
        if any_light_on:
            # Turn off all lights in the area and disable magic mode
            await self._turn_off_lights(area_id)
            self.client.disable_magic_mode(area_id)
        else:
            # Turn on all lights with adaptive lighting and enable magic mode
            await self._turn_on_lights_adaptive(area_id)
            self.client.enable_magic_mode(area_id)
            
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
        logger.info(f"Off button HELD on ZHA device: {device_id} - Simulating time +1 hour")
        
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
        await self._set_lights_for_simulated_time(area_id)
        
    async def _handle_off_button_release(self, device_id: str):
        """Handle the OFF button release - reset time simulation.
        
        Args:
            device_id: The device ID that triggered the event
        """
        logger.info(f"Off button RELEASED on ZHA device: {device_id} - Resetting time simulation")
        
        # Reset simulated time offset
        self.simulated_time_offset = timedelta(hours=0)
        logger.info("Time simulation reset to current time")
        
        # Get area for this device
        area_id = self.client.device_to_area_mapping.get(device_id)
        if not area_id:
            logger.warning(f"No area mapping found for device: {device_id}")
            return
        
        # Set lights back to current time adaptive values
        await self._turn_on_lights_adaptive(area_id)
        
    async def _handle_up_button_press(self, device_id: str):
        """Handle the UP button press for dimming up.
        
        Args:
            device_id: The device ID that triggered the event
        """
        logger.info(f"Up button pressed on ZHA device: {device_id}")
        
        # Get area for this device
        area_id = self.client.device_to_area_mapping.get(device_id)
        if not area_id:
            logger.warning(f"No area mapping found for device: {device_id}")
            return
        
        # Increase brightness
        await self.dim_up(area_id)
        
    async def _handle_down_button_press(self, device_id: str):
        """Handle the DOWN button press for dimming down.
        
        Args:
            device_id: The device ID that triggered the event
        """
        logger.info(f"Down button pressed on ZHA device: {device_id}")
        
        # Get area for this device
        area_id = self.client.device_to_area_mapping.get(device_id)
        if not area_id:
            logger.warning(f"No area mapping found for device: {device_id}")
            return
        
        # Decrease brightness
        await self.dim_down(area_id)
        
    async def _turn_off_lights(self, area_id: str):
        """Turn off all lights in an area.
        
        Args:
            area_id: The area ID to control
        """
        logger.info(f"Turning all lights OFF in area {area_id}")
        service_data = {
            "area_id": area_id,
            "transition": 1  # 1 second transition
        }
        await self.client.call_service("light", "turn_off", service_data)
        logger.info(f"Turned off all lights in area {area_id}")
        
    async def _turn_on_lights_adaptive(self, area_id: str):
        """Turn on all lights in an area with adaptive lighting.
        
        Args:
            area_id: The area ID to control
        """
        logger.info(f"Turning lights ON with adaptive settings in area {area_id}")
        
        # Get adaptive lighting values
        if not self.client.sun_data:
            logger.warning("No sun data available for adaptive lighting")
            # Fall back to default white light
            service_data = {
                "area_id": area_id,
                "kelvin": 3500,  # Neutral white
                "brightness_pct": 80,
                "transition": 1
            }
        else:
            logger.info("=== Adaptive Lighting Calculation ===")
            logger.info(f"Sun elevation: {self.client.sun_data.get('elevation', 'N/A')}°")
            logger.info(f"Sun azimuth: {self.client.sun_data.get('azimuth', 'N/A')}°")
            logger.info(f"Next sunrise: {self.client.sun_data.get('next_rising', 'N/A')}")
            logger.info(f"Next sunset: {self.client.sun_data.get('next_setting', 'N/A')}")
            
            adaptive_values = get_adaptive_lighting()
            
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
        
        await self.client.call_service("light", "turn_on", service_data)
        logger.info(f"Turned on lights in area {area_id} with adaptive settings")
        
    async def dim_up(self, area_id: str, increment_pct: int = 17):
        """Increase brightness of all lights in an area by a percentage.
        
        Args:
            area_id: The area ID to control
            increment_pct: Percentage to increase brightness (default 17%)
        """
        logger.info(f"Increasing brightness by {increment_pct}% in area {area_id}")
        
        # Get current light states in the area
        lights_in_area = await self.client.get_lights_in_area(area_id)
        
        # Check if any lights are on
        any_light_on = False
        for light in lights_in_area:
            if light.get("state") == "on":
                any_light_on = True
                break
        
        if not any_light_on:
            logger.info(f"No lights are on in area {area_id}, turning on with default brightness")
            # Turn on lights at a low brightness if none are on
            service_data = {
                "area_id": area_id,
                "brightness_pct": increment_pct,
                "transition": 0.5
            }
        else:
            # Increase brightness of lights that are on
            # Note: Home Assistant will handle the brightness increase for all lights in the area
            service_data = {
                "area_id": area_id,
                "brightness_step_pct": increment_pct,
                "transition": 1
            }
        
        await self.client.call_service("light", "turn_on", service_data)
        logger.info(f"Brightness increased by {increment_pct}% in area {area_id}")
        
    async def dim_down(self, area_id: str, decrement_pct: int = 17):
        """Decrease brightness of all lights in an area by a percentage.
        
        Args:
            area_id: The area ID to control
            decrement_pct: Percentage to decrease brightness (default 17%)
        """
        logger.info(f"Decreasing brightness by {decrement_pct}% in area {area_id}")
        
        # Get current light states in the area
        lights_in_area = await self.client.get_lights_in_area(area_id)
        
        # Check if any lights are on
        any_light_on = False
        lights_on_count = 0
        total_brightness = 0
        
        for light in lights_in_area:
            if light.get("state") == "on":
                any_light_on = True
                lights_on_count += 1
                # Get current brightness if available
                brightness = light.get("attributes", {}).get("brightness")
                if brightness:
                    # Convert from 0-255 to percentage
                    brightness_pct = (brightness / 255) * 100
                    total_brightness += brightness_pct
        
        if not any_light_on:
            logger.info(f"No lights are on in area {area_id}, nothing to dim")
            return
        
        # Calculate average brightness
        avg_brightness = total_brightness / lights_on_count if lights_on_count > 0 else 50
        
        # If dimming would turn lights off (brightness <= decrement), turn them off instead
        if avg_brightness <= decrement_pct:
            logger.info(f"Dimming by {decrement_pct}% would turn lights off, turning off instead")
            await self._turn_off_lights(area_id)
        else:
            # Decrease brightness of lights that are on
            service_data = {
                "area_id": area_id,
                "brightness_step_pct": -decrement_pct,  # Negative value to decrease
                "transition": 0.5
            }
            
            await self.client.call_service("light", "turn_on", service_data)
            logger.info(f"Brightness decreased by {decrement_pct}% in area {area_id}")
            
    async def _set_lights_for_simulated_time(self, area_id: str) -> None:
        """
        Push the lights in *area_id* to whatever they should look like at
        (now + self.simulated_time_offset).  Uses the same adaptive-lighting
        brain as a normal ON-press so the maths can never drift.
        """
        # 1. work out the pretend “current” time -----------------------------
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
            adaptive = get_adaptive_lighting(
                current_time=simulated_time
            )
        except Exception:
            logger.exception("Adaptive-lighting calculation FAILED")
            return

        logger.info("Sun pos %.2f  |  %d K  |  %d %%",
                    adaptive["sun_position"],
                    adaptive["color_temp"],
                    adaptive["brightness"])

        # 4. hammer the lights – no fade -------------------------------------
        await self.client.call_service(
            "light", "turn_on",
            {
                "area_id": area_id,
                "kelvin": adaptive["color_temp"],
                "brightness_pct": adaptive["brightness"],
                "transition": 1,
            }
        )
        logger.info("Lights in %s set for simulated time", area_id)