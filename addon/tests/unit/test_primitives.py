#!/usr/bin/env python3
"""Test suite for primitives.py - MagicLight service primitives."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from primitives import MagicLightPrimitives
from brain import DEFAULT_MAX_DIM_STEPS


class TestMagicLightPrimitives:
    """Test cases for MagicLightPrimitives."""

    def setup_method(self):
        """Set up test environment for each test."""
        # Create mock websocket client
        self.mock_client = MagicMock()
        self.mock_client.magic_mode_areas = set()
        self.mock_client.magic_mode_time_offsets = {}
        self.mock_client.config = {"max_dim_steps": DEFAULT_MAX_DIM_STEPS}
        self.mock_client.curve_params = {}

        # Mock async methods
        self.mock_client.turn_on_lights_adaptive = AsyncMock()
        self.mock_client.get_adaptive_lighting_for_area = AsyncMock()
        self.mock_client.any_lights_on_in_area = AsyncMock()
        self.mock_client.determine_light_target = AsyncMock()
        self.mock_client.call_service = AsyncMock()
        self.mock_client.disable_magic_mode = AsyncMock()
        self.mock_client.enable_magic_mode = MagicMock()

        # Set default return values
        self.mock_client.determine_light_target.return_value = ("area_id", "test_area")
        self.mock_client.get_adaptive_lighting_for_area.return_value = {
            'kelvin': 3000,
            'brightness': 80,
            'rgb': [255, 200, 150],
            'xy': [0.5, 0.4]
        }

        self.primitives = MagicLightPrimitives(self.mock_client)

    @pytest.mark.asyncio
    async def test_step_up_magic_mode(self):
        """Test step_up when area is in magic mode."""
        area_id = "test_area"
        self.mock_client.magic_mode_areas.add(area_id)
        self.mock_client.magic_mode_time_offsets[area_id] = 60  # 1 hour offset

        # Mock the dimming calculation
        mock_dimming_result = {
            'time_offset_minutes': 30,
            'kelvin': 4000,
            'brightness': 85,
            'rgb': [255, 220, 180],
            'xy': [0.45, 0.35]
        }

        with patch('primitives.calculate_dimming_step', return_value=mock_dimming_result):
            await self.primitives.step_up(area_id, "test_source")

        # Verify time offset was updated
        assert self.mock_client.magic_mode_time_offsets[area_id] == 90  # 60 + 30

        # Verify lights were updated with dimming result
        self.mock_client.turn_on_lights_adaptive.assert_called_once()
        call_args = self.mock_client.turn_on_lights_adaptive.call_args
        assert call_args[0][0] == area_id  # area_id
        lighting_values = call_args[0][1]  # lighting_values
        assert lighting_values['kelvin'] == 4000
        assert lighting_values['brightness'] == 85
        assert call_args[1]['transition'] == 0.2  # transition

    @pytest.mark.asyncio
    async def test_step_up_magic_mode_with_bounds(self):
        """Test step_up respects time offset bounds."""
        area_id = "test_area"
        self.mock_client.magic_mode_areas.add(area_id)
        self.mock_client.magic_mode_time_offsets[area_id] = 700  # Near upper bound

        mock_dimming_result = {'time_offset_minutes': 100, 'kelvin': 4000, 'brightness': 85}

        with patch('primitives.calculate_dimming_step', return_value=mock_dimming_result):
            await self.primitives.step_up(area_id)

        # Should be clamped to 720 (12 hours)
        assert self.mock_client.magic_mode_time_offsets[area_id] == 720

    @pytest.mark.asyncio
    async def test_step_up_magic_mode_calculation_error(self):
        """Test step_up fallback when calculation fails."""
        area_id = "test_area"
        self.mock_client.magic_mode_areas.add(area_id)
        self.mock_client.magic_mode_time_offsets[area_id] = 0

        with patch('primitives.calculate_dimming_step', side_effect=Exception("Calculation failed")):
            await self.primitives.step_up(area_id)

        # Should fall back to simple offset
        assert self.mock_client.magic_mode_time_offsets[area_id] == 30

        # Should call get_adaptive_lighting_for_area as fallback
        self.mock_client.get_adaptive_lighting_for_area.assert_called_once_with(area_id)
        self.mock_client.turn_on_lights_adaptive.assert_called_once()

    @pytest.mark.asyncio
    async def test_step_up_non_magic_mode_lights_on(self):
        """Test step_up when not in magic mode with lights on."""
        area_id = "test_area"
        self.mock_client.any_lights_on_in_area.return_value = True

        await self.primitives.step_up(area_id)

        # Should check if lights are on
        self.mock_client.any_lights_on_in_area.assert_called_once_with(area_id)

        # Should increase brightness
        self.mock_client.call_service.assert_called_once_with(
            "light", "turn_on",
            {"brightness_step_pct": 17, "transition": 1},
            {"area_id": "test_area"}
        )

    @pytest.mark.asyncio
    async def test_step_up_non_magic_mode_lights_off(self):
        """Test step_up when not in magic mode with lights off."""
        area_id = "test_area"
        self.mock_client.any_lights_on_in_area.return_value = False

        await self.primitives.step_up(area_id)

        # Should check if lights are on but not call service
        self.mock_client.any_lights_on_in_area.assert_called_once_with(area_id)
        self.mock_client.call_service.assert_not_called()

    @pytest.mark.asyncio
    async def test_step_down_magic_mode(self):
        """Test step_down when area is in magic mode."""
        area_id = "test_area"
        self.mock_client.magic_mode_areas.add(area_id)
        self.mock_client.magic_mode_time_offsets[area_id] = 30

        mock_dimming_result = {
            'time_offset_minutes': -20,
            'kelvin': 2500,
            'brightness': 50,
            'rgb': [255, 180, 120]
        }

        with patch('primitives.calculate_dimming_step', return_value=mock_dimming_result):
            await self.primitives.step_down(area_id)

        # Verify time offset was updated
        assert self.mock_client.magic_mode_time_offsets[area_id] == 10  # 30 + (-20)

        # Verify lights were updated
        self.mock_client.turn_on_lights_adaptive.assert_called_once()
        call_args = self.mock_client.turn_on_lights_adaptive.call_args
        lighting_values = call_args[0][1]
        assert lighting_values['kelvin'] == 2500
        assert lighting_values['brightness'] == 50

    @pytest.mark.asyncio
    async def test_step_down_magic_mode_minimum_brightness(self):
        """Test step_down ensures minimum brightness."""
        area_id = "test_area"
        self.mock_client.magic_mode_areas.add(area_id)

        mock_dimming_result = {
            'time_offset_minutes': -10,
            'kelvin': 2000,
            'brightness': 0  # Below minimum
        }

        with patch('primitives.calculate_dimming_step', return_value=mock_dimming_result):
            await self.primitives.step_down(area_id)

        # Should enforce minimum brightness of 1
        call_args = self.mock_client.turn_on_lights_adaptive.call_args
        lighting_values = call_args[0][1]
        assert lighting_values['brightness'] == 1

    @pytest.mark.asyncio
    async def test_step_down_non_magic_mode(self):
        """Test step_down when not in magic mode."""
        area_id = "test_area"
        self.mock_client.any_lights_on_in_area.return_value = True

        await self.primitives.step_down(area_id)

        # Should decrease brightness
        self.mock_client.call_service.assert_called_once_with(
            "light", "turn_on",
            {"brightness_step_pct": -17, "transition": 0.5},
            {"area_id": "test_area"}
        )

    @pytest.mark.asyncio
    async def test_magiclight_on_not_enabled(self):
        """Test magiclight_on when not previously enabled."""
        area_id = "test_area"

        await self.primitives.magiclight_on(area_id)

        # Should enable magic mode
        self.mock_client.enable_magic_mode.assert_called_once_with(area_id, restore_offset=True)

        # Should get and apply adaptive lighting
        self.mock_client.get_adaptive_lighting_for_area.assert_called_once_with(area_id)
        self.mock_client.turn_on_lights_adaptive.assert_called_once()

    @pytest.mark.asyncio
    async def test_magiclight_on_already_enabled(self):
        """Test magiclight_on when already enabled."""
        area_id = "test_area"
        self.mock_client.magic_mode_areas.add(area_id)

        await self.primitives.magiclight_on(area_id)

        # Should still call enable but without restoring offset (preserves current stepped state)
        self.mock_client.enable_magic_mode.assert_called_once_with(area_id, restore_offset=False)

        # Should still update lights
        self.mock_client.turn_on_lights_adaptive.assert_called_once()

    @pytest.mark.asyncio
    async def test_magiclight_off_enabled(self):
        """Test magiclight_off when enabled."""
        area_id = "test_area"
        self.mock_client.magic_mode_areas.add(area_id)
        self.mock_client.magic_mode_time_offsets[area_id] = 120

        await self.primitives.magiclight_off(area_id)

        # Should disable magic mode with save_offset=True
        self.mock_client.disable_magic_mode.assert_called_once_with(area_id, save_offset=True)

    @pytest.mark.asyncio
    async def test_magiclight_off_not_enabled(self):
        """Test magiclight_off when not enabled."""
        area_id = "test_area"

        await self.primitives.magiclight_off(area_id)

        # Should not call disable_magic_mode
        self.mock_client.disable_magic_mode.assert_not_called()

    @pytest.mark.asyncio
    async def test_magiclight_toggle_single_area(self):
        """Test magiclight_toggle delegates to toggle_multiple."""
        area_id = "test_area"

        # Mock the multi-area method
        self.primitives.magiclight_toggle_multiple = AsyncMock()

        await self.primitives.magiclight_toggle(area_id, "test_source")

        # Should call toggle_multiple with single area as list
        self.primitives.magiclight_toggle_multiple.assert_called_once_with([area_id], "test_source")

    @pytest.mark.asyncio
    async def test_magiclight_toggle_multiple_lights_on(self):
        """Test magiclight_toggle_multiple when lights are on."""
        area_ids = ["area1", "area2"]
        self.mock_client.magic_mode_areas.update(area_ids)
        self.mock_client.any_lights_on_in_area.return_value = True

        await self.primitives.magiclight_toggle_multiple(area_ids)

        # Should check combined light state
        self.mock_client.any_lights_on_in_area.assert_called_once_with(area_ids)

        # Should disable magic mode for both areas
        assert self.mock_client.disable_magic_mode.call_count == 2

        # Should turn off lights in both areas
        assert self.mock_client.call_service.call_count == 2
        for call in self.mock_client.call_service.call_args_list:
            # Check the domain and service (first two args)
            assert call[0][0] == "light"  # domain
            assert call[0][1] == "turn_off"  # service

    @pytest.mark.asyncio
    async def test_magiclight_toggle_multiple_lights_off(self):
        """Test magiclight_toggle_multiple when lights are off."""
        area_ids = ["area1", "area2"]
        self.mock_client.any_lights_on_in_area.return_value = False

        await self.primitives.magiclight_toggle_multiple(area_ids)

        # Should enable magic mode for both areas
        assert self.mock_client.enable_magic_mode.call_count == 2

        # Should get adaptive lighting and turn on lights for both areas
        assert self.mock_client.get_adaptive_lighting_for_area.call_count == 2
        assert self.mock_client.turn_on_lights_adaptive.call_count == 2

    @pytest.mark.asyncio
    async def test_magiclight_toggle_multiple_string_input(self):
        """Test magiclight_toggle_multiple handles string input."""
        area_id = "single_area"
        self.mock_client.any_lights_on_in_area.return_value = False

        await self.primitives.magiclight_toggle_multiple(area_id)

        # Should convert string to list and process normally
        self.mock_client.any_lights_on_in_area.assert_called_once_with([area_id])
        self.mock_client.enable_magic_mode.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset(self):
        """Test reset functionality."""
        area_id = "test_area"
        self.mock_client.magic_mode_time_offsets[area_id] = 180  # Current offset
        self.mock_client.saved_time_offsets = {area_id: 180}  # Saved offset
        self.mock_client.save_offsets = MagicMock()

        await self.primitives.reset(area_id)

        # Should reset time offset to 0
        assert self.mock_client.magic_mode_time_offsets[area_id] == 0

        # Should preserve saved offset (for future magiclight_on calls)
        assert area_id in self.mock_client.saved_time_offsets
        assert self.mock_client.saved_time_offsets[area_id] == 180

        # Should enable magic mode
        self.mock_client.enable_magic_mode.assert_called_once_with(area_id)

        # Should get and apply adaptive lighting
        self.mock_client.get_adaptive_lighting_for_area.assert_called_once_with(area_id)
        self.mock_client.turn_on_lights_adaptive.assert_called_once_with(
            area_id,
            self.mock_client.get_adaptive_lighting_for_area.return_value,
            transition=1
        )

    @pytest.mark.asyncio
    async def test_step_functions_with_custom_config(self):
        """Test step functions use custom config values."""
        area_id = "test_area"
        self.mock_client.magic_mode_areas.add(area_id)
        self.mock_client.config = {"max_dim_steps": 25}
        self.mock_client.curve_params = {"custom_param": "value"}

        mock_dimming_result = {'time_offset_minutes': 15, 'kelvin': 3500, 'brightness': 75}

        with patch('primitives.calculate_dimming_step', return_value=mock_dimming_result) as mock_calc:
            await self.primitives.step_up(area_id)

        # Should pass custom config to calculation
        mock_calc.assert_called_once()
        call_kwargs = mock_calc.call_args[1]
        assert call_kwargs['max_steps'] == 25
        assert call_kwargs['custom_param'] == "value"

    @pytest.mark.asyncio
    async def test_step_functions_no_config(self):
        """Test step functions work without config."""
        area_id = "test_area"
        self.mock_client.magic_mode_areas.add(area_id)
        # Remove config attributes
        delattr(self.mock_client, 'config')
        delattr(self.mock_client, 'curve_params')

        mock_dimming_result = {'time_offset_minutes': 15, 'kelvin': 3500, 'brightness': 75}

        with patch('primitives.calculate_dimming_step', return_value=mock_dimming_result) as mock_calc:
            await self.primitives.step_up(area_id)

        # Should use defaults
        call_kwargs = mock_calc.call_args[1]
        assert 'max_steps' in call_kwargs
        # Should not pass any curve_params since attribute doesn't exist

    @pytest.mark.asyncio
    async def test_source_parameter_logging(self):
        """Test that source parameter is used in logging."""
        area_id = "test_area"
        custom_source = "automation_trigger"

        # Test with magic mode
        self.mock_client.magic_mode_areas.add(area_id)
        mock_dimming_result = {'time_offset_minutes': 15, 'kelvin': 3500, 'brightness': 75}

        with patch('primitives.calculate_dimming_step', return_value=mock_dimming_result):
            with patch('primitives.logger') as mock_logger:
                await self.primitives.step_up(area_id, custom_source)

                # Should log with custom source
                mock_logger.info.assert_called()
                log_call = mock_logger.info.call_args_list[0][0][0]
                assert custom_source in log_call