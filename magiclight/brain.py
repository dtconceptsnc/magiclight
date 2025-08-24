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
from datetime import datetime, timedelta
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

# Default dimming steps (for arc-based dimming)
DEFAULT_MAX_DIM_STEPS = int(os.getenv("MAX_DIM_STEPS", "8"))

# Morning curve parameters (defaults from HTML)
DEFAULT_MORNING_BRI_MID = 6.0       # Midpoint hours from solar midnight
DEFAULT_MORNING_BRI_STEEP = 1.0     # Steepness of curve
DEFAULT_MORNING_BRI_DECAY = 0.02    # Decay around noon
DEFAULT_MORNING_BRI_GAIN = 1.0      # Gain multiplier
DEFAULT_MORNING_BRI_OFFSET = 0      # Brightness offset

DEFAULT_MORNING_CCT_MID = 6.0       # Midpoint hours from solar midnight
DEFAULT_MORNING_CCT_STEEP = 1.0     # Steepness of curve
DEFAULT_MORNING_CCT_DECAY = 0.02    # Decay around noon
DEFAULT_MORNING_CCT_GAIN = 1.0      # Gain multiplier
DEFAULT_MORNING_CCT_OFFSET = 0      # Color temp offset

# Evening curve parameters (defaults from HTML)
DEFAULT_EVENING_BRI_MID = 6.0       # Midpoint hours from solar noon
DEFAULT_EVENING_BRI_STEEP = 1.0     # Steepness of curve
DEFAULT_EVENING_BRI_DECAY = 0.02    # Decay around noon
DEFAULT_EVENING_BRI_GAIN = 1.0      # Gain multiplier
DEFAULT_EVENING_BRI_OFFSET = 0      # Brightness offset

DEFAULT_EVENING_CCT_MID = 6.0       # Midpoint hours from solar noon
DEFAULT_EVENING_CCT_STEEP = 1.0     # Steepness of curve
DEFAULT_EVENING_CCT_DECAY = 0.02    # Decay around noon
DEFAULT_EVENING_CCT_GAIN = 3.0      # Gain multiplier
DEFAULT_EVENING_CCT_OFFSET = 0      # Color temp offset

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
        solar_midnight: Optional[datetime] = None,
        color_mode: ColorMode = ColorMode.KELVIN,
        # Morning brightness curve parameters
        morning_bri_mid: float = DEFAULT_MORNING_BRI_MID,
        morning_bri_steep: float = DEFAULT_MORNING_BRI_STEEP,
        morning_bri_decay: float = DEFAULT_MORNING_BRI_DECAY,
        morning_bri_gain: float = DEFAULT_MORNING_BRI_GAIN,
        morning_bri_offset: float = DEFAULT_MORNING_BRI_OFFSET,
        # Morning CCT curve parameters
        morning_cct_mid: float = DEFAULT_MORNING_CCT_MID,
        morning_cct_steep: float = DEFAULT_MORNING_CCT_STEEP,
        morning_cct_decay: float = DEFAULT_MORNING_CCT_DECAY,
        morning_cct_gain: float = DEFAULT_MORNING_CCT_GAIN,
        morning_cct_offset: float = DEFAULT_MORNING_CCT_OFFSET,
        # Evening brightness curve parameters
        evening_bri_mid: float = DEFAULT_EVENING_BRI_MID,
        evening_bri_steep: float = DEFAULT_EVENING_BRI_STEEP,
        evening_bri_decay: float = DEFAULT_EVENING_BRI_DECAY,
        evening_bri_gain: float = DEFAULT_EVENING_BRI_GAIN,
        evening_bri_offset: float = DEFAULT_EVENING_BRI_OFFSET,
        # Evening CCT curve parameters
        evening_cct_mid: float = DEFAULT_EVENING_CCT_MID,
        evening_cct_steep: float = DEFAULT_EVENING_CCT_STEEP,
        evening_cct_decay: float = DEFAULT_EVENING_CCT_DECAY,
        evening_cct_gain: float = DEFAULT_EVENING_CCT_GAIN,
        evening_cct_offset: float = DEFAULT_EVENING_CCT_OFFSET,
    ) -> None:
        self.min_color_temp = min_color_temp
        self.max_color_temp = max_color_temp
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness
        self.sunrise_time = sunrise_time
        self.sunset_time = sunset_time
        self.solar_noon = solar_noon
        self.solar_midnight = solar_midnight
        self.color_mode = color_mode
        
        # Morning curve parameters
        self.morning_bri_mid = morning_bri_mid
        self.morning_bri_steep = morning_bri_steep
        self.morning_bri_decay = morning_bri_decay
        self.morning_bri_gain = morning_bri_gain
        self.morning_bri_offset = morning_bri_offset
        
        self.morning_cct_mid = morning_cct_mid
        self.morning_cct_steep = morning_cct_steep
        self.morning_cct_decay = morning_cct_decay
        self.morning_cct_gain = morning_cct_gain
        self.morning_cct_offset = morning_cct_offset
        
        # Evening curve parameters
        self.evening_bri_mid = evening_bri_mid
        self.evening_bri_steep = evening_bri_steep
        self.evening_bri_decay = evening_bri_decay
        self.evening_bri_gain = evening_bri_gain
        self.evening_bri_offset = evening_bri_offset
        
        self.evening_cct_mid = evening_cct_mid
        self.evening_cct_steep = evening_cct_steep
        self.evening_cct_decay = evening_cct_decay
        self.evening_cct_gain = evening_cct_gain
        self.evening_cct_offset = evening_cct_offset

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
    
    def get_solar_time(self, now: datetime) -> float:
        """Get the current time in solar hours (0-24 where 0 is solar midnight, 12 is solar noon)."""
        if self.solar_midnight and self.solar_noon:
            # Calculate hours from solar midnight
            hours_from_midnight = (now - self.solar_midnight).total_seconds() / 3600
            # Wrap to 0-24 range
            return hours_from_midnight % 24
        elif self.solar_noon:
            # Calculate from solar noon if midnight not available
            hours_from_noon = (now - self.solar_noon).total_seconds() / 3600
            return (hours_from_noon + 12) % 24
        else:
            # Fallback to regular time
            return now.hour + now.minute / 60
    
    @staticmethod
    def logistic_up(t: float, m: float, k: float) -> float:
        """Logistic function for morning curves."""
        return 1 / (1 + math.exp(-k * (t - m)))
    
    @staticmethod
    def decay_around_noon(t: float, alpha: float) -> float:
        """Decay function centered around solar noon (t=12)."""
        return math.exp(-alpha * (t - 12) ** 2)
    
    def map_morning(self, t: float, m: float, k: float, alpha: float, gain: float, 
                   offset: float, out_min: float, out_max: float) -> float:
        """Map morning time to value using logistic curve with decay."""
        base = self.logistic_up(t, m, k) * self.decay_around_noon(t, alpha)
        scaled = max(0, min(1, base * gain))
        y = out_min + (out_max - out_min) * scaled
        y += offset
        return y
    
    def map_evening(self, t: float, m: float, k: float, alpha: float, gain: float,
                   offset: float, out_min: float, out_max: float) -> float:
        """Map evening time to value using inverted logistic curve with decay."""
        te = t - 12  # Shift time for evening calculation
        base = (1 - self.logistic_up(te, m, k)) * self.decay_around_noon(t, alpha)
        scaled = max(0, min(1, base * gain))
        y = out_min + (out_max - out_min) * scaled
        y += offset
        return y

    # colour / brightness ------------------------------------------------
    def calculate_color_temperature(self, now: datetime) -> int:
        """Calculate color temperature using morning/evening curves based on solar time."""
        solar_time = self.get_solar_time(now)
        
        if solar_time < 12:
            # Morning: use morning curve (solar midnight to solar noon)
            value = self.map_morning(
                solar_time,
                self.morning_cct_mid,
                self.morning_cct_steep,
                self.morning_cct_decay,
                self.morning_cct_gain,
                self.morning_cct_offset,
                self.min_color_temp,
                self.max_color_temp
            )
        else:
            # Evening: use evening curve (solar noon to solar midnight)
            value = self.map_evening(
                solar_time,
                self.evening_cct_mid,
                self.evening_cct_steep,
                self.evening_cct_decay,
                self.evening_cct_gain,
                self.evening_cct_offset,
                self.min_color_temp,
                self.max_color_temp
            )
        
        # Clamp to valid range
        return int(max(self.min_color_temp, min(self.max_color_temp, value)))

    def calculate_brightness(self, now: datetime) -> int:
        """Calculate brightness using morning/evening curves based on solar time."""
        solar_time = self.get_solar_time(now)
        
        if solar_time < 12:
            # Morning: use morning curve (solar midnight to solar noon)
            value = self.map_morning(
                solar_time,
                self.morning_bri_mid,
                self.morning_bri_steep,
                self.morning_bri_decay,
                self.morning_bri_gain,
                self.morning_bri_offset,
                self.min_brightness,
                self.max_brightness
            )
        else:
            # Evening: use evening curve (solar noon to solar midnight)
            value = self.map_evening(
                solar_time,
                self.evening_bri_mid,
                self.evening_bri_steep,
                self.evening_bri_decay,
                self.evening_bri_gain,
                self.evening_bri_offset,
                self.min_brightness,
                self.max_brightness
            )
        
        # Clamp to valid range
        return int(max(self.min_brightness, min(self.max_brightness, value)))

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
    
    def calculate_step_target(self, now: datetime, action: str = 'brighten', 
                            max_steps: int = DEFAULT_MAX_DIM_STEPS) -> Tuple[datetime, Dict[str, Any]]:
        """Calculate target time and lighting values for dim/brighten step.
        
        This implements the arc-based stepping algorithm from the designer:
        - Builds an arc through the day's lighting curve
        - Steps along this arc maintaining perceptual consistency
        - Ensures smooth transitions that feel natural
        
        Args:
            now: Current time
            action: 'brighten' or 'dim'
            max_steps: Maximum number of steps in the arc (default 15)
            
        Returns:
            Tuple of (target_datetime, lighting_values_dict)
        """
        solar_time = self.get_solar_time(now)
        is_morning = solar_time < 12
        
        # Calculate arc for the current half-day
        # Morning: solar midnight to solar noon
        # Evening: solar noon to solar midnight
        
        # Sample the curve to build arc
        samples = []
        sample_step = 0.1  # Sample every 0.1 solar hours
        
        if is_morning:
            # Sample from midnight to noon
            for t in [i * sample_step for i in range(int(12 / sample_step) + 1)]:
                samples.append({
                    'solar_time': t,
                    'brightness': self.map_morning(
                        t, self.morning_bri_mid, self.morning_bri_steep,
                        self.morning_bri_decay, self.morning_bri_gain,
                        self.morning_bri_offset, self.min_brightness, self.max_brightness
                    ),
                    'kelvin': self.map_morning(
                        t, self.morning_cct_mid, self.morning_cct_steep,
                        self.morning_cct_decay, self.morning_cct_gain,
                        self.morning_cct_offset, self.min_color_temp, self.max_color_temp
                    )
                })
        else:
            # Sample from noon to midnight
            for t in [12 + i * sample_step for i in range(int(12 / sample_step) + 1)]:
                samples.append({
                    'solar_time': t,
                    'brightness': self.map_evening(
                        t, self.evening_bri_mid, self.evening_bri_steep,
                        self.evening_bri_decay, self.evening_bri_gain,
                        self.evening_bri_offset, self.min_brightness, self.max_brightness
                    ),
                    'kelvin': self.map_evening(
                        t, self.evening_cct_mid, self.evening_cct_steep,
                        self.evening_cct_decay, self.evening_cct_gain,
                        self.evening_cct_offset, self.min_color_temp, self.max_color_temp
                    )
                })
        
        # Build arc with weighted distances
        # Normalize values for distance calculation
        bmin, bmax = self.min_brightness, self.max_brightness
        kmin, kmax = self.min_color_temp, self.max_color_temp
        
        # Convert kelvin to mireds for perceptual uniformity
        def to_mired(k):
            return 1e6 / k if k > 0 else 0
        
        mired_min = to_mired(kmax)
        mired_max = to_mired(kmin)
        
        # Build arc distances
        arc_distances = [0]
        for i in range(1, len(samples)):
            # Normalized brightness difference
            b_norm_prev = (samples[i-1]['brightness'] - bmin) / max(1e-9, bmax - bmin)
            b_norm_curr = (samples[i]['brightness'] - bmin) / max(1e-9, bmax - bmin)
            db = b_norm_curr - b_norm_prev
            
            # Normalized mired difference
            m_prev = to_mired(samples[i-1]['kelvin'])
            m_curr = to_mired(samples[i]['kelvin'])
            m_norm_prev = (m_prev - mired_min) / max(1e-9, mired_max - mired_min)
            m_norm_curr = (m_curr - mired_min) / max(1e-9, mired_max - mired_min)
            dm = m_norm_curr - m_norm_prev
            
            # Weighted distance (brightness weight = 1.0, color weight = 0.6)
            distance = math.sqrt(1.0 * db**2 + 0.6 * dm**2)
            arc_distances.append(arc_distances[-1] + distance)
        
        total_arc_length = arc_distances[-1]
        
        # Find current position on arc
        current_idx = 0
        min_diff = float('inf')
        for i, sample in enumerate(samples):
            diff = abs(sample['solar_time'] - solar_time)
            if diff < min_diff:
                min_diff = diff
                current_idx = i
        
        # Interpolate to get exact arc position
        if current_idx < len(samples) - 1:
            t_curr = samples[current_idx]['solar_time']
            t_next = samples[current_idx + 1]['solar_time']
            if t_next > t_curr:
                interp = (solar_time - t_curr) / (t_next - t_curr)
                current_arc_pos = arc_distances[current_idx] + \
                    interp * (arc_distances[current_idx + 1] - arc_distances[current_idx])
            else:
                current_arc_pos = arc_distances[current_idx]
        else:
            current_arc_pos = arc_distances[current_idx]
        
        # Calculate step size
        step_size = total_arc_length / max_steps if max_steps > 0 else total_arc_length / 15
        
        # Determine step direction
        # Morning: brighten = forward (toward noon), dim = backward (toward midnight)
        # Evening: brighten = backward (toward noon), dim = forward (toward midnight)
        if is_morning:
            step_dir = step_size if action == 'brighten' else -step_size
        else:
            step_dir = -step_size if action == 'brighten' else step_size
        
        # Calculate target arc position
        target_arc_pos = current_arc_pos + step_dir
        target_arc_pos = max(0, min(total_arc_length, target_arc_pos))
        
        # Find target sample index and interpolation
        target_idx = 0
        for i in range(len(arc_distances) - 1):
            if arc_distances[i] <= target_arc_pos <= arc_distances[i + 1]:
                target_idx = i
                break
        
        # Interpolate to find target solar time, then recalculate values from curves
        if target_idx < len(samples) - 1 and arc_distances[target_idx + 1] > arc_distances[target_idx]:
            interp = (target_arc_pos - arc_distances[target_idx]) / \
                    (arc_distances[target_idx + 1] - arc_distances[target_idx])
            target_solar_time = samples[target_idx]['solar_time'] + \
                interp * (samples[target_idx + 1]['solar_time'] - samples[target_idx]['solar_time'])
        else:
            target_solar_time = samples[target_idx]['solar_time']
        
        # Recalculate brightness and kelvin from the actual curves at target_solar_time
        # This ensures smooth transitions without interpolation artifacts
        if target_solar_time < 12:
            # Morning: use morning curves
            target_brightness = self.map_morning(
                target_solar_time, self.morning_bri_mid, self.morning_bri_steep,
                self.morning_bri_decay, self.morning_bri_gain,
                self.morning_bri_offset, self.min_brightness, self.max_brightness
            )
            target_kelvin = self.map_morning(
                target_solar_time, self.morning_cct_mid, self.morning_cct_steep,
                self.morning_cct_decay, self.morning_cct_gain,
                self.morning_cct_offset, self.min_color_temp, self.max_color_temp
            )
        else:
            # Evening: use evening curves
            target_brightness = self.map_evening(
                target_solar_time, self.evening_bri_mid, self.evening_bri_steep,
                self.evening_bri_decay, self.evening_bri_gain,
                self.evening_bri_offset, self.min_brightness, self.max_brightness
            )
            target_kelvin = self.map_evening(
                target_solar_time, self.evening_cct_mid, self.evening_cct_steep,
                self.evening_cct_decay, self.evening_cct_gain,
                self.evening_cct_offset, self.min_color_temp, self.max_color_temp
            )
        
        # Convert solar time back to real datetime
        hours_diff = target_solar_time - solar_time
        target_datetime = now + timedelta(hours=hours_diff)
        
        # Prepare lighting values
        target_kelvin = int(max(self.min_color_temp, min(self.max_color_temp, target_kelvin)))
        target_brightness = int(max(self.min_brightness, min(self.max_brightness, target_brightness)))
        
        rgb = self.color_temperature_to_rgb(target_kelvin)
        xy = self.color_temperature_to_xy(target_kelvin)
        
        return target_datetime, {
            'kelvin': target_kelvin,
            'brightness': target_brightness,
            'rgb': rgb,
            'xy': xy,
            'solar_time': target_solar_time
        }

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

def calculate_dimming_step(
    current_time: datetime,
    action: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    timezone: Optional[str] = None,
    max_steps: int = DEFAULT_MAX_DIM_STEPS,
    # Allow overriding curve parameters (optional)
    morning_bri_params: Optional[Dict[str, float]] = None,
    morning_cct_params: Optional[Dict[str, float]] = None,
    evening_bri_params: Optional[Dict[str, float]] = None,
    evening_cct_params: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """Calculate the next dimming step along the adaptive curve.
    
    Args:
        current_time: Current time
        action: 'brighten' or 'dim'
        latitude: Location latitude
        longitude: Location longitude
        timezone: Timezone string
        max_steps: Maximum number of steps in the dimming arc
        *_params: Optional curve parameter overrides
        
    Returns:
        Dict with target lighting values and time offset
    """
    latitude, longitude, timezone = _auto_location(latitude, longitude, timezone)
    if latitude is None or longitude is None:
        raise ValueError("Latitude/longitude not provided and not found in env vars")

    try:
        tzinfo = ZoneInfo(timezone) if timezone else None
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone '%s' – falling back to system local", timezone)
        tzinfo = None

    now = current_time.astimezone(tzinfo) if tzinfo else current_time

    loc = LocationInfo(latitude=latitude, longitude=longitude, timezone=tzinfo or "UTC")
    observer = loc.observer
    solar_events = sun(observer, date=now.date(), tzinfo=loc.timezone)
    
    # Calculate solar midnight
    solar_noon = solar_events["noon"]
    solar_midnight = solar_noon - timedelta(hours=12) if solar_noon.hour >= 12 else solar_noon + timedelta(hours=12)

    # Prepare curve parameters
    kwargs = {
        "sunrise_time": solar_events["sunrise"],
        "sunset_time": solar_events["sunset"],
        "solar_noon": solar_noon,
        "solar_midnight": solar_midnight,
    }
    
    # Add curve parameters if provided
    if morning_bri_params:
        kwargs.update({f"morning_bri_{k}": v for k, v in morning_bri_params.items()
                      if k in ["mid", "steep", "decay", "gain", "offset"]})
    if morning_cct_params:
        kwargs.update({f"morning_cct_{k}": v for k, v in morning_cct_params.items()
                      if k in ["mid", "steep", "decay", "gain", "offset"]})
    if evening_bri_params:
        kwargs.update({f"evening_bri_{k}": v for k, v in evening_bri_params.items()
                      if k in ["mid", "steep", "decay", "gain", "offset"]})
    if evening_cct_params:
        kwargs.update({f"evening_cct_{k}": v for k, v in evening_cct_params.items()
                      if k in ["mid", "steep", "decay", "gain", "offset"]})

    al = AdaptiveLighting(**kwargs)
    
    # Calculate the step target
    target_time, lighting_values = al.calculate_step_target(now, action, max_steps)
    
    # Calculate time offset in minutes
    time_offset_minutes = (target_time - now).total_seconds() / 60
    
    logger.info(f"Dimming step: {action} from {now.isoformat()} to {target_time.isoformat()}")
    logger.info(f"Target values: {lighting_values['kelvin']}K, {lighting_values['brightness']}%")
    
    return {
        **lighting_values,
        'time_offset_minutes': time_offset_minutes,
        'target_time': target_time
    }

def get_adaptive_lighting(
    *,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    timezone: Optional[str] = None,
    current_time: Optional[datetime] = None,
    # Allow overriding curve parameters (optional)
    morning_bri_params: Optional[Dict[str, float]] = None,
    morning_cct_params: Optional[Dict[str, float]] = None,
    evening_bri_params: Optional[Dict[str, float]] = None,
    evening_cct_params: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """Compute adaptive-lighting values using morning/evening curves.

    If *latitude*, *longitude* or *timezone* are omitted the function will try
    to pull them from the conventional Home Assistant env-vars.  Failing that
    it falls back to the system local timezone, and raises if lat/lon remain
    undefined.
    
    The optional curve parameter dicts can contain: mid, steep, decay, gain, offset
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

    # Calculate solar midnight (opposite of solar noon)
    solar_noon = solar_events["noon"]
    solar_midnight = solar_noon - timedelta(hours=12) if solar_noon.hour >= 12 else solar_noon + timedelta(hours=12)

    # Prepare curve parameters (use provided or defaults)
    kwargs = {
        "sunrise_time": solar_events["sunrise"],
        "sunset_time": solar_events["sunset"],
        "solar_noon": solar_noon,
        "solar_midnight": solar_midnight,
    }
    
    # Add morning brightness parameters if provided
    if morning_bri_params:
        kwargs.update({
            f"morning_bri_{k}": v for k, v in morning_bri_params.items()
            if k in ["mid", "steep", "decay", "gain", "offset"]
        })
    
    # Add morning CCT parameters if provided
    if morning_cct_params:
        kwargs.update({
            f"morning_cct_{k}": v for k, v in morning_cct_params.items()
            if k in ["mid", "steep", "decay", "gain", "offset"]
        })
    
    # Add evening brightness parameters if provided
    if evening_bri_params:
        kwargs.update({
            f"evening_bri_{k}": v for k, v in evening_bri_params.items()
            if k in ["mid", "steep", "decay", "gain", "offset"]
        })
    
    # Add evening CCT parameters if provided
    if evening_cct_params:
        kwargs.update({
            f"evening_cct_{k}": v for k, v in evening_cct_params.items()
            if k in ["mid", "steep", "decay", "gain", "offset"]
        })

    al = AdaptiveLighting(**kwargs)

    sun_pos = al.calculate_sun_position(now, elev)
    solar_time = al.get_solar_time(now)
    
    # Use new morning/evening curve methods (they take datetime now)
    cct = al.calculate_color_temperature(now)
    bri = al.calculate_brightness(now)
    
    # Calculate all color representations
    rgb = al.color_temperature_to_rgb(cct)
    xy_from_kelvin = al.color_temperature_to_xy(cct)

    log_msg = f"{now.isoformat()} – elev {elev:.1f}°, solar_time {solar_time:.2f}h"
    log_msg += f" | lighting: {cct}K/{bri}%"
    logger.info(log_msg)
    
    # Log color information
    logger.info(f"Color values: {cct}K, RGB({rgb[0]}, {rgb[1]}, {rgb[2]}), XY({xy_from_kelvin[0]:.4f}, {xy_from_kelvin[1]:.4f})")

    return {
        "color_temp": cct,  # Keep for backwards compatibility
        "kelvin": cct,
        "brightness": bri,
        "rgb": rgb,
        "xy": xy_from_kelvin,  # Use direct kelvin->xy conversion
        "sun_position": sun_pos,
        "solar_time": solar_time
    }
