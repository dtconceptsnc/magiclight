#!/usr/bin/env python3
"""Brain module for adaptive lighting – self-contained, with Home Assistant fallbacks.

Key updates
-----------
* `get_adaptive_lighting()` no longer *requires* latitude / longitude / timezone.
  If they’re omitted it pulls them from typical Home Assistant env-vars
  (`HASS_LATITUDE`, `HASS_LONGITUDE`, `HASS_TIME_ZONE` or `TZ`).  If those
  are missing it finally falls back to the local system timezone.
* No other public API changes – `config` overrides still work.

This keeps the module usable both inside a HA add-on and in standalone
scripts/tests.
"""

from __future__ import annotations

import math
import os
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple, Any
from enum import Enum

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # stdlib ≥3.9
from astral import LocationInfo
from astral.sun import sun, elevation as solar_elevation

logger = logging.getLogger(__name__)

class ColorMode(Enum):
    """Color mode for light control."""
    KELVIN = "kelvin"           # Use Kelvin color temperature
    RGB = "rgb"                 # Use RGB values
    XY = "xy"                   # Use CIE xy coordinates

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default color temperature range (Kelvin)
DEFAULT_MIN_COLOR_TEMP = int(os.getenv("MIN_COLOR_TEMP", "500"))  # Warm white (candle-like)
DEFAULT_MAX_COLOR_TEMP = int(os.getenv("MAX_COLOR_TEMP", "6500"))  # Cool daylight

# Default brightness range (percentage)
DEFAULT_MIN_BRIGHTNESS = 1
DEFAULT_MAX_BRIGHTNESS = 100

# Sun position to color/brightness mapping - default values, can be overridden
DEFAULT_SUN_CCT_GAMMA = 0.9         # Color temperature gamma (>1 = cooler during day)
DEFAULT_SUN_BRIGHTNESS_GAMMA = 0.5  # Brightness gamma (1 = cubic smooth-step)

# ---------------------------------------------------------------------------
# Adaptive-lighting math (unchanged)
# ---------------------------------------------------------------------------

class AdaptiveLighting:
    """Calculate adaptive lighting values based on sun position."""

    def __init__(
        self,
        *,
        min_color_temp: int = DEFAULT_MIN_COLOR_TEMP,
        max_color_temp: int = DEFAULT_MAX_COLOR_TEMP,
        min_brightness: int = DEFAULT_MIN_BRIGHTNESS,
        max_brightness: int = DEFAULT_MAX_BRIGHTNESS,
        sunrise_time: Optional[datetime] = None,
        sunset_time: Optional[datetime] = None,
        solar_noon: Optional[datetime] = None,
        color_mode: ColorMode = ColorMode.KELVIN,
    ) -> None:
        self.min_color_temp = min_color_temp
        self.max_color_temp = max_color_temp
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness
        self.sunrise_time = sunrise_time
        self.sunset_time = sunset_time
        self.solar_noon = solar_noon
        self.color_mode = color_mode

    def calculate_sun_position(self, now: datetime, elev_deg: float) -> float:
        """Calculate sun position using time-based cosine wave.
        
        This matches the HTML visualization approach:
        - Uses local solar time (accounting for solar noon)
        - Returns -cos(2π * hour / 24) where hour is in local solar time
        - Gives smooth transition from -1 (midnight) to +1 (solar noon)
        """
        if self.solar_noon:
            # Calculate hours from solar noon (solar noon = 0)
            hours_from_noon = (now - self.solar_noon).total_seconds() / 3600
            
            # Convert to 24-hour cycle (0-24 where noon = 12)
            solar_hour = (hours_from_noon + 12) % 24
            
            # Calculate position using cosine wave
            # -cos(2π * h / 24) gives: midnight=-1, 6am=0, noon=1, 6pm=0
            return -math.cos(2 * math.pi * solar_hour / 24)
        
        # Fallback: use simple time of day if no solar noon available
        hour = now.hour + now.minute / 60
        return -math.cos(2 * math.pi * hour / 24)

    # colour / brightness ------------------------------------------------
    def calculate_color_temperature(self, pos: float, *, gamma: float = DEFAULT_SUN_CCT_GAMMA) -> int:
        """
        Map sun-position (-1 … 1) to colour temperature using a cubic smooth-step.
        `gamma` < 1 warms the day (slower rise); > 1 cools it faster.

        pos = -1  →  min_color_temp      (night)
        pos =  0  →  ~⅓ up the range     (dawn / dusk)
        pos = +1  →  max_color_temp      (noon)
        """
        # 1. Linear map  [-1, 1] → [0, 1]
        t = (pos + 1) * 0.5

        # 2. Optional gamma to bias the curve (0.7-0.9 ≈ warmer day)
        if gamma != 1.0:
            t = t ** gamma

        # 3. Cubic smooth-step easing
        s = t * t * (3.0 - 2.0 * t)

        # 4. Interpolate
        val = self.min_color_temp + s * (self.max_color_temp - self.min_color_temp)
        return int(val)

    def calculate_brightness(self, pos: float, *, gamma: float = DEFAULT_SUN_BRIGHTNESS_GAMMA) -> int:
        """Calculate brightness based on sun position with optional gamma adjustment.
        
        Args:
            pos: Sun position (-1 to 1)
            gamma: Gamma value for brightness curve (1 = cubic smooth-step, <1 = dimmer, >1 = brighter)
        """
        # Map -1…1 -> 0…1
        t = (pos + 1) * 0.5          # 0 at night, 1 at noon
        
        # Apply gamma if specified
        if gamma != 1.0:
            t = t ** gamma
        
        # Cubic smooth-step easing
        s = t * t * (3.0 - 2.0 * t)
        
        return int(self.min_brightness +
                s * (self.max_brightness - self.min_brightness))

    # colour-space helpers ----------------------------------------------
    @staticmethod
    def color_temperature_to_rgb(kelvin: int) -> Tuple[int, int, int]:
        """Convert color temperature to RGB using improved Krystek polynomial approach.
        
        This uses polynomial approximations for the Planckian locus to get x,y
        coordinates, then converts through XYZ to RGB color space.
        More accurate than the simple Tanner Helland approximation.
        """
        # First get x,y coordinates using Krystek polynomials
        x, y = AdaptiveLighting.color_temperature_to_xy(kelvin)
        
        # Convert x,y to XYZ (assuming Y=1 for relative luminance)
        Y = 1.0
        X = (x * Y) / y if y != 0 else 0
        Z = ((1 - x - y) * Y) / y if y != 0 else 0
        
        # Convert XYZ to linear RGB (sRGB primaries)
        r =  3.2404542 * X - 1.5371385 * Y - 0.4985314 * Z
        g = -0.9692660 * X + 1.8760108 * Y + 0.0415560 * Z
        b =  0.0556434 * X - 0.2040259 * Y + 1.0572252 * Z
        
        # Clamp negative values
        r = max(0, r)
        g = max(0, g)
        b = max(0, b)
        
        # Normalize if any component > 1 (preserve color ratios)
        max_val = max(r, g, b)
        if max_val > 1:
            r /= max_val
            g /= max_val
            b /= max_val
        
        # Apply gamma correction (linear to sRGB)
        def linear_to_srgb(c):
            if c <= 0.0031308:
                return 12.92 * c
            else:
                return 1.055 * (c ** (1/2.4)) - 0.055
        
        r = linear_to_srgb(r)
        g = linear_to_srgb(g)
        b = linear_to_srgb(b)
        
        # Convert to 8-bit values
        return (
            int(max(0, min(255, round(r * 255)))),
            int(max(0, min(255, round(g * 255)))),
            int(max(0, min(255, round(b * 255)))),
        )

    @staticmethod
    def color_temperature_to_xy(cct: float) -> Tuple[float, float]:
        """Convert color temperature to CIE 1931 x,y using high-precision Krystek polynomials.
        
        Uses the improved Krystek & Moritz (1982) polynomial approximations for the
        Planckian locus. These provide excellent accuracy from 1000K to 25000K.
        
        Reference: Krystek, M. (1985). "An algorithm to calculate correlated colour
        temperature". Color Research & Application, 10(1), 38-40.
        """
        T = max(1000, min(cct, 25000))  # Clamp to valid range
        
        # Use reciprocal temperature for better numerical stability
        invT = 1000.0 / T  # T in thousands of Kelvin
        
        # Calculate x coordinate using Krystek's polynomial
        if T <= 4000:
            # Low temperature range (1000-4000K)
            x = (-0.2661239 * invT**3 
                 - 0.2343589 * invT**2 
                 + 0.8776956 * invT 
                 + 0.179910)
        else:
            # High temperature range (4000-25000K)
            x = (-3.0258469 * invT**3 
                 + 2.1070379 * invT**2 
                 + 0.2226347 * invT 
                 + 0.240390)
        
        # Calculate y coordinate using Krystek's polynomial
        if T <= 2222:
            # Very low temperature
            y = (-1.1063814 * x**3 
                 - 1.34811020 * x**2 
                 + 2.18555832 * x 
                 - 0.20219683)
        elif T <= 4000:
            # Low-mid temperature
            y = (-0.9549476 * x**3 
                 - 1.37418593 * x**2 
                 + 2.09137015 * x 
                 - 0.16748867)
        else:
            # High temperature
            y = (3.0817580 * x**3 
                 - 5.87338670 * x**2 
                 + 3.75112997 * x 
                 - 0.37001483)
        
        return (x, y)

    @staticmethod
    def rgb_to_xy(rgb: Tuple[int, int, int]) -> Tuple[float, float]:
        r, g, b = [c / 255.0 for c in rgb]
        r = ((r + 0.055) / 1.055) ** 2.4 if r > 0.04045 else r / 12.92
        g = ((g + 0.055) / 1.055) ** 2.4 if g > 0.04045 else g / 12.92
        b = ((b + 0.055) / 1.055) ** 2.4 if b > 0.04045 else b / 12.92
        X = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
        Y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
        Z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
        if X + Y + Z == 0:
            return (0.0, 0.0)
        x = X / (X + Y + Z)
        y = Y / (X + Y + Z)
        return (x, y)

# ---------------------------------------------------------------------------
# Helper: resolve lat/lon/tz from HA-style env vars
# ---------------------------------------------------------------------------

def _auto_location(lat: Optional[float], lon: Optional[float], tz: Optional[str]):
    if lat is not None and lon is not None:
        return lat, lon, tz  # caller supplied

    try:
        lat = lat or float(os.getenv("HASS_LATITUDE", os.getenv("LATITUDE", "")))
        lon = lon or float(os.getenv("HASS_LONGITUDE", os.getenv("LONGITUDE", "")))
    except ValueError:
        lat = lon = None

    tz = tz or os.getenv("HASS_TIME_ZONE", os.getenv("TZ", "")) or None
    return lat, lon, tz

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_adaptive_lighting(
    *,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    timezone: Optional[str] = None,
    current_time: Optional[datetime] = None,
    sun_cct_gamma: Optional[float] = None,
    sun_brightness_gamma: Optional[float] = None
) -> Dict[str, Any]:
    """Compute adaptive-lighting values.

    If *latitude*, *longitude* or *timezone* are omitted the function will try
    to pull them from the conventional Home Assistant env-vars.  Failing that
    it falls back to the system local timezone, and raises if lat/lon remain
    undefined.
    """
    latitude, longitude, timezone = _auto_location(latitude, longitude, timezone)
    if latitude is None or longitude is None:
        raise ValueError("Latitude/longitude not provided and not found in env vars")

    try:
        tzinfo = ZoneInfo(timezone) if timezone else None
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone '%s' – falling back to system local", timezone)
        tzinfo = None

    now = current_time.astimezone(tzinfo) if (current_time and tzinfo) else (
        current_time or datetime.now(tzinfo)
    )

    loc = LocationInfo(latitude=latitude, longitude=longitude, timezone=tzinfo or "UTC")
    observer = loc.observer
    solar_events = sun(observer, date=now.date(), tzinfo=loc.timezone)
    elev = solar_elevation(observer, now)

    al = AdaptiveLighting(
        sunrise_time=solar_events["sunrise"],
        sunset_time=solar_events["sunset"],
        solar_noon=solar_events["noon"],
    )

    sun_pos = al.calculate_sun_position(now, elev)
    
    # Use provided gamma values or defaults
    cct_gamma = sun_cct_gamma if sun_cct_gamma is not None else DEFAULT_SUN_CCT_GAMMA
    brightness_gamma = sun_brightness_gamma if sun_brightness_gamma is not None else DEFAULT_SUN_BRIGHTNESS_GAMMA
    
    cct = base_cct = al.calculate_color_temperature(sun_pos, gamma=cct_gamma)
    bri = base_bri = al.calculate_brightness(sun_pos, gamma=brightness_gamma)
    
    # Calculate all color representations
    rgb = al.color_temperature_to_rgb(cct)
    xy_from_kelvin = al.color_temperature_to_xy(cct)

    log_msg = f"{now.isoformat()} – elev {elev:.1f}°, pos {sun_pos:.2f}"
    log_msg += f" | base: {base_cct}K/{base_bri}% → adjusted: {cct}K/{bri}%"
    logger.info(log_msg)
    
    # Log color information
    logger.info(f"Color values: {cct}K, RGB({rgb[0]}, {rgb[1]}, {rgb[2]}), XY({xy_from_kelvin[0]:.4f}, {xy_from_kelvin[1]:.4f})")

    return {
        "color_temp": cct,  # Keep for backwards compatibility
        "kelvin": cct,
        "brightness": bri,
        "rgb": rgb,
        "xy": xy_from_kelvin,  # Use direct kelvin->xy conversion
        "sun_position": sun_pos
    }
