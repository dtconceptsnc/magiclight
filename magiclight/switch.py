#!/usr/bin/env python3
"""Switch command processing module for MagicLight."""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import time
from zoneinfo import ZoneInfo
import random

from brain import calculate_dimming_step, DEFAULT_MAX_DIM_STEPS
from light_controller import LightCommand, Protocol


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
        # Default protocol for switches - can be overridden per switch
        self.default_protocol = Protocol.ZIGBEE
        
    async def process_button_press(self, device_id: str, command: str, button: str):
        """Process a button press from a switch.
        
        Args:
            device_id: The device ID
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
        elif button == "off" and command == "off_triple_press":
            await self._handle_off_triple_press(device_id)
        elif button == "up" and command == "up_press":
            await self._handle_up_button_press(device_id)
        elif button == "down" and command == "down_press":
            await self._handle_down_button_press(device_id)
        else:
            logger.info(f"Unhandled button press: device={device_id}, button={button}, command={command}")

    def get_protocol_for_device(self, device_id: str) -> Protocol:
        """Determine the protocol for a given device.
        
        Args:
            device_id: The device ID
            
        Returns:
            The protocol to use for this device
        """
        # In the future, this could look up device info to determine protocol
        # For now, return the default protocol
        return self.default_protocol

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
        
        # Use light controller to set random color
        if self.client.light_controller:
            command = LightCommand(
                area=area_id,
                rgb_color=(r, g, b),
                brightness=int(0.8 * 255),  # 80% brightness
                transition=0.5,
                on=True
            )
            protocol = self.get_protocol_for_device(device_id)
            await self.client.light_controller.turn_on_lights(command, protocol=protocol)
        else:
            # Fallback to direct service call
            service_data = {
                "rgb_color": [r, g, b],
                "brightness_pct": 80,
                "transition": 0.5
            }
            await self.client.call_service("light", "turn_on", service_data, {"area_id": area_id})
        
        logger.info(f"Set lights in area {area_id} to random RGB color: ({r}, {g}, {b})")
    
    async def _handle_off_button_press(self, device_id: str):
        """Handle the OFF button press - always reset to time offset 0 and enable magic mode.
        
        Args:
            device_id: The device ID that triggered the event
        """
        logger.info(f"Off button pressed on device: {device_id}")
        
        # Get area for this device
        area_id = self.client.device_to_area_mapping.get(device_id)
        if not area_id:
            logger.warning(f"No area mapping found for device: {device_id}")
            return
        
        # Check if lights are on in the area
        lights_in_area = await self.client.get_lights_in_area(area_id)
        any_light_on = any(light.get("state") == "on" for light in lights_in_area)

        # Reset time offset to 0 and enable magic mode
        logger.info(f"Resetting to time offset 0 and enabling magic mode for area {area_id}")
        
        # Reset the time offset to 0
        self.client.magic_mode_time_offsets[area_id] = 0
        
        # Enable magic mode (this also resets time offset to 0 internally)
        self.client.enable_magic_mode(area_id)
        
        # Get and apply adaptive lighting values for current time (offset 0)
        lighting_values = await self.client.get_adaptive_lighting_for_area(area_id)
        await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=1)
        logger.info(f"Magic mode enabled with time offset 0 for area {area_id}")
            
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
        lights_in_area = await self.client.get_lights_in_area(area_id)
        
        # Check if any lights are on
        any_light_on = False
        for light in lights_in_area:
            if light.get("state") == "on":
                any_light_on = True
                break
        
        if any_light_on:
            # Turn off all lights in the area and disable magic mode (no flash when turning off)
            await self._turn_off_lights(area_id, device_id)
            await self.client.disable_magic_mode(area_id, flash=False)
        else:
            # Turn on all lights with adaptive lighting and enable magic mode
            await self._turn_on_lights_adaptive(area_id, device_id)
            self.client.enable_magic_mode(area_id)  # This will reset time offset to 0
            
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
        
        # Increase brightness
        await self.dim_up(area_id, device_id)
        
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
        
        # Decrease brightness
        await self.dim_down(area_id, device_id)
        
    async def _turn_off_lights(self, area_id: str, device_id: str):
        """Turn off all lights in an area.
        
        Args:
            area_id: The area ID to control
            device_id: The device ID that triggered this action
        """
        logger.info(f"Turning all lights OFF in area {area_id}")
        
        # Use light controller if available
        if self.client.light_controller:
            command = LightCommand(
                area=area_id,
                transition=1.0,
                on=False
            )
            protocol = self.get_protocol_for_device(device_id)
            await self.client.light_controller.turn_off_lights(command, protocol=protocol)
        else:
            # Fallback to direct service call
            service_data = {"transition": 1}
            await self.client.call_service("light", "turn_off", service_data, {"area_id": area_id})
        
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
            if self.client.light_controller:
                command = LightCommand(
                    area=area_id,
                    color_temp=3500,  # Neutral white
                    brightness=int(0.8 * 255),  # 80% brightness
                    transition=1.0,
                    on=True
                )
                protocol = self.get_protocol_for_device(device_id)
                await self.client.light_controller.turn_on_lights(command, protocol=protocol)
            else:
                service_data = {
                    "kelvin": 3500,
                    "brightness_pct": 80,
                    "transition": 1
                }
                await self.client.call_service("light", "turn_on", service_data, {"area_id": area_id})
        else:
            # Use centralized method to get adaptive lighting values
            adaptive_values = await self.client.get_adaptive_lighting_for_area(area_id)
            # Use the centralized light control function
            await self.client.turn_on_lights_adaptive(area_id, adaptive_values, transition=1)
        logger.info(f"Turned on lights in area {area_id} with adaptive settings")
        
    async def dim_up(self, area_id: str, device_id: str, increment_pct: int = 17):
        """Increase brightness - in magic mode, move along the adaptive curve.
        
        Args:
            area_id: The area ID to control
            device_id: The device ID that triggered this action
            increment_pct: Percentage to increase brightness (default 17%) - used only when not in magic mode
        """
        # Check if area is in magic mode
        if area_id in self.client.magic_mode_areas:
            logger.info(f"Dimming up along magic mode curve for area {area_id}")
            
            # Get current time with offset
            current_offset = self.client.magic_mode_time_offsets.get(area_id, 0)
            current_time = datetime.now() + timedelta(minutes=current_offset)
            
            # Use the new arc-based dimming calculation
            try:
                # Get max_dim_steps from config if available
                max_steps = DEFAULT_MAX_DIM_STEPS  # Use the constant from brain.py
                if hasattr(self.client, 'config') and self.client.config:
                    max_steps = self.client.config.get('max_dim_steps', DEFAULT_MAX_DIM_STEPS)
                
                # Get curve parameters from client if available
                curve_params = {}
                if hasattr(self.client, 'curve_params'):
                    curve_params = self.client.curve_params
                
                dimming_result = calculate_dimming_step(
                    current_time=current_time,
                    action='brighten',
                    max_steps=max_steps,
                    **curve_params  # Pass the curve parameters
                )
                
                # Update the stored offset
                new_offset = current_offset + dimming_result['time_offset_minutes']
                # Limit offset to reasonable bounds (-12 hours to +12 hours)
                new_offset = max(-720, min(720, new_offset))
                self.client.magic_mode_time_offsets[area_id] = new_offset
                
                logger.info(f"Time offset for area {area_id}: {current_offset:.1f} -> {new_offset:.1f} minutes")
                
                # Apply the lighting values
                lighting_values = {
                    'kelvin': dimming_result['kelvin'],
                    'brightness': dimming_result['brightness'],
                    'rgb': dimming_result.get('rgb'),
                    'xy': dimming_result.get('xy')
                }
                
                await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=0.2)
                logger.info(f"Applied magic mode brightening: {lighting_values['kelvin']}K, {lighting_values['brightness']}%")
                
            except Exception as e:
                logger.error(f"Error calculating dimming step: {e}")
                # Fall back to simple time offset adjustment
                new_offset = current_offset + 30
                new_offset = max(-720, min(720, new_offset))
                self.client.magic_mode_time_offsets[area_id] = new_offset
                
                lighting_values = await self.client.get_adaptive_lighting_for_area(area_id)
                await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=0.2)
            
        else:
            # Not in magic mode - use standard dimming
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
                logger.info(f"No lights are on in area {area_id}, not turning on lights")
                return
            else:
                # Increase brightness of lights that are on
                if self.client.light_controller:
                    # Use brightness step command via light controller
                    # This requires getting current state and calculating new brightness
                    # For now, use direct service call for brightness stepping
                    service_data = {
                        "brightness_step_pct": increment_pct,
                        "transition": 1
                    }
                    await self.client.call_service("light", "turn_on", service_data, {"area_id": area_id})
                else:
                    service_data = {
                        "brightness_step_pct": increment_pct,
                        "transition": 1
                    }
                    await self.client.call_service("light", "turn_on", service_data, {"area_id": area_id})
                
                logger.info(f"Brightness increased by {increment_pct}% in area {area_id}")
        
    async def dim_down(self, area_id: str, device_id: str, decrement_pct: int = 17):
        """Decrease brightness - in magic mode, move along the adaptive curve.
        
        Args:
            area_id: The area ID to control
            device_id: The device ID that triggered this action
            decrement_pct: Percentage to decrease brightness (default 17%) - used only when not in magic mode
        """
        # Check if area is in magic mode
        if area_id in self.client.magic_mode_areas:
            logger.info(f"Dimming down along magic mode curve for area {area_id}")
            
            # Get current time with offset
            current_offset = self.client.magic_mode_time_offsets.get(area_id, 0)
            current_time = datetime.now() + timedelta(minutes=current_offset)
            
            # Use the new arc-based dimming calculation
            try:
                # Get max_dim_steps from config if available
                max_steps = DEFAULT_MAX_DIM_STEPS  # Use the constant from brain.py
                if hasattr(self.client, 'config') and self.client.config:
                    max_steps = self.client.config.get('max_dim_steps', DEFAULT_MAX_DIM_STEPS)
                    logger.debug(f"Using max_dim_steps from config: {max_steps}")
                else:
                    logger.debug(f"Using default max_dim_steps: {max_steps}")
                
                # Get current light brightness before dimming
                lights_in_area = await self.client.get_lights_in_area(area_id)
                current_brightness = None
                for light in lights_in_area:
                    if light.get("state") == "on":
                        brightness = light.get("attributes", {}).get("brightness")
                        if brightness:
                            current_brightness = int((brightness / 255) * 100)
                            break
                
                logger.debug(f"Current brightness before dimming: {current_brightness}%")
                logger.debug(f"Current time with offset: {current_time.isoformat()}, offset={current_offset} minutes")
                
                # Get curve parameters from client if available
                curve_params = {}
                if hasattr(self.client, 'curve_params'):
                    curve_params = self.client.curve_params
                    logger.debug(f"Using curve_params from client: {list(curve_params.keys())}")
                
                dimming_result = calculate_dimming_step(
                    current_time=current_time,
                    action='dim',
                    max_steps=max_steps,
                    **curve_params  # Pass the curve parameters
                )
                
                # Update the stored offset
                new_offset = current_offset + dimming_result['time_offset_minutes']
                # Limit offset to reasonable bounds (-12 hours to +12 hours)
                new_offset = max(-720, min(720, new_offset))
                self.client.magic_mode_time_offsets[area_id] = new_offset
                
                logger.info(f"Time offset for area {area_id}: {current_offset:.1f} -> {new_offset:.1f} minutes")
                logger.debug(f"Dimming result - brightness: {dimming_result['brightness']}%, kelvin: {dimming_result['kelvin']}K")
                logger.debug(f"Time offset change: {dimming_result['time_offset_minutes']:.1f} minutes")
                
                # Apply the lighting values
                lighting_values = {
                    'kelvin': dimming_result['kelvin'],
                    'brightness': max(1, dimming_result['brightness']),  # Ensure minimum brightness
                    'rgb': dimming_result.get('rgb'),
                    'xy': dimming_result.get('xy')
                }
                
                await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=0.2)
                logger.info(f"Applied magic mode dimming: {lighting_values['kelvin']}K, {lighting_values['brightness']}% (was {current_brightness}%)")
                
            except Exception as e:
                logger.error(f"Error calculating dimming step: {e}")
                # Fall back to simple time offset adjustment
                new_offset = current_offset - 30
                new_offset = max(-720, min(720, new_offset))
                self.client.magic_mode_time_offsets[area_id] = new_offset
                
                lighting_values = await self.client.get_adaptive_lighting_for_area(area_id)
                lighting_values = lighting_values.copy()
                lighting_values['brightness'] = max(1, lighting_values['brightness'])
                await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=0.2)
            
        else:
            # Not in magic mode - use standard dimming
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
                await self._turn_off_lights(area_id, device_id)
            else:
                # Decrease brightness of lights that are on
                if self.client.light_controller:
                    # Use brightness step command via service call for now
                    service_data = {
                        "brightness_step_pct": -decrement_pct,  # Negative value to decrease
                        "transition": 0.5
                    }
                    await self.client.call_service("light", "turn_on", service_data, {"area_id": area_id})
                else:
                    service_data = {
                        "brightness_step_pct": -decrement_pct,
                        "transition": 0.5
                    }
                    await self.client.call_service("light", "turn_on", service_data, {"area_id": area_id})
                
                logger.info(f"Brightness decreased by {decrement_pct}% in area {area_id}")
            
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