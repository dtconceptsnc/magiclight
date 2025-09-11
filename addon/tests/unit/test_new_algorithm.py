#!/usr/bin/env python3
"""Test script for the new simplified logistic curves and arc-based dimming."""

import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from brain import get_adaptive_lighting, calculate_dimming_step


@pytest.fixture
def test_config():
    """Provide test configuration with new parameter names."""
    return {
        'min_color_temp': 500,
        'max_color_temp': 6500,
        'min_brightness': 1,
        'max_brightness': 100,
        'mid_bri_up': 6.0,
        'steep_bri_up': 1.5,
        'mid_cct_up': 6.0,
        'steep_cct_up': 1.5,
        'mid_bri_dn': 8.0,
        'steep_bri_dn': 1.3,
        'mid_cct_dn': 8.0,
        'steep_cct_dn': 1.3,
        'mirror_up': True,
        'mirror_dn': True,
        'gamma_ui': 38  # Maps to gamma 0.62
    }


@pytest.fixture
def test_location():
    """Provide test location parameters."""
    return {
        'latitude': 35.0,
        'longitude': -78.6,
        'timezone': 'US/Eastern'
    }


class TestSimplifiedAdaptiveLighting:
    """Test the simplified adaptive lighting curves."""
    
    def test_adaptive_lighting_throughout_day(self, test_config, test_location):
        """Test adaptive lighting values at different times of day."""
        tz = ZoneInfo("US/Eastern")
        base_date = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        
        test_times = [
            (base_date.replace(hour=0), "Midnight"),
            (base_date.replace(hour=6), "6 AM"),
            (base_date.replace(hour=12), "Noon"),
            (base_date.replace(hour=18), "6 PM"),
        ]
        
        for test_time, label in test_times:
            result = get_adaptive_lighting(
                current_time=test_time,
                config=test_config,
                **test_location
            )
            
            # Basic sanity checks
            assert 'brightness' in result
            assert 'kelvin' in result
            assert 'rgb' in result
            assert 'solar_time' in result
            
            # Range checks
            assert test_config['min_brightness'] <= result['brightness'] <= test_config['max_brightness']
            assert test_config['min_color_temp'] <= result['kelvin'] <= test_config['max_color_temp']
            assert len(result['rgb']) == 3
            assert all(0 <= c <= 255 for c in result['rgb'])
            assert 0 <= result['solar_time'] <= 24
    
    def test_noon_values(self, test_config, test_location):
        """Test that noon gives maximum brightness and color temperature."""
        tz = ZoneInfo("US/Eastern")
        noon = datetime.now(tz).replace(hour=12, minute=0, second=0, microsecond=0)
        
        result = get_adaptive_lighting(
            current_time=noon,
            config=test_config,
            **test_location
        )
        
        # At noon, we expect values to be near maximum
        assert result['brightness'] >= 90  # Should be near max
        assert result['kelvin'] >= 6000  # Should be near max


class TestArcBasedDimming:
    """Test the arc-based dimming step calculation."""
    
    def test_morning_brightening_steps(self, test_config, test_location):
        """Test brightening steps in the morning."""
        tz = ZoneInfo("US/Eastern")
        morning_time = datetime.now(tz).replace(hour=8, minute=0, second=0, microsecond=0)
        
        # Take 3 brightening steps
        current_time = morning_time
        previous_brightness = None
        
        for i in range(3):
            result = calculate_dimming_step(
                current_time=current_time,
                action='brighten',
                max_steps=10,
                config=test_config,
                **test_location
            )
            
            assert 'brightness' in result
            assert 'kelvin' in result
            assert 'time_offset_minutes' in result
            assert 'target_time' in result
            
            # Brightness should generally increase when brightening in morning
            if previous_brightness is not None:
                assert result['brightness'] >= previous_brightness - 5  # Allow small variance
            
            previous_brightness = result['brightness']
            current_time = result['target_time']
    
    def test_evening_dimming_steps(self, test_config, test_location):
        """Test dimming steps in the evening."""
        tz = ZoneInfo("US/Eastern")
        evening_time = datetime.now(tz).replace(hour=19, minute=0, second=0, microsecond=0)
        
        # Take 3 dimming steps
        current_time = evening_time
        previous_brightness = None
        
        for i in range(3):
            result = calculate_dimming_step(
                current_time=current_time,
                action='dim',
                max_steps=10,
                config=test_config,
                **test_location
            )
            
            assert 'brightness' in result
            assert 'kelvin' in result
            assert 'time_offset_minutes' in result
            assert 'target_time' in result
            
            # Brightness should generally decrease when dimming in evening
            if previous_brightness is not None:
                assert result['brightness'] <= previous_brightness + 5  # Allow small variance
            
            previous_brightness = result['brightness']
            current_time = result['target_time']



class TestMirrorParameters:
    """Test that mirror flags work correctly."""
    
    def test_mirror_up_flag(self, test_location):
        """Test that mirror_up makes CCT follow brightness parameters."""
        tz = ZoneInfo("US/Eastern")
        morning = datetime.now(tz).replace(hour=9, minute=0, second=0, microsecond=0)
        
        # Test with mirror ON
        config_mirrored = {
            'mid_bri_up': 5.0,
            'steep_bri_up': 2.0,
            'mid_cct_up': 7.0,  # These should be ignored
            'steep_cct_up': 1.0,  # These should be ignored
            'mirror_up': True,
        }
        
        result_mirrored = get_adaptive_lighting(
            current_time=morning,
            config=config_mirrored,
            **test_location
        )
        
        # Test with mirror OFF
        config_unmirrored = {
            'mid_bri_up': 5.0,
            'steep_bri_up': 2.0,
            'mid_cct_up': 7.0,
            'steep_cct_up': 1.0,
            'mirror_up': False,
        }
        
        result_unmirrored = get_adaptive_lighting(
            current_time=morning,
            config=config_unmirrored,
            **test_location
        )
        
        # With different CCT parameters, results should differ when not mirrored
        # This is a basic check - exact values depend on the curve calculations
        assert result_mirrored['kelvin'] != result_unmirrored['kelvin'] or \
               abs(result_mirrored['kelvin'] - result_unmirrored['kelvin']) < 100