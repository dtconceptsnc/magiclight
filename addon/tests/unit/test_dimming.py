#!/usr/bin/env python3
"""Test script to verify dimming respects min/max boundaries"""

import sys
sys.path.insert(0, 'magiclight')

from datetime import datetime
from brain import calculate_dimming_step, get_adaptive_lighting
import os

# Test with custom min/max values
def test_dimming_boundaries():
    print("Testing dimming with custom boundaries...")
    
    # Set test boundaries
    min_ct = 2000
    max_ct = 4000
    min_brightness = 20
    max_brightness = 80
    
    # Test location (San Francisco)
    latitude = 37.7749
    longitude = -122.4194
    timezone = "America/Los_Angeles"
    
    current_time = datetime.now()
    
    print(f"\nTest boundaries:")
    print(f"  Color temp: {min_ct}K - {max_ct}K")
    print(f"  Brightness: {min_brightness}% - {max_brightness}%")
    
    # Test brighten action
    print("\n=== Testing BRIGHTEN ===")
    for i in range(5):
        result = calculate_dimming_step(
            current_time=current_time,
            action='brighten',
            latitude=latitude,
            longitude=longitude,
            timezone=timezone,
            min_color_temp=min_ct,
            max_color_temp=max_ct,
            min_brightness=min_brightness,
            max_brightness=max_brightness,
            max_steps=10
        )
        
        print(f"Step {i+1}: Kelvin={result['kelvin']}K, Brightness={result['brightness']}%")
        
        # Check boundaries
        assert min_ct <= result['kelvin'] <= max_ct, f"Kelvin {result['kelvin']} out of bounds!"
        assert min_brightness <= result['brightness'] <= max_brightness, f"Brightness {result['brightness']} out of bounds!"
        
        # Move time forward for next step
        current_time = result['target_time']
    
    # Reset time and test dim action
    current_time = datetime.now()
    print("\n=== Testing DIM ===")
    for i in range(5):
        result = calculate_dimming_step(
            current_time=current_time,
            action='dim',
            latitude=latitude,
            longitude=longitude,
            timezone=timezone,
            min_color_temp=min_ct,
            max_color_temp=max_ct,
            min_brightness=min_brightness,
            max_brightness=max_brightness,
            max_steps=10
        )
        
        print(f"Step {i+1}: Kelvin={result['kelvin']}K, Brightness={result['brightness']}%")
        
        # Check boundaries
        assert min_ct <= result['kelvin'] <= max_ct, f"Kelvin {result['kelvin']} out of bounds!"
        assert min_brightness <= result['brightness'] <= max_brightness, f"Brightness {result['brightness']} out of bounds!"
        
        # Move time forward for next step
        current_time = result['target_time']
    
    print("\n✅ All boundary checks passed!")
    
    # Test get_adaptive_lighting with custom boundaries
    print("\n=== Testing get_adaptive_lighting ===")
    lighting = get_adaptive_lighting(
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        min_color_temp=min_ct,
        max_color_temp=max_ct,
        min_brightness=min_brightness,
        max_brightness=max_brightness
    )
    
    print(f"Current: Kelvin={lighting['kelvin']}K, Brightness={lighting['brightness']}%")
    assert min_ct <= lighting['kelvin'] <= max_ct, f"Kelvin {lighting['kelvin']} out of bounds!"
    assert min_brightness <= lighting['brightness'] <= max_brightness, f"Brightness {lighting['brightness']} out of bounds!"
    print("✅ get_adaptive_lighting boundaries respected!")

if __name__ == "__main__":
    test_dimming_boundaries()
    print("\n🎉 All tests passed!")