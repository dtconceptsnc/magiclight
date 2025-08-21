#!/usr/bin/env python3
"""Compare HTML formula vs Python brain.py formula"""

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# HTML formula (using Local Solar Time)
def html_sun_position(hour):
    """HTML uses: -cos((2*PI*h)/24) where h is Local Solar Time"""
    return -math.cos((2 * math.pi * hour) / 24)

# Python brain.py formula for daytime
def python_sun_position_daytime(elev_deg):
    """Python uses: sin(radians(elev_deg)) during daytime"""
    return math.sin(math.radians(elev_deg))

# Test at different times
print("Hour | HTML pos | Elev(deg) | Python pos | Difference")
print("-----|----------|-----------|------------|------------")

# Sample elevation angles at different times (approximate)
# These would vary by location and date
elevations = [
    (0, -40),   # Midnight
    (3, -35),   # 3 AM
    (6, 0),     # Sunrise ~6 AM
    (9, 30),    # 9 AM
    (12, 60),   # Noon (max elevation varies by latitude)
    (15, 30),   # 3 PM
    (18, 0),    # Sunset ~6 PM
    (21, -35),  # 9 PM
]

for hour, elev in elevations:
    html_pos = html_sun_position(hour)
    if elev >= 0:
        python_pos = python_sun_position_daytime(elev)
    else:
        # Night time - Python uses different formula
        TWILIGHT = -18.0
        if elev <= TWILIGHT:
            python_pos = -1.0
        else:
            python_pos = elev / -TWILIGHT
    
    diff = html_pos - python_pos
    print(f"{hour:4} | {html_pos:8.3f} | {elev:9} | {python_pos:10.3f} | {diff:11.3f}")

print("\n" + "="*60)
print("Key differences:")
print("1. HTML uses time-based cosine: smooth -1 to 1 over 24h")
print("2. Python uses actual sun elevation angle")
print("3. At noon: HTML always gives 1.0, Python gives sin(60°)≈0.866")
print("4. Python's curve shape depends on actual sun path, not just time")