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

        # Should NOT update lights when already enabled (preserves stepped-down state)
        self.mock_client.turn_on_lights_adaptive.assert_not_called()

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
        self.mock_client.recall_time_offsets = {area_id: 180}  # Recall offset
        self.mock_client.save_offsets = MagicMock()

        await self.primitives.reset(area_id)

        # Should reset time offset to 0
        assert self.mock_client.magic_mode_time_offsets[area_id] == 0

        # Should clear recall offset by default (for true reset)
        assert area_id not in self.mock_client.recall_time_offsets
        self.mock_client.save_offsets.assert_called_once()

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
    async def test_reset_preserve_recall(self):
        """Test reset functionality with preserve recall offset option."""
        area_id = "test_area"
        self.mock_client.magic_mode_time_offsets[area_id] = 180  # Current offset
        self.mock_client.recall_time_offsets = {area_id: 180}  # Recall offset
        self.mock_client.save_offsets = MagicMock()

        await self.primitives.reset(area_id, clear_saved=False)

        # Should reset time offset to 0
        assert self.mock_client.magic_mode_time_offsets[area_id] == 0

        # Should preserve recall offset when clear_saved=False
        assert area_id in self.mock_client.recall_time_offsets
        assert self.mock_client.recall_time_offsets[area_id] == 180
        self.mock_client.save_offsets.assert_not_called()

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


class TestSolarMidnightReset:
    """Test cases for solar midnight reset functionality."""

    def setup_method(self):
        """Set up test environment for each test."""
        # Create mock websocket client
        self.mock_client = MagicMock()
        self.mock_client.magic_mode_areas = set()
        self.mock_client.magic_mode_time_offsets = {}
        self.mock_client.recall_time_offsets = {}
        self.mock_client.latitude = 40.7128
        self.mock_client.longitude = -74.0060
        self.mock_client.timezone = "America/New_York"

        # Mock async methods
        self.mock_client.update_lights_in_magic_mode = AsyncMock()
        self.mock_client.save_offsets = MagicMock()

    @pytest.mark.asyncio
    async def test_solar_midnight_resets_both_offsets(self):
        """Test that solar midnight resets both current and recall offsets."""
        from main import HomeAssistantWebSocketClient

        # Create a real instance to test the method
        client = HomeAssistantWebSocketClient("localhost", 8123, "test_token")
        client.latitude = 40.7128
        client.longitude = -74.0060
        client.timezone = "America/New_York"

        # Mock the async method
        client.update_lights_in_magic_mode = AsyncMock()
        client.save_offsets = MagicMock()

        # Set up test data
        area1 = "living_room"
        area2 = "bedroom"

        # Current offsets
        client.magic_mode_time_offsets = {area1: 120, area2: -60}
        # Recall offsets
        client.recall_time_offsets = {area1: 180, area2: -90}
        # Magic mode areas
        client.magic_mode_areas = {area1, area2}

        # Mock datetime to simulate crossing solar midnight
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        # Simulate yesterday and today
        tzinfo = ZoneInfo("America/New_York")
        yesterday = datetime(2024, 1, 15, 23, 30, tzinfo=tzinfo)
        today = datetime(2024, 1, 16, 0, 30, tzinfo=tzinfo)  # After midnight

        # First call (before midnight) - should return current time
        result1 = await client.reset_offsets_at_solar_midnight(None)
        assert result1 is not None

        # Second call (after midnight) - should trigger reset
        with patch('main.datetime') as mock_datetime:
            mock_datetime.now.return_value = today

            # Mock astral calculations to return predictable solar times
            with patch('astral.sun.sun') as mock_sun:
                solar_noon = today.replace(hour=12, minute=0, second=0)
                mock_sun.return_value = {"noon": solar_noon}

                result2 = await client.reset_offsets_at_solar_midnight(yesterday)

        # Should return updated time
        assert result2 is not None

        # Both current offsets should be reset to 0
        assert client.magic_mode_time_offsets[area1] == 0
        assert client.magic_mode_time_offsets[area2] == 0

        # Recall offsets should be cleared
        assert area1 not in client.recall_time_offsets
        assert area2 not in client.recall_time_offsets

        # Should save the cleared state
        client.save_offsets.assert_called_once()

        # Should update lights for magic mode areas
        assert client.update_lights_in_magic_mode.call_count == 2
        client.update_lights_in_magic_mode.assert_any_call(area1)
        client.update_lights_in_magic_mode.assert_any_call(area2)