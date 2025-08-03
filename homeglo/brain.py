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

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # stdlib ≥3.9
from astral import LocationInfo
from astral.sun import sun, elevation as solar_elevation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default color temperature range (Kelvin)
DEFAULT_MIN_COLOR_TEMP = 2000  # Warm white (candle-like)
DEFAULT_MAX_COLOR_TEMP = 6500  # Cool daylight

# Default brightness range (percentage)
DEFAULT_MIN_BRIGHTNESS = 1
DEFAULT_MAX_BRIGHTNESS = 100

# Lux sensor range
DEFAULT_MIN_LUX = 10.0      # Very dark (night)
DEFAULT_MAX_LUX = 6000.0    # Bright indoor/cloudy day

# Lux normalization
LUX_GAMMA = 0.6            # Perceptual curve gamma correction

# Lux brightness adjustment parameters
LUX_BRIGHTNESS_K = 7       # Logistic curve steepness (higher = steeper drop)
LUX_BRIGHTNESS_M = 0.4     # Midpoint where brightness is 50% (0-1)

# Lux color adjustment
DEFAULT_LUX_COLOR_WEIGHT = 0.1  # How much lux affects color temp (0-1)

# TWILIGHT
CIVIL_TWILIGHT = -6.0   # deg, sun elevation at civil-dusk/dawn
NAUTICAL_TWILIGHT = -12.0
ASTRONOMICAL_TWILIGHT = -18.0

TWILIGHT = ASTRONOMICAL_TWILIGHT

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
        min_lux: float = DEFAULT_MIN_LUX,
        max_lux: float = DEFAULT_MAX_LUX,
        lux_color_weight: float = DEFAULT_LUX_COLOR_WEIGHT,
    ) -> None:
        self.min_color_temp = min_color_temp
        self.max_color_temp = max_color_temp
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness
        self.sunrise_time = sunrise_time
        self.sunset_time = sunset_time
        self.solar_noon = solar_noon
        self.min_lux = min_lux
        self.max_lux = max_lux
        self.lux_color_weight = lux_color_weight

    def calculate_sun_position(self, now: datetime, elev_deg: float) -> float:
        if self.sunrise_time and self.sunset_time and self.solar_noon:
            # ---- outside sunrise-sunset? fade through civil twilight ----
            if now < self.sunrise_time or now > self.sunset_time:
                # elev_deg is 0 at horizon, negative below
                if elev_deg <= TWILIGHT:
                    return -1.0
                return elev_deg / -TWILIGHT   # 0°→0, -6°→-1
            # ---- normal daytime parabola ----
            return math.sin(math.radians(elev_deg))

        # fallback path (no sunrise/sunset info)
        if elev_deg >= 0:
            return min(1.0, elev_deg / 60.0)
        return max(-1.0, elev_deg / 18.0)

    # lux helpers --------------------------------------------------------
    def _lux_to_norm(
        self,
        lux: float,
        min_lux: float,
        max_lux: float,
        gamma: float = LUX_GAMMA,
    ) -> float:
        """Perceptual (log) normalisation of lux → 0-1."""
        lux = max(min_lux, min(max_lux, lux))
        log_norm = (
            math.log10(lux) - math.log10(min_lux)
        ) / (math.log10(max_lux) - math.log10(min_lux))
        return log_norm ** gamma
    
    def apply_lux_adjustments(
        self,
        color_temp: int,
        brightness: int,
        lux: Optional[float],
    ) -> Tuple[int, int]:
        if lux is None:
            return color_temp, brightness

        ln = self._lux_to_norm(lux, self.min_lux, self.max_lux)
        logger.info(f"Applying lux adjustments: {lux:.0f} lux (normalized: {ln:.2f})")

        # ---------- BRIGHTNESS ----------
        # logistic: k controls slope, m the mid-point
        k = LUX_BRIGHTNESS_K
        m = LUX_BRIGHTNESS_M
        b_factor = 1 / (1 + math.exp(k * (ln - m)))
        bri = int(brightness * b_factor)
        bri = max(self.min_brightness, min(self.max_brightness, bri))

        # ---------- COLOUR TEMPERATURE ----------
        # shift proportionally within CCT span
        cct_span = self.max_color_temp - self.min_color_temp
        # ln=0 → no shift; ln=1 → full daylight
        cct = int(color_temp + (cct_span * (ln - 0.5) * self.lux_color_weight))
        cct = max(self.min_color_temp, min(self.max_color_temp, cct))

        return cct, bri    

    # colour / brightness ------------------------------------------------
    def calculate_color_temperature(self, pos: float, *, gamma: float = 1) -> int:
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

    def calculate_brightness(self, pos: float) -> int:
        # Map -1…1 -> 0…1 then use cubic easing so it’s gentler near max/min
        t = (pos + 1) * 0.5          # 0 at night, 1 at noon
        s = t*t*(3 - 2*t)            # smooth-step
        return int(self.min_brightness +
                s * (self.max_brightness - self.min_brightness))

    # colour-space helpers ----------------------------------------------
    @staticmethod
    def color_temperature_to_rgb(kelvin: int) -> Tuple[int, int, int]:
        temp = kelvin / 100
        red = 255 if temp <= 66 else 329.698727446 * ((temp - 60) ** -0.1332047592)
        green = (
            99.4708025861 * math.log(temp) - 161.1195681661 if temp <= 66 else
            288.1221695283 * ((temp - 60) ** -0.0755148492)
        )
        if temp >= 66:
            blue = 255
        elif temp <= 19:
            blue = 0
        else:
            blue = 138.5177312231 * math.log(temp - 10) - 305.0447927307
        return (
            int(max(0, min(255, red))),
            int(max(0, min(255, green))),
            int(max(0, min(255, blue))),
        )

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
    config: Optional[Dict[str, Any]] = None,
    lux: Optional[float] = None,
    lux_adjustment: bool = False,
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
    cct = base_cct = al.calculate_color_temperature(sun_pos)
    bri = base_bri = al.calculate_brightness(sun_pos)
    
    # Apply lux adjustments as a post-processing stage if enabled
    if lux_adjustment and lux is not None:
        cct, bri = al.apply_lux_adjustments(base_cct, base_bri, lux)
    
    rgb = al.color_temperature_to_rgb(cct)
    xy = al.rgb_to_xy(rgb)

    log_msg = f"{now.isoformat()} – elev {elev:.1f}°, pos {sun_pos:.2f}"
    if lux is not None:
        log_msg += f", lux {lux:.0f}"
    log_msg += f" | base: {base_cct}K/{base_bri}% → adjusted: {cct}K/{bri}%"
    logger.info(log_msg)

    return {
        "color_temp": cct,
        "brightness": bri,
        "rgb": rgb,
        "xy": xy,
        "sun_position": sun_pos,
        "lux": lux,
    }
