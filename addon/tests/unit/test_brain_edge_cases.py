#!/usr/bin/env python3
"""Test edge cases and error conditions in brain.py for improved coverage."""

from datetime import datetime, timezone
import math
import pytest

from brain import (
    AdaptiveLighting,
    get_adaptive_lighting,
    calculate_dimming_step,
    ColorMode,
    DEFAULT_MAX_DIM_STEPS
)


class TestAdaptiveLightingEdgeCases:
    """Test edge cases for AdaptiveLighting class."""

    def test_sun_position_no_solar_noon_fallback(self):
        """Test sun position calculation when solar_noon is None (fallback case)."""
        # Create AdaptiveLighting with no solar times
        al = AdaptiveLighting()
        assert al.solar_noon is None
        assert al.solar_midnight is None

        now = datetime(2024, 6, 21, 15, 30, 0)  # 3:30 PM
        # Call with any elevation value to trigger the calculation
        sun_pos = al.calculate_sun_position(now, elev_deg=45.0)

        # Should use fallback calculation based on hour
        # Line 153-154: Fallback using simple time of day
        expected = -math.cos(2 * math.pi * 15.5 / 24)  # 15.5 = 15 + 30/60
        assert abs(sun_pos - expected) < 0.001

    def test_get_solar_time_with_only_solar_noon(self):
        """Test get_solar_time when only solar_noon is available."""
        solar_noon = datetime(2024, 6, 21, 12, 0, 0)
        al = AdaptiveLighting(solar_noon=solar_noon, solar_midnight=None)

        # Test time 3 hours after solar noon
        test_time = datetime(2024, 6, 21, 15, 0, 0)
        solar_time = al.get_solar_time(test_time)

        # Lines 165-166: Calculate from solar noon when midnight not available
        # Should be (3 + 12) % 24 = 15
        assert abs(solar_time - 15.0) < 0.001

    def test_get_solar_time_no_solar_times_fallback(self):
        """Test get_solar_time fallback when no solar times available."""
        al = AdaptiveLighting()  # No solar times

        test_time = datetime(2024, 6, 21, 14, 30, 0)  # 2:30 PM
        solar_time = al.get_solar_time(test_time)

        # Should fall back to regular time: 14.5 hours
        expected = 14.5
        assert abs(solar_time - expected) < 0.001

    def test_to_perceptual_brightness_edge_values(self):
        """Test perceptual brightness conversion with edge values."""
        al = AdaptiveLighting(gamma_ui=38)  # Default UI value

        # Lines 173-174: Convert linear brightness to perceptual using gamma
        # Test boundary values
        assert al.to_perceptual_brightness(0) == 0.0
        assert al.to_perceptual_brightness(100) == 1.0

        # Test clamping (values outside 0-100 range)
        assert al.to_perceptual_brightness(-10) == 0.0  # Clamped to 0
        assert al.to_perceptual_brightness(150) == 1.0   # Clamped to 100

    def test_to_mired_edge_values(self):
        """Test mired conversion with edge values."""
        al = AdaptiveLighting()

        # Line 178: Convert Kelvin to mireds with clamping
        # Test boundary clamping
        very_low_kelvin = al.to_mired(100)  # Should clamp to 500K
        expected_low = 1e6 / 500
        assert abs(very_low_kelvin - expected_low) < 0.001

        very_high_kelvin = al.to_mired(10000)  # Should clamp to 6500K
        expected_high = 1e6 / 6500
        assert abs(very_high_kelvin - expected_high) < 0.001

    def test_color_temperature_to_rgb_edge_cases(self):
        """Test RGB conversion with edge cases."""
        al = AdaptiveLighting()

        # Test with very low and high kelvin values
        rgb_low = al.color_temperature_to_rgb(500)   # Minimum
        rgb_high = al.color_temperature_to_rgb(6500)  # Maximum

        # Should return valid RGB values
        for rgb in [rgb_low, rgb_high]:
            assert len(rgb) == 3
            assert all(0 <= c <= 255 for c in rgb)

    def test_color_temperature_to_xy_edge_cases(self):
        """Test XY conversion with edge cases."""
        al = AdaptiveLighting()

        # Test with boundary values
        xy_low = al.color_temperature_to_xy(500)
        xy_high = al.color_temperature_to_xy(6500)

        # Should return valid XY values
        for xy in [xy_low, xy_high]:
            assert len(xy) == 2
            assert 0 <= xy[0] <= 1
            assert 0 <= xy[1] <= 1


    def test_calculate_dimming_step_edge_cases(self):
        """Test calculate_dimming_step with edge cases."""
        now = datetime(2024, 6, 21, 12, 0, 0)

        # Test with very small max_steps that might cause division issues
        result = calculate_dimming_step(
            current_time=now,
            action="brighten",
            latitude=37.0,
            longitude=-122.0,
            timezone="America/Los_Angeles",
            max_steps=0.1  # Very small value
        )

        # Should still return valid result
        assert "kelvin" in result
        assert "brightness" in result
        assert "time_offset_minutes" in result

    def test_calculate_dimming_step_invalid_action(self):
        """Test calculate_dimming_step with invalid action."""
        now = datetime(2024, 6, 21, 12, 0, 0)

        # Line 522: Handle invalid action parameter
        result = calculate_dimming_step(
            current_time=now,
            action="invalid_action",  # Invalid action
            latitude=37.0,
            longitude=-122.0,
            timezone="America/Los_Angeles",
            max_steps=DEFAULT_MAX_DIM_STEPS
        )

        # Should still return valid result
        assert "kelvin" in result
        assert "brightness" in result
        assert "time_offset_minutes" in result

    def test_calculate_dimming_step_boundary_conditions(self):
        """Test calculate_dimming_step with boundary conditions."""
        now = datetime(2024, 6, 21, 12, 0, 0)
        location_params = {
            "latitude": 37.0,
            "longitude": -122.0,
            "timezone": "America/Los_Angeles"
        }

        # Test with max_steps = 1 (minimum)
        result = calculate_dimming_step(
            current_time=now,
            action="brighten",
            max_steps=1,
            **location_params
        )

        assert "time_offset_minutes" in result
        assert abs(result["time_offset_minutes"]) > 0  # Should have some offset

        # Test with very high max_steps
        result_high = calculate_dimming_step(
            current_time=now,
            action="dim",
            max_steps=1000,
            **location_params
        )

        assert "time_offset_minutes" in result_high
        # With high max_steps, offset should be smaller
        assert abs(result_high["time_offset_minutes"]) < abs(result["time_offset_minutes"])

    def test_get_adaptive_lighting_with_custom_config(self):
        """Test get_adaptive_lighting with custom configuration."""
        now = datetime(2024, 6, 21, 12, 0, 0)

        # Test with custom color mode in config
        result_rgb = get_adaptive_lighting(
            current_time=now,
            latitude=37.0,
            longitude=-122.0,
            timezone="America/Los_Angeles",
            config={"color_mode": "rgb"}
        )

        assert "rgb" in result_rgb
        assert "kelvin" in result_rgb

        # Test with XY color mode in config
        result_xy = get_adaptive_lighting(
            current_time=now,
            latitude=37.0,
            longitude=-122.0,
            timezone="America/Los_Angeles",
            config={"color_mode": "xy"}
        )

        assert "xy" in result_xy
        assert "kelvin" in result_xy

    def test_adaptive_lighting_with_extreme_curve_parameters(self):
        """Test AdaptiveLighting with extreme curve parameters."""
        # Test with extreme midpoint and steepness values
        al = AdaptiveLighting(
            mid_bri_up=0.1,    # Very early morning peak
            steep_bri_up=10.0,  # Very steep
            mid_cct_dn=23.5,   # Very late evening
            steep_cct_dn=0.1   # Very gradual
        )

        morning = datetime(2024, 6, 21, 6, 0, 0)
        brightness = al.calculate_brightness(morning)
        color_temp = al.calculate_color_temperature(morning)

        # Should still return valid values
        assert 1 <= brightness <= 100
        assert 500 <= color_temp <= 6500

    def test_color_conversion_with_extreme_values(self):
        """Test color conversions with extreme input values."""
        al = AdaptiveLighting()

        # Test RGB conversion with boundary Kelvin values
        rgb_min = al.color_temperature_to_rgb(500)   # Minimum
        rgb_max = al.color_temperature_to_rgb(6500)  # Maximum

        for rgb in [rgb_min, rgb_max]:
            assert len(rgb) == 3
            assert all(0 <= c <= 255 for c in rgb)

        # Test XY conversion with boundary Kelvin values
        xy_min = al.color_temperature_to_xy(500)
        xy_max = al.color_temperature_to_xy(6500)

        for xy in [xy_min, xy_max]:
            assert len(xy) == 2
            assert 0 <= xy[0] <= 1
            assert 0 <= xy[1] <= 1


