#!/usr/bin/env python3
"""MagicLight Primitives - Core actions that can be triggered via service calls or other means."""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from brain import calculate_dimming_step, DEFAULT_MAX_DIM_STEPS

logger = logging.getLogger(__name__)


class MagicLightPrimitives:
    """Handles all MagicLight primitive actions/service calls."""
    
    def __init__(self, websocket_client):
        """Initialize the MagicLight primitives handler.
        
        Args:
            websocket_client: Reference to the HomeAssistantWebSocketClient instance
        """
        self.client = websocket_client
        
    async def step_up(self, area_id: str, source: str = "service_call"):
        """Step up - Adjust TimeLocation to brighten and cool lights one step up the MagicLight curve.
        
        Args:
            area_id: The area ID to control
            source: Source of the action (e.g., "service_call", "switch", etc.)
        """
        # Check if area is in magic mode (HomeGlo enabled)
        if area_id in self.client.magic_mode_areas:
            logger.info(f"[{source}] Stepping up along MagicLight curve for area {area_id}")
            
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

                # Get dynamic min/max values from curve_params
                max_brightness = curve_params.get('max_brightness', 100)
                max_kelvin = curve_params.get('max_color_temp', 6500)

                # Check if this would put us at maximum values (stuck on plateau)
                # If brightening result is already at maximum, don't apply the offset change
                if dimming_result['brightness'] >= max_brightness and dimming_result['kelvin'] >= max_kelvin:
                    logger.info(f"Step up would reach maximum plateau ({max_brightness}%, {max_kelvin}K) - stopping at current offset {current_offset:.1f} minutes")
                    # Don't change the offset, just return current state
                    lighting_values = await self.client.get_adaptive_lighting_for_area(area_id)
                    await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=0.2)
                    return

                # Update the TimeLocation (stored offset)
                new_offset = current_offset + dimming_result['time_offset_minutes']
                # Limit offset to reasonable bounds (-6 hours to +18 hours from solar noon)
                # This keeps us within meaningful parts of the solar day curve
                new_offset = max(-360, min(1080, new_offset))
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
                logger.info(f"Applied MagicLight step up: {lighting_values['kelvin']}K, {lighting_values['brightness']}%")
                
            except Exception as e:
                logger.error(f"Error calculating step up: {e}")
                # Fall back to simple time offset adjustment
                new_offset = current_offset + 30
                new_offset = max(-720, min(720, new_offset))
                self.client.magic_mode_time_offsets[area_id] = new_offset
                
                lighting_values = await self.client.get_adaptive_lighting_for_area(area_id)
                await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=0.2)
            
        else:
            # Not in MagicLight mode - use standard brightness increase
            logger.info(f"[{source}] Area {area_id} not in MagicLight mode, using standard brightness increase")
            
            # Check if any lights are on
            any_light_on = await self.client.any_lights_on_in_area(area_id)
            
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
        """Step down - Adjust TimeLocation to dim and warm lights one step down the MagicLight curve.
        
        Args:
            area_id: The area ID to control
            source: Source of the action (e.g., "service_call", "switch", etc.)
        """
        # Check if area is in magic mode (HomeGlo enabled)
        if area_id in self.client.magic_mode_areas:
            logger.info(f"[{source}] Stepping down along MagicLight curve for area {area_id}")
            
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
                    action='dim',
                    max_steps=max_steps,
                    **curve_params
                )

                # Get dynamic min/max values from curve_params
                min_brightness = curve_params.get('min_brightness', 1)
                min_kelvin = curve_params.get('min_color_temp', 500)

                # Check if this would put us at minimum values (stuck on plateau)
                # If dimming result is already at minimum, don't apply the offset change
                if dimming_result['brightness'] <= min_brightness and dimming_result['kelvin'] <= min_kelvin:
                    logger.info(f"Step down would reach minimum plateau ({min_brightness}%, {min_kelvin}K) - stopping at current offset {current_offset:.1f} minutes")
                    # Don't change the offset, just return current state
                    lighting_values = await self.client.get_adaptive_lighting_for_area(area_id)
                    await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=0.2)
                    return

                # Update the TimeLocation (stored offset)
                new_offset = current_offset + dimming_result['time_offset_minutes']
                # Limit offset to reasonable bounds (-6 hours to +18 hours from solar noon)
                # This keeps us within meaningful parts of the solar day curve
                new_offset = max(-360, min(1080, new_offset))
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
                logger.info(f"Applied MagicLight step down: {lighting_values['kelvin']}K, {lighting_values['brightness']}%")
                
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
            # Not in MagicLight mode - use standard brightness decrease
            logger.info(f"[{source}] Area {area_id} not in MagicLight mode, using standard brightness decrease")
            
            # Check if any lights are on
            any_light_on = await self.client.any_lights_on_in_area(area_id)
            
            if not any_light_on:
                logger.info(f"No lights are on in area {area_id}, nothing to dim")
                return
            
            # Just decrease brightness by 17% - Home Assistant handles minimum brightness
            target_type, target_value = await self.client.determine_light_target(area_id)
            service_data = {
                "brightness_step_pct": -17,  # Negative value to decrease
                "transition": 0.5
            }
            target = {target_type: target_value}
            await self.client.call_service("light", "turn_on", service_data, target)
            logger.info(f"Brightness decreased by 17% in area {area_id}")
    
    async def magiclight_on(self, area_id: str, source: str = "service_call"):
        """MagicLight On - Enable MagicLight mode and set lights to current time position.
        
        When MagicLight is enabled:
        - The area enters "magic mode" and tracks solar time
        - Lights are automatically updated every minute based on TimeLocation
        - If there's a recall TimeLocation from when MagicLight was last disabled, it's restored
        - Otherwise, TimeLocation starts at current time (offset = 0)
        
        Args:
            area_id: The area ID to control
            source: Source of the action
        """
        logger.info(f"[{source}] Enabling MagicLight for area {area_id}")
        
        # Check if already enabled
        was_enabled = area_id in self.client.magic_mode_areas

        if was_enabled:
            # MagicLight already enabled - don't change lights, just ensure it stays enabled
            self.client.enable_magic_mode(area_id, restore_offset=False)
            logger.info(f"MagicLight was already enabled for area {area_id}, no changes made")
        else:
            # MagicLight was disabled - enable it and restore saved offset if available
            self.client.enable_magic_mode(area_id, restore_offset=True)

            # Get and apply adaptive lighting values for current TimeLocation
            lighting_values = await self.client.get_adaptive_lighting_for_area(area_id)
            await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=1)

            offset = self.client.magic_mode_time_offsets.get(area_id, 0)
            logger.info(f"MagicLight enabled for area {area_id} with TimeLocation offset {offset} minutes")
    
    async def magiclight_off(self, area_id: str, source: str = "service_call"):
        """MagicLight Off - Disable MagicLight mode without changing light state.
        
        When MagicLight is disabled:
        - The area exits "magic mode" and stops tracking solar time
        - Lights remain in their current state (no change)
        - The current TimeLocation is saved as recall offset for later restoration
        - Automatic minute-by-minute updates stop
        
        Args:
            area_id: The area ID to control
            source: Source of the action
        """
        logger.info(f"[{source}] Disabling MagicLight for area {area_id} (lights unchanged)")
        
        # Check if actually enabled
        if area_id not in self.client.magic_mode_areas:
            logger.info(f"MagicLight was already disabled for area {area_id}")
            return
        
        # Get current offset before disabling (for logging)
        current_offset = self.client.magic_mode_time_offsets.get(area_id, 0)
        
        # Disable magic mode (sets MagicLight = false, preserves TimeLocation)
        # save_offset=True means it will save current TimeLocation for later restoration
        await self.client.disable_magic_mode(area_id, save_offset=True)
        
        logger.info(f"MagicLight disabled for area {area_id}, TimeLocation offset {current_offset} minutes saved, lights unchanged")
    
    async def magiclight_toggle_multiple(self, area_ids: list, source: str = "service_call"):
        """MagicLight Toggle for multiple areas - Smart toggle based on combined light state.
        
        If ANY lights are on in ANY area:
        - Turn off all lights in all areas
        - Disable MagicLight mode in all areas
        
        If ALL lights are off in ALL areas:
        - Turn on lights with adaptive lighting in all areas
        - Enable MagicLight mode in all areas
        
        Args:
            area_ids: List of area IDs to control as a group
            source: Source of the action
        """
        # Convert single area to list for consistency
        if isinstance(area_ids, str):
            area_ids = [area_ids]
        
        logger.info(f"[{source}] Toggle called for areas: {area_ids}")
        
        # Check if ANY lights are on in ANY of the areas
        # Pass all areas at once - the function handles checking them all
        any_light_on = await self.client.any_lights_on_in_area(area_ids)
        
        logger.info(f"Toggle decision for {len(area_ids)} area(s): lights_on={any_light_on}")
        
        if any_light_on:
            # Lights are on somewhere - turn off ALL areas and disable MagicLight
            logger.info(f"Lights are on in at least one area, turning off all areas and disabling MagicLight")
            
            for area_id in area_ids:
                # Disable HomeGlo mode first to prevent race conditions
                if area_id in self.client.magic_mode_areas:
                    await self.client.disable_magic_mode(area_id, save_offset=True)
                    logger.info(f"HomeGlo disabled for area {area_id}")
                
                # Then turn off all lights
                target_type, target_value = await self.client.determine_light_target(area_id)
                service_data = {"transition": 1}
                target = {target_type: target_value}
                await self.client.call_service("light", "turn_off", service_data, target)
            
        else:
            # All lights are off - turn them all on with MagicLight
            logger.info(f"All lights are off in all areas, enabling MagicLight and turning on")
            
            for area_id in area_ids:
                # Enable magic mode (sets MagicLight = true)
                self.client.enable_magic_mode(area_id, restore_offset=True)
                
                # Get and apply adaptive lighting values
                lighting_values = await self.client.get_adaptive_lighting_for_area(area_id)
                await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=1)
                
                offset = self.client.magic_mode_time_offsets.get(area_id, 0)
                logger.info(f"MagicLight enabled for area {area_id} with TimeLocation offset {offset} minutes")
    
    async def magiclight_toggle(self, area_id: str, source: str = "service_call"):
        """MagicLight Toggle - Smart toggle based on light state.
        
        Just delegates to magiclight_toggle_multiple for consistency.
        
        Args:
            area_id: The area ID to control
            source: Source of the action
        """
        await self.magiclight_toggle_multiple([area_id], source)
    
    async def reset(self, area_id: str, clear_saved: bool = True, source: str = "service_call"):
        """Reset - Set TimeLocation to current time (offset 0), enable MagicLight, and unfreeze.

        This resets the area to track the current actual time, enables MagicLight mode,
        and applies the appropriate lighting for the current time.

        Args:
            area_id: The area ID to control
            clear_saved: Whether to also clear recall offsets (default True for true reset)
            source: Source of the action
        """
        logger.info(f"[{source}] Resetting MagicLight state for area {area_id}")

        # Reset time offset to 0 (sets TimeLocation to current time)
        self.client.magic_mode_time_offsets[area_id] = 0

        # Clear recall offset for true reset (unless preserving for special cases)
        if clear_saved and area_id in self.client.recall_time_offsets:
            del self.client.recall_time_offsets[area_id]
            self.client.save_offsets()
            logger.info(f"Cleared recall offset for area {area_id}")

        # Enable magic mode (MagicLight = true)
        # This ensures the area will track time going forward
        self.client.enable_magic_mode(area_id)

        # DayHalf is automatically determined by the brain based on current solar position
        # Frozen state would be handled by separate freeze/unfreeze primitives when implemented

        # Get and apply adaptive lighting values for current time (offset 0)
        lighting_values = await self.client.get_adaptive_lighting_for_area(area_id)
        await self.client.turn_on_lights_adaptive(area_id, lighting_values, transition=1)

        logger.info(f"Reset complete: area {area_id} now tracking current time with MagicLight enabled")
    
    # TODO: Add more primitives as we implement them:
    # - full_send (zone-wide operation)
    # - freeze/unfreeze
    # - nitelite
    # - britelite