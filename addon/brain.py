#!/usr/bin/env python3
"""Brain module for adaptive lighting – self-contained, with Home Assistant fallbacks.

Key updates
-----------
* Simplified logistic curves without gain/offset/decay parameters
* Simplified brightness-based stepping matching JavaScript designer.html
* Direct parameter names matching JavaScript designer (mid_bri_up, steep_bri_up, etc.)
* Percentage-based stepping: step_size = (max - min) / steps
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
DEFAULT_MIN_BRIGHTNESS = int(os.getenv("MIN_BRIGHTNESS", "1"))
DEFAULT_MAX_BRIGHTNESS = int(os.getenv("MAX_BRIGHTNESS", "100"))

# Default dimming steps (for arc-based dimming)
DEFAULT_MAX_DIM_STEPS = int(os.getenv("MAX_DIM_STEPS", "10"))

# Gamma for perceptual brightness (default 0.62)
DEFAULT_GAMMA_UI = int(os.getenv("GAMMA_UI", "38"))  # UI value: 38 maps to gamma 0.62

# Morning curve parameters (simplified - only midpoint & steepness)
DEFAULT_MID_BRI_UP = 6.0       # Midpoint hours from solar midnight
DEFAULT_STEEP_BRI_UP = 1.5     # Steepness of curve

DEFAULT_MID_CCT_UP = 6.0       # Midpoint hours from solar midnight  
DEFAULT_STEEP_CCT_UP = 1.5     # Steepness of curve

# Evening curve parameters (simplified - only midpoint & steepness)
DEFAULT_MID_BRI_DN = 8.0       # Midpoint hours from solar noon
DEFAULT_STEEP_BRI_DN = 1.3     # Steepness of curve

DEFAULT_MID_CCT_DN = 8.0       # Midpoint hours from solar noon
DEFAULT_STEEP_CCT_DN = 1.3     # Steepness of curve

# Mirror flags (CCT follows brightness by default)
DEFAULT_MIRROR_UP = True
DEFAULT_MIRROR_DN = True

# ---------------------------------------------------------------------------
# Adaptive-lighting math (simplified)
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
        # Simplified morning parameters
        mid_bri_up: float = DEFAULT_MID_BRI_UP,
        steep_bri_up: float = DEFAULT_STEEP_BRI_UP,
        mid_cct_up: float = DEFAULT_MID_CCT_UP,
        steep_cct_up: float = DEFAULT_STEEP_CCT_UP,
        # Simplified evening parameters
        mid_bri_dn: float = DEFAULT_MID_BRI_DN,
        steep_bri_dn: float = DEFAULT_STEEP_BRI_DN,
        mid_cct_dn: float = DEFAULT_MID_CCT_DN,
        steep_cct_dn: float = DEFAULT_STEEP_CCT_DN,
        # Mirror flags
        mirror_up: bool = DEFAULT_MIRROR_UP,
        mirror_dn: bool = DEFAULT_MIRROR_DN,
        # Gamma for perceptual brightness
        gamma_ui: int = DEFAULT_GAMMA_UI,
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
        
        # Simplified morning parameters
        self.mid_bri_up = mid_bri_up
        self.steep_bri_up = steep_bri_up
        self.mid_cct_up = mid_cct_up if not mirror_up else mid_bri_up
        self.steep_cct_up = steep_cct_up if not mirror_up else steep_bri_up
        
        # Simplified evening parameters
        self.mid_bri_dn = mid_bri_dn
        self.steep_bri_dn = steep_bri_dn
        self.mid_cct_dn = mid_cct_dn if not mirror_dn else mid_bri_dn
        self.steep_cct_dn = steep_cct_dn if not mirror_dn else steep_bri_dn
        
        # Store mirror flags
        self.mirror_up = mirror_up
        self.mirror_dn = mirror_dn
        
        # Calculate gamma from UI value (0-100 maps to 1.0-0.0)
        self.gamma_b = (100 - gamma_ui) / 100.0

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
    
    def to_perceptual_brightness(self, brightness: float) -> float:
        """Convert linear brightness to perceptual using gamma."""
        normalized = max(0, min(100, brightness)) / 100.0
        return math.pow(normalized, self.gamma_b)
    
    def to_mired(self, kelvin: float) -> float:
        """Convert Kelvin to mireds for perceptual uniformity."""
        return 1e6 / max(500, min(6500, kelvin))
    
    @staticmethod
    def map_half(t: float, m: float, k: float, out_min: float, out_max: float, direction: int) -> float:
        """Simplified logistic mapping for morning/evening curves.
        
        Args:
            t: Time in solar hours (0-12 for morning, 12-24 for evening)
            m: Midpoint of the curve
            k: Steepness of the curve
            out_min: Minimum output value
            out_max: Maximum output value
            direction: +1 for morning (rises), -1 for evening (falls)
        """
        # Adjust time for evening calculation
        te = t if direction > 0 else (t - 12)
        
        # Calculate base logistic
        if direction > 0:
            # Morning: standard logistic
            base = 1 / (1 + math.exp(-k * (te - m)))
        else:
            # Evening: inverted logistic
            base = 1 - 1 / (1 + math.exp(-k * (te - m)))
        
        # Map to output range
        span = out_max - out_min
        return max(out_min, min(out_max, out_min + span * base))

    def calculate_color_temperature(self, now: datetime) -> int:
        """Calculate color temperature using simplified morning/evening curves."""
        solar_time = self.get_solar_time(now)
        
        if solar_time < 12:
            # Morning: use morning curve (solar midnight to solar noon)
            value = self.map_half(
                solar_time,
                self.mid_cct_up,
                self.steep_cct_up,
                self.min_color_temp,
                self.max_color_temp,
                direction=+1
            )
        else:
            # Evening: use evening curve (solar noon to solar midnight)
            value = self.map_half(
                solar_time,
                self.mid_cct_dn,
                self.steep_cct_dn,
                self.min_color_temp,
                self.max_color_temp,
                direction=-1
            )
        
        # Clamp to valid range
        return int(max(self.min_color_temp, min(self.max_color_temp, value)))

    def calculate_brightness(self, now: datetime) -> int:
        """Calculate brightness using simplified morning/evening curves."""
        solar_time = self.get_solar_time(now)
        
        if solar_time < 12:
            # Morning: use morning curve (solar midnight to solar noon)
            value = self.map_half(
                solar_time,
                self.mid_bri_up,
                self.steep_bri_up,
                self.min_brightness,
                self.max_brightness,
                direction=+1
            )
        else:
            # Evening: use evening curve (solar noon to solar midnight)
            value = self.map_half(
                solar_time,
                self.mid_bri_dn,
                self.steep_bri_dn,
                self.min_brightness,
                self.max_brightness,
                direction=-1
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
        
        This implements the simplified brightness-based stepping from designer.html:
        - Calculates step size as (max_brightness - min_brightness) / steps
        - Adds/subtracts step from current brightness
        - Finds the solar time that produces that brightness on the curve
        
        Args:
            now: Current time
            action: 'brighten' or 'dim'
            max_steps: Maximum number of steps from min to max brightness
            
        Returns:
            Tuple of (target_datetime, lighting_values_dict)
        """
        solar_time = self.get_solar_time(now)
        is_morning = solar_time < 12
        
        # Get current brightness and kelvin
        current_brightness = self.calculate_brightness(now)
        current_kelvin = self.calculate_color_temperature(now)

        # Calculate step size (matches JavaScript: brightnessStepSize function)
        step_size = (self.max_brightness - self.min_brightness) / max(1, min(500, max_steps))

        # Determine direction
        direction = 1 if action == 'brighten' else -1

        # Get curve boundaries to prevent stepping beyond plateaus
        boundaries = self.find_curve_boundaries()

        # Check if we're already at or past the meaningful boundaries
        tolerance = 0.1  # Small tolerance for floating point comparisons

        if direction < 0:  # Dimming/stepping down
            # Check if we're at minimum values (on the plateau)
            at_min_brightness = current_brightness <= self.min_brightness + tolerance
            at_min_kelvin = current_kelvin <= self.min_color_temp + tolerance

            # Check if we're past the solar time boundaries where curve plateaus
            if is_morning:
                past_boundary = solar_time <= boundaries.get('min_brightness_morning', 0) + 0.1
            else:
                past_boundary = solar_time >= boundaries.get('min_brightness_evening', 24) - 0.1

            if (at_min_brightness and at_min_kelvin) or past_boundary:
                logger.debug(f"Already at minimum boundary: brightness={current_brightness:.1f}%, kelvin={current_kelvin}K, solar_time={solar_time:.2f}h")
                return now, {
                    'kelvin': int(current_kelvin),
                    'brightness': int(current_brightness),
                    'rgb': self.color_temperature_to_rgb(int(current_kelvin)),
                    'xy': self.color_temperature_to_xy(int(current_kelvin)),
                    'solar_time': solar_time
                }

        elif direction > 0:  # Brightening/stepping up
            # Check if we're at maximum values (on the plateau)
            at_max_brightness = current_brightness >= self.max_brightness - tolerance
            at_max_kelvin = current_kelvin >= self.max_color_temp - tolerance

            # Check if we're past the solar time boundaries where curve plateaus
            if is_morning:
                past_boundary = solar_time >= boundaries.get('max_brightness_morning', 12) - 0.1
            else:
                past_boundary = solar_time <= boundaries.get('max_brightness_evening', 12) + 0.1

            if (at_max_brightness and at_max_kelvin) or past_boundary:
                logger.debug(f"Already at maximum boundary: brightness={current_brightness:.1f}%, kelvin={current_kelvin}K, solar_time={solar_time:.2f}h")
                return now, {
                    'kelvin': int(current_kelvin),
                    'brightness': int(current_brightness),
                    'rgb': self.color_temperature_to_rgb(int(current_kelvin)),
                    'xy': self.color_temperature_to_xy(int(current_kelvin)),
                    'solar_time': solar_time
                }

        # Calculate target brightness
        target_brightness = current_brightness + (direction * step_size)
        
        # Clamp target brightness to valid range
        target_brightness = max(self.min_brightness, min(self.max_brightness, target_brightness))
        
        # Find solar time that produces this brightness (matches findHourForBrightnessOnHalf)
        target_solar_time = self._find_solar_time_for_brightness(target_brightness, is_morning, direction)

        if target_solar_time is None:
            # Couldn't find matching time, use current
            target_solar_time = solar_time

        # Constrain target solar time to meaningful curve boundaries
        # This prevents stepping beyond the plateau points
        if direction < 0:  # Dimming
            if is_morning:
                min_boundary = boundaries.get('min_brightness_morning', 0)
                target_solar_time = max(target_solar_time, min_boundary)
            else:
                max_boundary = boundaries.get('min_brightness_evening', 24)
                target_solar_time = min(target_solar_time, max_boundary)
        else:  # Brightening
            if is_morning:
                max_boundary = boundaries.get('max_brightness_morning', 12)
                target_solar_time = min(target_solar_time, max_boundary)
            else:
                min_boundary = boundaries.get('max_brightness_evening', 12)
                target_solar_time = max(target_solar_time, min_boundary)
        
        # Calculate color temperature at target time
        if target_solar_time < 12:
            # Morning: use morning curve
            target_kelvin = self.map_half(
                target_solar_time, self.mid_cct_up, self.steep_cct_up,
                self.min_color_temp, self.max_color_temp, direction=+1
            )
        else:
            # Evening: use evening curve
            target_kelvin = self.map_half(
                target_solar_time, self.mid_cct_dn, self.steep_cct_dn,
                self.min_color_temp, self.max_color_temp, direction=-1
            )
        
        # Convert solar time back to real datetime
        hours_diff = target_solar_time - solar_time
        target_datetime = now + timedelta(hours=hours_diff)
        
        # Prepare lighting values
        target_kelvin = int(max(self.min_color_temp, min(self.max_color_temp, target_kelvin)))
        target_brightness = int(max(self.min_brightness, min(self.max_brightness, target_brightness)))
        
        logger.debug(f"Step calculation: current_brightness={current_brightness:.1f}%, target_brightness={target_brightness:.1f}%")
        logger.debug(f"Solar times: current={solar_time:.2f}h, target={target_solar_time:.2f}h")
        logger.debug(f"Final values: brightness={target_brightness}%, kelvin={target_kelvin}K")
        
        rgb = self.color_temperature_to_rgb(target_kelvin)
        xy = self.color_temperature_to_xy(target_kelvin)
        
        return target_datetime, {
            'kelvin': target_kelvin,
            'brightness': target_brightness,
            'rgb': rgb,
            'xy': xy,
            'solar_time': target_solar_time
        }
    
    def _find_solar_time_for_brightness(self, target_brightness: float, is_morning: bool,
                                        direction: int = 0) -> Optional[float]:
        """Find the solar time that produces the target brightness.

        This matches the JavaScript findHourForBrightnessOnHalf function.

        Args:
            target_brightness: Target brightness percentage
            is_morning: Whether to search morning (True) or evening (False) curve
            direction: Step direction (1 for brightening, -1 for dimming, 0 for closest)

        Returns:
            Solar time (0-24) that produces the target brightness, or None if not found
        """
        # Sample the appropriate curve
        samples = []
        sample_step = 0.05  # Fine sampling for accuracy
        
        if is_morning:
            # Sample morning curve (0 to 12)
            for t in [i * sample_step for i in range(int(12 / sample_step) + 1)]:
                brightness = self.map_half(
                    t, self.mid_bri_up, self.steep_bri_up,
                    self.min_brightness, self.max_brightness, direction=+1
                )
                samples.append((t, brightness))
        else:
            # Sample evening curve (12 to 24)
            for t in [12 + i * sample_step for i in range(int(12 / sample_step) + 1)]:
                brightness = self.map_half(
                    t, self.mid_bri_dn, self.steep_bri_dn,
                    self.min_brightness, self.max_brightness, direction=-1
                )
                samples.append((t, brightness))
        
        # Find the segment containing target brightness
        for i in range(1, len(samples)):
            t0, b0 = samples[i-1]
            t1, b1 = samples[i]
            
            # Check if target is between these two samples
            between = (b0 <= b1 and b0 <= target_brightness <= b1) or \
                     (b0 > b1 and b1 <= target_brightness <= b0)
            
            if between and abs(b1 - b0) > 1e-9:
                # Interpolate to find exact solar time
                interp = (target_brightness - b0) / (b1 - b0)
                target_time = t0 + interp * (t1 - t0)
                return target_time
        
        # If not found in curve, return appropriate endpoint based on direction
        # For morning: samples[0] is start (darkest), samples[-1] is end (brightest)
        # For evening: samples[0] is start (brightest), samples[-1] is end (darkest)

        if direction < 0:  # Dimming - prefer the darker end
            if is_morning:
                return samples[0][0]  # Morning start (darkest)
            else:
                return samples[-1][0]  # Evening end (darkest)
        elif direction > 0:  # Brightening - prefer the brighter end
            if is_morning:
                return samples[-1][0]  # Morning end (brightest)
            else:
                return samples[0][0]  # Evening start (brightest)
        else:  # No direction specified, use closest by brightness
            if abs(target_brightness - samples[0][1]) < abs(target_brightness - samples[-1][1]):
                return samples[0][0]
            else:
                return samples[-1][0]

    def find_curve_boundaries(self) -> Dict[str, float]:
        """Find the solar times where curves reach minimum/maximum values.

        This finds the 'plateau' points where stepping further won't change the lighting.

        Returns:
            Dict with keys: 'min_brightness_morning', 'min_brightness_evening',
                           'min_kelvin_morning', 'min_kelvin_evening',
                           'max_brightness_morning', 'max_brightness_evening',
                           'max_kelvin_morning', 'max_kelvin_evening'
        """
        boundaries = {}

        # Find minimum brightness points (where curve first reaches min_brightness)
        boundaries['min_brightness_morning'] = self._find_solar_time_for_brightness(
            self.min_brightness + 0.1, is_morning=True)  # Slight tolerance
        boundaries['min_brightness_evening'] = self._find_solar_time_for_brightness(
            self.min_brightness + 0.1, is_morning=False)

        # Find maximum brightness points
        boundaries['max_brightness_morning'] = self._find_solar_time_for_brightness(
            self.max_brightness - 0.1, is_morning=True)
        boundaries['max_brightness_evening'] = self._find_solar_time_for_brightness(
            self.max_brightness - 0.1, is_morning=False)

        # For color temperature, we need to sample and find plateaus
        # Morning: find where it reaches min kelvin
        for t in [i * 0.05 for i in range(int(12 / 0.05) + 1)]:
            kelvin = self.map_half(
                t, self.mid_cct_up, self.steep_cct_up,
                self.min_color_temp, self.max_color_temp, direction=+1
            )
            if kelvin <= self.min_color_temp + 1:  # Tolerance for floating point
                boundaries['min_kelvin_morning'] = t
                break
        else:
            boundaries['min_kelvin_morning'] = 0.0

        # Morning: find where it reaches max kelvin
        for t in [i * 0.05 for i in range(int(12 / 0.05) + 1)]:
            kelvin = self.map_half(
                t, self.mid_cct_up, self.steep_cct_up,
                self.min_color_temp, self.max_color_temp, direction=+1
            )
            if kelvin >= self.max_color_temp - 1:
                boundaries['max_kelvin_morning'] = t
                break
        else:
            boundaries['max_kelvin_morning'] = 12.0

        # Evening: find where it reaches min kelvin
        for t in [12 + i * 0.05 for i in range(int(12 / 0.05) + 1)]:
            kelvin = self.map_half(
                t, self.mid_cct_dn, self.steep_cct_dn,
                self.min_color_temp, self.max_color_temp, direction=-1
            )
            if kelvin <= self.min_color_temp + 1:
                boundaries['min_kelvin_evening'] = t
                break
        else:
            boundaries['min_kelvin_evening'] = 24.0

        # Evening: find where it reaches max kelvin
        for t in [12 + i * 0.05 for i in range(int(12 / 0.05) + 1)]:
            kelvin = self.map_half(
                t, self.mid_cct_dn, self.steep_cct_dn,
                self.min_color_temp, self.max_color_temp, direction=-1
            )
            if kelvin >= self.max_color_temp - 1:
                boundaries['max_kelvin_evening'] = t
                break
        else:
            boundaries['max_kelvin_evening'] = 12.0

        return boundaries

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
    min_color_temp: int = DEFAULT_MIN_COLOR_TEMP,
    max_color_temp: int = DEFAULT_MAX_COLOR_TEMP,
    min_brightness: int = DEFAULT_MIN_BRIGHTNESS,
    max_brightness: int = DEFAULT_MAX_BRIGHTNESS,
    # Simplified curve parameters (optional)
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Calculate the next dimming step along the adaptive curve.
    
    Args:
        current_time: Current time
        action: 'brighten' or 'dim'
        latitude: Location latitude
        longitude: Location longitude
        timezone: Timezone string
        max_steps: Maximum number of steps in the dimming arc
        min_color_temp: Minimum color temperature in Kelvin
        max_color_temp: Maximum color temperature in Kelvin
        min_brightness: Minimum brightness percentage
        max_brightness: Maximum brightness percentage
        config: Optional configuration dict with curve parameters
        
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

    # Prepare curve parameters from config
    kwargs = {
        "min_color_temp": min_color_temp,
        "max_color_temp": max_color_temp,
        "min_brightness": min_brightness,
        "max_brightness": max_brightness,
        "sunrise_time": solar_events["sunrise"],
        "sunset_time": solar_events["sunset"],
        "solar_noon": solar_noon,
        "solar_midnight": solar_midnight,
    }
    
    # Add simplified curve parameters from config if provided
    if config:
        for key in ["mid_bri_up", "steep_bri_up", "mid_cct_up", "steep_cct_up",
                   "mid_bri_dn", "steep_bri_dn", "mid_cct_dn", "steep_cct_dn",
                   "mirror_up", "mirror_dn", "gamma_ui"]:
            if key in config:
                kwargs[key] = config[key]

    al = AdaptiveLighting(**kwargs)
    
    # Calculate the step target
    target_time, lighting_values = al.calculate_step_target(now, action, max_steps)
    
    # Calculate time offset in minutes
    time_offset_minutes = (target_time - now).total_seconds() / 60
    
    logger.debug(f"Dimming step: {action} from {now.isoformat()} to {target_time.isoformat()}")
    logger.debug(f"Target values: {lighting_values['kelvin']}K, {lighting_values['brightness']}%")
    
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
    min_color_temp: int = DEFAULT_MIN_COLOR_TEMP,
    max_color_temp: int = DEFAULT_MAX_COLOR_TEMP,
    min_brightness: int = DEFAULT_MIN_BRIGHTNESS,
    max_brightness: int = DEFAULT_MAX_BRIGHTNESS,
    # Optional config with simplified curve parameters
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Compute adaptive-lighting values using simplified morning/evening curves.

    If *latitude*, *longitude* or *timezone* are omitted the function will try
    to pull them from the conventional Home Assistant env-vars.  Failing that
    it falls back to the system local timezone, and raises if lat/lon remain
    undefined.
    
    Args:
        min_color_temp: Minimum color temperature in Kelvin
        max_color_temp: Maximum color temperature in Kelvin
        min_brightness: Minimum brightness percentage
        max_brightness: Maximum brightness percentage
        config: Optional dict with curve parameters
    
    The config dict can contain: mid_bri_up, steep_bri_up, mid_cct_up, steep_cct_up,
                                 mid_bri_dn, steep_bri_dn, mid_cct_dn, steep_cct_dn,
                                 mirror_up, mirror_dn, gamma_ui
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

    # Prepare curve parameters (use provided config or defaults)
    kwargs = {
        "min_color_temp": min_color_temp,
        "max_color_temp": max_color_temp,
        "min_brightness": min_brightness,
        "max_brightness": max_brightness,
        "sunrise_time": solar_events["sunrise"],
        "sunset_time": solar_events["sunset"],
        "solar_noon": solar_noon,
        "solar_midnight": solar_midnight,
    }
    
    # Add simplified parameters from config if provided
    if config:
        for key in ["mid_bri_up", "steep_bri_up", "mid_cct_up", "steep_cct_up",
                   "mid_bri_dn", "steep_bri_dn", "mid_cct_dn", "steep_cct_dn",
                   "mirror_up", "mirror_dn", "gamma_ui"]:
            if key in config:
                kwargs[key] = config[key]

    al = AdaptiveLighting(**kwargs)

    sun_pos = al.calculate_sun_position(now, elev)
    solar_time = al.get_solar_time(now)
    
    # Use simplified curve methods
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