#!/usr/bin/env python3
"""Test script for solar midnight offset reset functionality."""

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from astral import LocationInfo
from astral.sun import sun

# Test location (San Francisco)
latitude = 37.7749
longitude = -122.4194
timezone = "America/Los_Angeles"

# Simulate the reset function
async def test_reset_offsets_at_solar_midnight():
    """Test the solar midnight reset logic."""
    
    # Setup
    tzinfo = ZoneInfo(timezone)
    now = datetime.now(tzinfo)
    
    # Calculate solar events
    loc = LocationInfo(latitude=latitude, longitude=longitude, timezone=timezone)
    solar_events = sun(loc.observer, date=now.date(), tzinfo=tzinfo)
    solar_noon = solar_events["noon"]
    
    # Calculate solar midnight
    if solar_noon.hour >= 12:
        solar_midnight = solar_noon - timedelta(hours=12)
    else:
        solar_midnight = solar_noon + timedelta(hours=12)
    
    print(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Solar noon: {solar_noon.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Solar midnight: {solar_midnight.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Simulate offset dictionary
    magic_mode_time_offsets = {
        "living_room": 120,  # +2 hours
        "bedroom": -60,      # -1 hour
        "kitchen": 30,       # +30 minutes
        "bathroom": 0        # No offset
    }
    
    print("Initial offsets:")
    for area, offset in magic_mode_time_offsets.items():
        print(f"  {area}: {offset} minutes")
    print()
    
    # Test different scenarios
    test_times = [
        solar_midnight - timedelta(minutes=30),  # Before midnight
        solar_midnight - timedelta(seconds=1),   # Just before midnight
        solar_midnight,                          # Exactly at midnight
        solar_midnight + timedelta(seconds=1),   # Just after midnight
        solar_midnight + timedelta(minutes=30),  # After midnight
    ]
    
    for test_time in test_times:
        print(f"Testing time: {test_time.strftime('%H:%M:%S')}")
        
        # Simulate last check (1 hour before test time)
        last_check = test_time - timedelta(hours=1)
        
        # Check if we should reset
        should_reset = last_check < solar_midnight <= test_time
        
        if should_reset:
            print("  → RESET TRIGGERED!")
            # Reset all offsets
            for area in list(magic_mode_time_offsets.keys()):
                old_offset = magic_mode_time_offsets[area]
                if old_offset != 0:
                    print(f"     Resetting {area}: {old_offset} → 0 minutes")
                    magic_mode_time_offsets[area] = 0
        else:
            print("  → No reset needed")
        print()
    
    print("Final offsets after test:")
    for area, offset in magic_mode_time_offsets.items():
        print(f"  {area}: {offset} minutes")

# Run the test
if __name__ == "__main__":
    asyncio.run(test_reset_offsets_at_solar_midnight())