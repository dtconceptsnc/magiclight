#!/usr/bin/env python3
"""HomeGlo Primitives - Core actions that can be triggered via service calls or other means."""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from brain import calculate_dimming_step, DEFAULT_MAX_DIM_STEPS

logger = logging.getLogger(__name__)


class HomeGloPrimitives:
    """Handles all HomeGlo primitive actions/service calls."""
    
    def __init__(self, websocket_client):
        """Initialize the HomeGlo primitives handler.
        
        Args:
            websocket_client: Reference to the HomeAssistantWebSocketClient instance
        """
        self.client = websocket_client
        
    async def step_up(self, area_id: str, source: str = "service_call"):
        """Step up - Adjust TimeLocation to brighten and cool lights one step up the HomeGlo curve.
        
        Args:
            area_id: The area ID to control
            source: Source of the action (e.g., "service_call", "switch", etc.)
        """
        # Check if area is in magic mode (HomeGlo enabled)
        if area_id in self.client.magic_mode_areas:
            logger.info(f"[{source}] Stepping up along HomeGlo curve for area {area_id}")
            
            # Get current time with offset (TimeLocation)
            current_offset = self.client.magic_mode_time_offsets.get(area_id, 0)
            current_time = datetime.now() + timedelta(minutes=current_offset)
            
            try:
                # Get max_dim_steps from config if available
                max_steps = DEFAULT_MAX_DIM_STEPS
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
                    **curve_params
                )
                
                # Update the TimeLocation (stored offset)
                new_offset = current_offset + dimming_result['time_offset_minutes']
                # Limit offset to reasonable bounds (-12 hours to +12 hours)
                new_offset = max(-720, min(720, new_offset))
                self.client.magic_mode_time_offsets[area_id] = new_offset
                
                logger.info(f"TimeLocation for area {area_id}: {current_offset:.1f} -> {new_offset:.1f} minutes")
                
                # Apply the lighting values
                lighting_values = {
                    'kelvin': dimming_result['kelvin'],
                    'brightness': dimming_result['brightness'],
                    'rgb': dimming_result.get('rgb'),
                    'xy': dimming_result.get('xy')
                }
                
                await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=0.2)
                logger.info(f"Applied HomeGlo step up: {lighting_values['kelvin']}K, {lighting_values['brightness']}%")
                
            except Exception as e:
                logger.error(f"Error calculating step up: {e}")
                # Fall back to simple time offset adjustment
                new_offset = current_offset + 30
                new_offset = max(-720, min(720, new_offset))
                self.client.magic_mode_time_offsets[area_id] = new_offset
                
                lighting_values = await self.client.get_adaptive_lighting_for_area(area_id)
                await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=0.2)
            
        else:
            # Not in HomeGlo mode - use standard brightness increase
            logger.info(f"[{source}] Area {area_id} not in HomeGlo mode, using standard brightness increase")
            
            # Get current light states in the area
            lights_in_area = await self.client.get_lights_in_area(area_id)
            
            # Check if any lights are on
            any_light_on = any(light.get("state") == "on" for light in lights_in_area)
            
            if not any_light_on:
                logger.info(f"No lights are on in area {area_id}, not turning on lights")
                return
            
            # Increase brightness
            target_type, target_value = await self.client.determine_light_target(area_id)
            service_data = {
                "brightness_step_pct": 17,
                "transition": 1
            }
            target = {target_type: target_value}
            await self.client.call_service("light", "turn_on", service_data, target)
            logger.info(f"Brightness increased by 17% in area {area_id}")
        
    async def step_down(self, area_id: str, source: str = "service_call"):
        """Step down - Adjust TimeLocation to dim and warm lights one step down the HomeGlo curve.
        
        Args:
            area_id: The area ID to control
            source: Source of the action (e.g., "service_call", "switch", etc.)
        """
        # Check if area is in magic mode (HomeGlo enabled)
        if area_id in self.client.magic_mode_areas:
            logger.info(f"[{source}] Stepping down along HomeGlo curve for area {area_id}")
            
            # Get current time with offset (TimeLocation)
            current_offset = self.client.magic_mode_time_offsets.get(area_id, 0)
            current_time = datetime.now() + timedelta(minutes=current_offset)
            
            try:
                # Get max_dim_steps from config if available
                max_steps = DEFAULT_MAX_DIM_STEPS
                if hasattr(self.client, 'config') and self.client.config:
                    max_steps = self.client.config.get('max_dim_steps', DEFAULT_MAX_DIM_STEPS)
                
                # Get current light brightness before dimming
                lights_in_area = await self.client.get_lights_in_area(area_id)
                current_brightness = None
                for light in lights_in_area:
                    if light.get("state") == "on":
                        brightness = light.get("attributes", {}).get("brightness")
                        if brightness:
                            current_brightness = int((brightness / 255) * 100)
                            break
                
                logger.debug(f"Current brightness before stepping down: {current_brightness}%")
                
                # Get curve parameters from client if available
                curve_params = {}
                if hasattr(self.client, 'curve_params'):
                    curve_params = self.client.curve_params
                
                dimming_result = calculate_dimming_step(
                    current_time=current_time,
                    action='dim',
                    max_steps=max_steps,
                    **curve_params
                )
                
                # Update the TimeLocation (stored offset)
                new_offset = current_offset + dimming_result['time_offset_minutes']
                # Limit offset to reasonable bounds (-12 hours to +12 hours)
                new_offset = max(-720, min(720, new_offset))
                self.client.magic_mode_time_offsets[area_id] = new_offset
                
                logger.info(f"TimeLocation for area {area_id}: {current_offset:.1f} -> {new_offset:.1f} minutes")
                
                # Apply the lighting values
                lighting_values = {
                    'kelvin': dimming_result['kelvin'],
                    'brightness': max(1, dimming_result['brightness']),  # Ensure minimum brightness
                    'rgb': dimming_result.get('rgb'),
                    'xy': dimming_result.get('xy')
                }
                
                await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=0.2)
                logger.info(f"Applied HomeGlo step down: {lighting_values['kelvin']}K, {lighting_values['brightness']}%")
                
            except Exception as e:
                logger.error(f"Error calculating step down: {e}")
                # Fall back to simple time offset adjustment
                new_offset = current_offset - 30
                new_offset = max(-720, min(720, new_offset))
                self.client.magic_mode_time_offsets[area_id] = new_offset
                
                lighting_values = await self.client.get_adaptive_lighting_for_area(area_id)
                lighting_values = lighting_values.copy()
                lighting_values['brightness'] = max(1, lighting_values['brightness'])
                await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=0.2)
            
        else:
            # Not in HomeGlo mode - use standard brightness decrease
            logger.info(f"[{source}] Area {area_id} not in HomeGlo mode, using standard brightness decrease")
            
            # Get current light states in the area
            lights_in_area = await self.client.get_lights_in_area(area_id)
            
            # Check if any lights are on and get average brightness
            any_light_on = False
            lights_on_count = 0
            total_brightness = 0
            
            for light in lights_in_area:
                if light.get("state") == "on":
                    any_light_on = True
                    lights_on_count += 1
                    brightness = light.get("attributes", {}).get("brightness")
                    if brightness:
                        brightness_pct = (brightness / 255) * 100
                        total_brightness += brightness_pct
            
            if not any_light_on:
                logger.info(f"No lights are on in area {area_id}, nothing to dim")
                return
            
            # Calculate average brightness
            avg_brightness = total_brightness / lights_on_count if lights_on_count > 0 else 50
            
            # If dimming would turn lights off, turn them off instead
            if avg_brightness <= 17:
                logger.info(f"Dimming by 17% would turn lights off, turning off instead")
                target_type, target_value = await self.client.determine_light_target(area_id)
                service_data = {"transition": 1}
                target = {target_type: target_value}
                await self.client.call_service("light", "turn_off", service_data, target)
            else:
                # Decrease brightness
                target_type, target_value = await self.client.determine_light_target(area_id)
                service_data = {
                    "brightness_step_pct": -17,  # Negative value to decrease
                    "transition": 0.5
                }
                target = {target_type: target_value}
                await self.client.call_service("light", "turn_on", service_data, target)
                logger.info(f"Brightness decreased by 17% in area {area_id}")
    
    async def homeglo_on(self, area_id: str, source: str = "service_call"):
        """HomeGlo On - Enable HomeGlo mode and set lights to current time position.
        
        When HomeGlo is enabled:
        - The area enters "magic mode" and tracks solar time
        - Lights are automatically updated every minute based on TimeLocation
        - If there's a saved TimeLocation from when HomeGlo was last disabled, it's restored
        - Otherwise, TimeLocation starts at current time (offset = 0)
        
        Args:
            area_id: The area ID to control
            source: Source of the action
        """
        logger.info(f"[{source}] Enabling HomeGlo for area {area_id}")
        
        # Check if already enabled
        was_enabled = area_id in self.client.magic_mode_areas
        
        # Enable magic mode (sets HomeGlo = true)
        # restore_offset=True means it will restore saved TimeLocation if available
        self.client.enable_magic_mode(area_id, restore_offset=True)
        
        # Get and apply adaptive lighting values for current TimeLocation
        lighting_values = await self.client.get_adaptive_lighting_for_area(area_id)
        await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=1)
        
        if was_enabled:
            logger.info(f"HomeGlo was already enabled for area {area_id}, lights updated")
        else:
            offset = self.client.magic_mode_time_offsets.get(area_id, 0)
            logger.info(f"HomeGlo enabled for area {area_id} with TimeLocation offset {offset} minutes")
    
    async def homeglo_off(self, area_id: str, source: str = "service_call"):
        """HomeGlo Off - Disable HomeGlo mode without changing light state.
        
        When HomeGlo is disabled:
        - The area exits "magic mode" and stops tracking solar time
        - Lights remain in their current state (no change)
        - The current TimeLocation is saved for later restoration
        - Automatic minute-by-minute updates stop
        
        Args:
            area_id: The area ID to control
            source: Source of the action
        """
        logger.info(f"[{source}] Disabling HomeGlo for area {area_id} (lights unchanged)")
        
        # Check if actually enabled
        if area_id not in self.client.magic_mode_areas:
            logger.info(f"HomeGlo was already disabled for area {area_id}")
            return
        
        # Get current offset before disabling (for logging)
        current_offset = self.client.magic_mode_time_offsets.get(area_id, 0)
        
        # Disable magic mode (sets HomeGlo = false, preserves TimeLocation)
        # save_offset=True means it will save current TimeLocation for later restoration
        await self.client.disable_magic_mode(area_id, save_offset=True)
        
        logger.info(f"HomeGlo disabled for area {area_id}, TimeLocation offset {current_offset} minutes saved, lights unchanged")
    
    async def homeglo_toggle(self, area_id: str, source: str = "service_call"):
        """HomeGlo Toggle - Smart toggle based on light state.
        
        If lights are off:
        - Turn on lights with adaptive lighting
        - Enable HomeGlo mode
        
        If any lights are on:
        - Turn off all lights
        - Disable HomeGlo mode
        
        Args:
            area_id: The area ID to control
            source: Source of the action
        """
        logger.info(f"[{source}] Toggling HomeGlo for area {area_id}")
        
        # Get current light states in the area
        lights_in_area = await self.client.get_lights_in_area(area_id)
        
        # Check if any lights are on
        any_light_on = any(light.get("state") == "on" for light in lights_in_area)
        
        if any_light_on:
            # Lights are on - turn them off and disable HomeGlo
            logger.info(f"Lights are on in area {area_id}, turning off and disabling HomeGlo")
            
            # Turn off all lights
            target_type, target_value = await self.client.determine_light_target(area_id)
            service_data = {"transition": 1}
            target = {target_type: target_value}
            await self.client.call_service("light", "turn_off", service_data, target)
            
            # Disable HomeGlo mode if enabled
            if area_id in self.client.magic_mode_areas:
                await self.client.disable_magic_mode(area_id, save_offset=True)
                logger.info(f"HomeGlo disabled for area {area_id}")
            
        else:
            # Lights are off - turn them on with HomeGlo
            logger.info(f"Lights are off in area {area_id}, enabling HomeGlo and turning on")
            
            # Enable magic mode (sets HomeGlo = true)
            self.client.enable_magic_mode(area_id, restore_offset=True)
            
            # Get and apply adaptive lighting values
            lighting_values = await self.client.get_adaptive_lighting_for_area(area_id)
            await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=1)
            
            offset = self.client.magic_mode_time_offsets.get(area_id, 0)
            logger.info(f"HomeGlo enabled for area {area_id} with TimeLocation offset {offset} minutes")
    
    async def reset(self, area_id: str, source: str = "service_call"):
        """Reset - Set TimeLocation to current time (offset 0), enable HomeGlo, and unfreeze.
        
        This resets the area to track the current actual time, enables HomeGlo mode,
        and applies the appropriate lighting for the current time.
        
        Args:
            area_id: The area ID to control
            source: Source of the action
        """
        logger.info(f"[{source}] Resetting HomeGlo state for area {area_id}")
        
        # Reset time offset to 0 (sets TimeLocation to current time)
        self.client.magic_mode_time_offsets[area_id] = 0
        
        # Enable magic mode (HomeGlo = true)
        # This ensures the area will track time going forward
        self.client.enable_magic_mode(area_id)
        
        # DayHalf is automatically determined by the brain based on current solar position
        # Frozen state would be handled by separate freeze/unfreeze primitives when implemented
        
        # Get and apply adaptive lighting values for current time (offset 0)
        lighting_values = await self.client.get_adaptive_lighting_for_area(area_id)
        await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=1)
        
        logger.info(f"Reset complete: area {area_id} now tracking current time with HomeGlo enabled")
    
    # TODO: Add more primitives as we implement them:
    # - full_send (zone-wide operation)
    # - freeze/unfreeze
    # - nitelite
    # - britelite