#!/usr/bin/env python3
"""Brain module for calculating color temperature based on sun position."""

import math
from datetime import datetime
from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class AdaptiveLighting:
    """Calculate adaptive lighting based on sun position."""
    
    def __init__(
        self,
        min_color_temp: int = 2000,  # Warm white
        max_color_temp: int = 5500,  # Cool white
        sleep_color_temp: int = 1000,  # Very warm for sleep
        min_brightness: int = 10,
        max_brightness: int = 100,
        sunrise_time: Optional[datetime] = None,
        sunset_time: Optional[datetime] = None,
        solar_noon: Optional[datetime] = None,
        adapt_until_sleep: bool = True,
        sleep_time: Optional[datetime] = None
    ):
        """Initialize adaptive lighting calculator.
        
        Args:
            min_color_temp: Minimum color temperature in Kelvin (warmest)
            max_color_temp: Maximum color temperature in Kelvin (coolest)
            sleep_color_temp: Color temperature for sleep mode
            min_brightness: Minimum brightness percentage
            max_brightness: Maximum brightness percentage
            sunrise_time: Today's sunrise time
            sunset_time: Today's sunset time
            solar_noon: Today's solar noon time
            adapt_until_sleep: Continue adapting color temp after sunset
            sleep_time: Time to start sleep mode
        """
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
        
    def calculate_sun_position(self, current_time: datetime, sun_data: Dict) -> float:
        """Calculate sun position based on time and sun data.
        
        Args:
            current_time: Current time
            sun_data: Dictionary with sun data from Home Assistant
            
        Returns:
            Sun position value between -1 and 1
        """
        # Extract sun data
        elevation = sun_data.get('elevation', 0)
        
        # Parse sunrise/sunset times if provided in sun_data
        if 'next_rising' in sun_data and 'next_setting' in sun_data:
            # These might be ISO format strings from HA
            try:
                from dateutil import parser
                next_rising = parser.parse(sun_data['next_rising']) if isinstance(sun_data['next_rising'], str) else sun_data['next_rising']
                next_setting = parser.parse(sun_data['next_setting']) if isinstance(sun_data['next_setting'], str) else sun_data['next_setting']
                
                # Determine today's sunrise/sunset based on next times
                if next_rising.date() == current_time.date():
                    self.sunrise_time = next_rising
                else:
                    # Next rising is tomorrow, so sunrise was earlier today
                    self.sunrise_time = next_rising - datetime.timedelta(days=1)
                    
                if next_setting.date() == current_time.date() and next_setting > current_time:
                    self.sunset_time = next_setting
                else:
                    # Setting already happened today
                    self.sunset_time = next_setting if next_setting < current_time else next_setting - datetime.timedelta(days=1)
                    
                # Estimate solar noon as midpoint
                if self.sunrise_time and self.sunset_time:
                    sunrise_today = self.sunrise_time if self.sunrise_time.date() == current_time.date() else self.sunrise_time + datetime.timedelta(days=1)
                    sunset_today = self.sunset_time if self.sunset_time.date() == current_time.date() else self.sunset_time + datetime.timedelta(days=1)
                    if sunrise_today < sunset_today:
                        self.solar_noon = sunrise_today + (sunset_today - sunrise_today) / 2
            except:
                pass
        
        # Alternative calculation if we have sunrise/sunset times
        if self.sunrise_time and self.sunset_time and self.solar_noon:
            if current_time < self.sunrise_time:
                # Before sunrise
                return -1.0
            elif current_time > self.sunset_time:
                # After sunset
                if self.adapt_until_sleep and self.sleep_time and current_time < self.sleep_time:
                    # Calculate position between sunset and sleep time
                    total_duration = (self.sleep_time - self.sunset_time).total_seconds()
                    elapsed = (current_time - self.sunset_time).total_seconds()
                    return -1.0 * (elapsed / total_duration)
                return -1.0
            else:
                # During day - calculate parabolic position
                # h = solar noon, x = sunrise/sunset
                h = self.solar_noon
                if current_time <= h:
                    x = self.sunrise_time
                else:
                    x = self.sunset_time
                    
                h_seconds = h.timestamp()
                x_seconds = x.timestamp()
                current_seconds = current_time.timestamp()
                
                # Parabolic formula: k * (1 - ((current_time - h) / (h - x))²)
                if h_seconds != x_seconds:
                    position = 1 - ((current_seconds - h_seconds) / (h_seconds - x_seconds)) ** 2
                else:
                    position = 1.0
                    
                return max(0, min(1, position))
        
        # Elevation-based calculation - more accurate for current time
        # At 17:49 in winter, sun is likely below horizon or very low
        if elevation is not None:
            if elevation > 0:
                # Sun above horizon, normalize to 0-1
                # Max elevation is ~90 at equator, but more like 60-70 in most places
                return min(1.0, elevation / 60.0)
            else:
                # Sun below horizon, normalize to -1-0
                # Civil twilight ends at -6 degrees, we'll use -18 for full darkness
                return max(-1.0, elevation / 18.0)
            
    def calculate_color_temperature(self, sun_position: float) -> int:
        """Calculate color temperature based on sun position.
        
        Args:
            sun_position: Sun position between -1 and 1
            
        Returns:
            Color temperature in Kelvin
        """
        if sun_position > 0:
            # Sun above horizon - interpolate between min and max
            color_temp = (self.max_color_temp - self.min_color_temp) * sun_position + self.min_color_temp
        elif self.adapt_until_sleep:
            # Sun below horizon but adapting until sleep
            # Interpolate between min_temp and sleep_temp
            color_temp = abs(self.min_color_temp - self.sleep_color_temp) * abs(1 + sun_position) + self.sleep_color_temp
        else:
            # Sun below horizon, use minimum temperature
            color_temp = self.min_color_temp
            
        return int(color_temp)
        
    def calculate_brightness(self, sun_position: float) -> int:
        """Calculate brightness based on sun position.
        
        Args:
            sun_position: Sun position between -1 and 1
            
        Returns:
            Brightness percentage (0-100)
        """
        if sun_position > 0:
            # Sun above horizon - use max brightness
            brightness = self.max_brightness
        else:
            # Sun below horizon - interpolate
            brightness = (self.max_brightness - self.min_brightness) * (1 + sun_position) + self.min_brightness
            
        return int(max(self.min_brightness, min(self.max_brightness, brightness)))
        
    def color_temperature_to_rgb(self, kelvin: int) -> Tuple[int, int, int]:
        """Convert color temperature to RGB.
        
        Args:
            kelvin: Color temperature in Kelvin
            
        Returns:
            RGB tuple (0-255 for each component)
        """
        # Normalize kelvin to 0-255 range
        temp = kelvin / 100
        
        # Calculate red
        if temp <= 66:
            red = 255
        else:
            red = temp - 60
            red = 329.698727446 * (red ** -0.1332047592)
            red = max(0, min(255, red))
            
        # Calculate green
        if temp <= 66:
            green = temp
            green = 99.4708025861 * math.log(green) - 161.1195681661
        else:
            green = temp - 60
            green = 288.1221695283 * (green ** -0.0755148492)
        green = max(0, min(255, green))
        
        # Calculate blue
        if temp >= 66:
            blue = 255
        elif temp <= 19:
            blue = 0
        else:
            blue = temp - 10
            blue = 138.5177312231 * math.log(blue) - 305.0447927307
            blue = max(0, min(255, blue))
            
        return (int(red), int(green), int(blue))
        
    def rgb_to_xy(self, rgb: Tuple[int, int, int]) -> Tuple[float, float]:
        """Convert RGB to XY color space (for Philips Hue, etc).
        
        Args:
            rgb: RGB tuple (0-255 for each component)
            
        Returns:
            XY tuple
        """
        # Normalize RGB values
        r = rgb[0] / 255.0
        g = rgb[1] / 255.0
        b = rgb[2] / 255.0
        
        # Apply gamma correction
        r = ((r + 0.055) / 1.055) ** 2.4 if r > 0.04045 else r / 12.92
        g = ((g + 0.055) / 1.055) ** 2.4 if g > 0.04045 else g / 12.92
        b = ((b + 0.055) / 1.055) ** 2.4 if b > 0.04045 else b / 12.92
        
        # Convert to XYZ
        X = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
        Y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
        Z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
        
        # Convert to xy
        if X + Y + Z == 0:
            return (0.0, 0.0)
            
        x = X / (X + Y + Z)
        y = Y / (X + Y + Z)
        
        return (x, y)


def get_adaptive_lighting_from_sun(sun_data: Dict, config: Optional[Dict] = None) -> Dict:
    """Get adaptive lighting values based on sun position from Home Assistant.
    
    Args:
        sun_data: Sun entity data from Home Assistant containing:
            - elevation: Sun elevation in degrees
            - azimuth: Sun azimuth in degrees
            - next_rising: Next sunrise time
            - next_setting: Next sunset time
            - next_noon: Next solar noon
        config: Optional configuration override
        
    Returns:
        Dictionary with:
            - color_temp: Color temperature in Kelvin
            - brightness: Brightness percentage (0-100)
            - rgb: RGB tuple
            - xy: XY color coordinates
            - sun_position: Calculated sun position (-1 to 1)
    """
    # Default configuration
    default_config = {
        'min_color_temp': 2000,
        'max_color_temp': 5500,
        'sleep_color_temp': 1000,
        'min_brightness': 10,
        'max_brightness': 100,
        'adapt_until_sleep': True
    }
    
    if config:
        default_config.update(config)
        
    # Initialize adaptive lighting calculator
    al = AdaptiveLighting(**default_config)
    
    # Get current time
    current_time = datetime.now()
    
    # Calculate sun position
    sun_position = al.calculate_sun_position(current_time, sun_data)
    
    # Calculate color temperature
    color_temp = al.calculate_color_temperature(sun_position)
    
    # Calculate brightness
    brightness = al.calculate_brightness(sun_position)
    
    # Convert to RGB
    rgb = al.color_temperature_to_rgb(color_temp)
    
    # Convert to XY
    xy = al.rgb_to_xy(rgb)
    
    logger.info(f"Sun position: {sun_position:.2f}, Color temp: {color_temp}K, Brightness: {brightness}%")
    
    return {
        'color_temp': color_temp,
        'brightness': brightness,
        'rgb': rgb,
        'xy': xy,
        'sun_position': sun_position
    }


if __name__ == "__main__":
    # Test with sample data
    import datetime
    
    # More realistic data for 17:49 (5:49 PM)
    # In winter, sun is likely below horizon at this time
    sample_sun_data = {
        'elevation': -10.0,  # Sun 10 degrees below horizon (twilight)
        'azimuth': 245.0,    # Southwest
        'next_rising': '2025-01-28T07:15:00+00:00',  # Tomorrow morning
        'next_setting': '2025-01-28T17:30:00+00:00'  # Already set today
    }
    
    print(f"Current time: {datetime.now().strftime('%H:%M')}")
    result = get_adaptive_lighting_from_sun(sample_sun_data)
    print(f"Color Temperature: {result['color_temp']}K")
    print(f"Brightness: {result['brightness']}%")
    print(f"RGB: {result['rgb']}")
    print(f"XY: {result['xy']}")
    print(f"Sun Position: {result['sun_position']:.2f}")