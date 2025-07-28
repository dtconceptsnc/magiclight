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
# Adaptive-lighting math (unchanged)
# ---------------------------------------------------------------------------

class AdaptiveLighting:
    """Calculate adaptive lighting values based on sun position."""

    def __init__(
        self,
        *,
        min_color_temp: int = 2000,
        max_color_temp: int = 5500,
        sleep_color_temp: int = 1000,
        min_brightness: int = 10,
        max_brightness: int = 100,
        sunrise_time: Optional[datetime] = None,
        sunset_time: Optional[datetime] = None,
        solar_noon: Optional[datetime] = None,
        adapt_until_sleep: bool = True,
        sleep_time: Optional[datetime] = None,
    ) -> None:
        self.min_color_temp = min_color_temp
        self.max_color_temp = max_color_temp
        self.sleep_color_temp = sleep_color_temp
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness
        self.sunrise_time = sunrise_time
        self.sunset_time = sunset_time
        self.solar_noon = solar_noon
        self.adapt_until_sleep = adapt_until_sleep
        self.sleep_time = sleep_time

    # position helpers -------------------------------------------------
    def _parabolic_position(self, now: datetime) -> float:
        if not (self.sunrise_time and self.sunset_time and self.solar_noon):
            raise ValueError("Sunrise/sunset/noon times must all be set")
        if now < self.sunrise_time:
            return -1.0
        if now > self.sunset_time:
            if self.adapt_until_sleep and self.sleep_time and now < self.sleep_time:
                span = (self.sleep_time - self.sunset_time).total_seconds()
                elap = (now - self.sunset_time).total_seconds()
                return -1.0 * (elap / span)
            return -1.0
        h = self.solar_noon.timestamp()
        x = (
            self.sunrise_time.timestamp()
            if now <= self.solar_noon
            else self.sunset_time.timestamp()
        )
        cur = now.timestamp()
        pos = 1 - ((cur - h) / (h - x)) ** 2
        return max(0.0, min(1.0, pos))

    def calculate_sun_position(self, now: datetime, elev_deg: float) -> float:
        if self.sunrise_time and self.sunset_time and self.solar_noon:
            return self._parabolic_position(now)
        if elev_deg >= 0:
            return min(1.0, elev_deg / 60.0)
        return max(-1.0, elev_deg / 18.0)

    # colour / brightness ------------------------------------------------
    def calculate_color_temperature(self, pos: float) -> int:
        if pos > 0:
            val = (self.max_color_temp - self.min_color_temp) * pos + self.min_color_temp
        elif self.adapt_until_sleep:
            val = abs(self.min_color_temp - self.sleep_color_temp) * abs(1 + pos) + self.sleep_color_temp
        else:
            val = self.min_color_temp
        return int(val)

    def calculate_brightness(self, pos: float) -> int:
        if pos > 0:
            return self.max_brightness
        val = (self.max_brightness - self.min_brightness) * (1 + pos) + self.min_brightness
        return int(max(self.min_brightness, min(self.max_brightness, val)))

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

    defaults = {
        "min_color_temp": 2000,
        "max_color_temp": 5500,
        "sleep_color_temp": 1000,
        "min_brightness": 10,
        "max_brightness": 100,
        "adapt_until_sleep": True,
    }
    if config:
        defaults.update(config)

    al = AdaptiveLighting(
        sunrise_time=solar_events["sunrise"],
        sunset_time=solar_events["sunset"],
        solar_noon=solar_events["noon"],
        **defaults,
    )

    sun_pos = al.calculate_sun_position(now, elev)
    cct = al.calculate_color_temperature(sun_pos)
    bri = al.calculate_brightness(sun_pos)
    rgb = al.color_temperature_to_rgb(cct)
    xy = al.rgb_to_xy(rgb)

    logger.debug("%s – elev %.1f°, pos %.2f, %d K, %d%%", now.isoformat(), elev, sun_pos, cct, bri)

    return {
        "color_temp": cct,
        "brightness": bri,
        "rgb": rgb,
        "xy": xy,
        "sun_position": sun_pos,
    }
