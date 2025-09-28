#!/usr/bin/env python3
"""Web server for Home Assistant ingress - Light Designer interface."""

import asyncio
import json
import logging
import math
import os
from aiohttp import web
from aiohttp.web import Request, Response
import aiofiles
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from astral import LocationInfo
from astral.sun import sun

from brain import DEFAULT_MAX_DIM_STEPS, calculate_dimming_step, get_adaptive_lighting, AdaptiveLighting

logger = logging.getLogger(__name__)


def calculate_step_sequence(current_hour: float, action: str, max_steps: int, config: dict) -> list:
    """Calculate a sequence of step positions for visualization.

    Args:
        current_hour: Current clock time (0-24)
        action: 'brighten' or 'dim'
        max_steps: Maximum number of steps to calculate
        config: Configuration dict with curve parameters

    Returns:
        List of dicts with hour, brightness, kelvin, rgb for each step
    """
    steps = []

    # Get location from config
    latitude = config.get('latitude')
    longitude = config.get('longitude')
    timezone = config.get('timezone')

    if not latitude or not longitude or not timezone:
        logger.error("Missing location data in config")
        return steps

    # Use the current date but calculate proper solar times
    try:
        tzinfo = ZoneInfo(timezone)
    except:
        tzinfo = ZoneInfo('UTC')

    today = datetime.now(tzinfo).date()
    loc = LocationInfo(latitude=latitude, longitude=longitude, timezone=tzinfo)
    solar_events = sun(loc.observer, date=today, tzinfo=tzinfo)
    solar_noon = solar_events["noon"]
    solar_midnight = solar_events["noon"] - timedelta(hours=12)

    # Convert clock hour (0-24) to actual datetime
    # current_hour is now clock time (0 = midnight, 12 = noon, etc.)
    base_time = datetime.now(tzinfo).replace(hour=0, minute=0, second=0, microsecond=0)
    adjusted_time = base_time + timedelta(hours=current_hour)

    try:
        for step_num in range(max_steps):
            if step_num == 0:
                # First "step" is the current position
                lighting_values = get_adaptive_lighting(
                    latitude=config.get('latitude'),
                    longitude=config.get('longitude'),
                    timezone=config.get('timezone'),
                    current_time=adjusted_time,
                    config=config
                )
                steps.append({
                    'hour': current_hour,
                    'brightness': lighting_values['brightness'],
                    'kelvin': lighting_values['kelvin'],
                    'rgb': lighting_values.get('rgb', [255, 255, 255])
                })
            else:
                # Calculate the next step
                result = calculate_dimming_step(
                    current_time=adjusted_time,
                    action=action,
                    latitude=config.get('latitude'),
                    longitude=config.get('longitude'),
                    timezone=config.get('timezone'),
                    max_steps=max_steps,
                    min_color_temp=config.get('min_color_temp', 500),
                    max_color_temp=config.get('max_color_temp', 6500),
                    min_brightness=config.get('min_brightness', 1),
                    max_brightness=config.get('max_brightness', 100),
                    config=config
                )

                # Check if we've reached a boundary (no change)
                if abs(result['time_offset_minutes']) < 0.1:
                    break

                # Apply the time offset
                adjusted_time += timedelta(minutes=result['time_offset_minutes'])

                # Convert back to clock hour (0-24 scale)
                new_hour = adjusted_time.hour + adjusted_time.minute / 60.0

                steps.append({
                    'hour': new_hour,
                    'brightness': result['brightness'],
                    'kelvin': result['kelvin'],
                    'rgb': result.get('rgb', [255, 255, 255])
                })

                # Update for next iteration
                current_hour = new_hour

    except Exception as e:
        logger.error(f"Error calculating step sequence: {e}")
        logger.error(f"Config: {config}")
        logger.error(f"Current hour: {current_hour}, action: {action}, max_steps: {max_steps}")
        # Return at least the first step if possible
        if not steps:
            try:
                # Try to get just the current position without stepping
                lighting_values = get_adaptive_lighting(
                    latitude=config.get('latitude'),
                    longitude=config.get('longitude'),
                    timezone=config.get('timezone'),
                    current_time=adjusted_time,
                    config=config
                )
                steps.append({
                    'hour': current_hour,
                    'brightness': lighting_values['brightness'],
                    'kelvin': lighting_values['kelvin'],
                    'rgb': lighting_values.get('rgb', [255, 255, 255])
                })
            except Exception as e2:
                logger.error(f"Error getting current position: {e2}")

    return steps


def generate_curve_data(config: dict) -> dict:
    """Generate complete curve data for visualization.

    Args:
        config: Configuration dict with curve parameters and location

    Returns:
        Dict containing curve arrays, solar times, and segments
    """
    try:
        # Get location from config
        latitude = config.get('latitude', 35.0)
        longitude = config.get('longitude', -78.6)
        timezone = config.get('timezone', 'US/Eastern')
        month = config.get('month', 6)  # Test month for UI

        # Create timezone info
        try:
            tzinfo = ZoneInfo(timezone)
        except:
            tzinfo = ZoneInfo('UTC')

        # Use current date but for the specified test month
        today = datetime.now(tzinfo).replace(month=month, day=15)  # Mid-month for consistency
        loc = LocationInfo(latitude=latitude, longitude=longitude, timezone=tzinfo)
        solar_events = sun(loc.observer, date=today.date(), tzinfo=tzinfo)

        solar_noon = solar_events["noon"]
        solar_midnight = solar_events["noon"] - timedelta(hours=12)

        # Use the get_adaptive_lighting function to get values at each time point
        # We'll call it for each sample point

        # Sample at 0.1 hour intervals (matching JavaScript)
        sample_step = 0.1
        hours = []
        brightness_values = []
        cct_values = []
        rgb_values = []
        sun_power_values = []

        # Morning segment (solar midnight to solar noon)
        morning_hours = []
        morning_brightness = []
        morning_cct = []

        # Evening segment (solar noon to solar midnight)
        evening_hours = []
        evening_brightness = []
        evening_cct = []

        # Sample the full 24-hour curve using actual clock time
        # Start from midnight of today and sample every 0.1 hours
        base_time = datetime.now(tzinfo).replace(hour=0, minute=0, second=0, microsecond=0)

        for i in range(int(24 / sample_step)):
            current_time = base_time + timedelta(hours=i * sample_step)

            # Calculate hour of day (0-24 scale) for plotting
            clock_hour = current_time.hour + current_time.minute / 60.0

            # Get adaptive lighting values using the main function
            lighting_values = get_adaptive_lighting(
                latitude=latitude,
                longitude=longitude,
                timezone=timezone,
                current_time=current_time,
                min_color_temp=config.get('min_color_temp', 500),
                max_color_temp=config.get('max_color_temp', 6500),
                min_brightness=config.get('min_brightness', 1),
                max_brightness=config.get('max_brightness', 100),
                config=config
            )

            brightness = lighting_values['brightness']
            cct = lighting_values['kelvin']
            rgb = lighting_values.get('rgb', [255, 255, 255])

            # Calculate sun power (simple approximation based on time)
            # This is just for visualization - using a simple sine wave approximation
            hour_of_day = current_time.hour + current_time.minute / 60
            if 6 <= hour_of_day <= 18:  # Daytime hours
                sun_power = max(0, 300 * math.sin(math.pi * (hour_of_day - 6) / 12))
            else:
                sun_power = 0

            # Add to main arrays
            hours.append(clock_hour)
            brightness_values.append(brightness)
            cct_values.append(cct)
            rgb_values.append(list(rgb))
            sun_power_values.append(sun_power)

            # Add to appropriate segment (split at solar noon, not clock noon)
            # Convert solar noon to clock time for proper segmentation
            solar_noon_clock = solar_noon.hour + solar_noon.minute / 60.0
            if clock_hour < solar_noon_clock:
                morning_hours.append(clock_hour)
                morning_brightness.append(brightness)
                morning_cct.append(cct)
            else:
                evening_hours.append(clock_hour)
                evening_brightness.append(brightness)
                evening_cct.append(cct)

            # Move to next sample point
            current_time += timedelta(hours=sample_step)

        # Convert solar times to clock hours (0-24 scale)
        solar_noon_hour = solar_noon.hour + solar_noon.minute / 60.0
        solar_midnight_hour = (solar_noon_hour + 12) % 24

        # Calculate sunrise/sunset if available
        sunrise_hour = None
        sunset_hour = None
        try:
            if 'sunrise' in solar_events and solar_events['sunrise']:
                sunrise_hour = solar_events['sunrise'].hour + solar_events['sunrise'].minute / 60.0

            if 'sunset' in solar_events and solar_events['sunset']:
                sunset_hour = solar_events['sunset'].hour + solar_events['sunset'].minute / 60.0
        except:
            pass

        return {
            'hours': hours,
            'bris': brightness_values,
            'ccts': cct_values,
            'sunPower': sun_power_values,
            'morn': {
                'hours': morning_hours,
                'bris': morning_brightness,
                'ccts': morning_cct
            },
            'eve': {
                'hours': evening_hours,
                'bris': evening_brightness,
                'ccts': evening_cct
            },
            'solar': {
                'sunrise': sunrise_hour,
                'sunset': sunset_hour,
                'solarNoon': solar_noon_hour,
                'solarMidnight': solar_midnight_hour
            }
        }

    except Exception as e:
        logger.error(f"Error generating curve data: {e}")
        # Return minimal valid structure on error
        return {
            'hours': [0, 12, 24],
            'bris': [1, 100, 1],
            'ccts': [500, 6500, 500],
            'sunPower': [0, 300, 0],
            'morn': {'hours': [0, 12], 'bris': [1, 100], 'ccts': [500, 6500]},
            'eve': {'hours': [12, 24], 'bris': [100, 1], 'ccts': [6500, 500]},
            'solar': {'sunrise': 6, 'sunset': 18, 'solarNoon': 12, 'solarMidnight': 0}
        }


class LightDesignerServer:
    """Web server for the Light Designer ingress interface."""
    
    def __init__(self, port: int = 8099):
        self.port = port
        self.app = web.Application()
        self.setup_routes()
        
        # Detect environment and set appropriate paths
        # In Home Assistant, /data directory exists. In dev, use local directory
        if os.path.exists("/data"):
            # Running in Home Assistant
            self.data_dir = "/data"
        else:
            # Running in development - use local .data directory
            self.data_dir = os.path.join(os.path.dirname(__file__), ".data")
            # Create directory if it doesn't exist
            os.makedirs(self.data_dir, exist_ok=True)
            logger.info(f"Development mode: using {self.data_dir} for configuration storage")
        
        # Set file paths based on data directory
        self.options_file = os.path.join(self.data_dir, "options.json")
        self.designer_file = os.path.join(self.data_dir, "designer_config.json")
        
    def setup_routes(self):
        """Set up web routes."""
        # API routes - must handle all ingress prefixes
        self.app.router.add_route('GET', '/{path:.*}/api/config', self.get_config)
        self.app.router.add_route('POST', '/{path:.*}/api/config', self.save_config)
        self.app.router.add_route('GET', '/{path:.*}/api/steps', self.get_step_sequences)
        self.app.router.add_route('GET', '/{path:.*}/api/curve', self.get_curve_data)
        self.app.router.add_route('GET', '/{path:.*}/api/time', self.get_time)
        self.app.router.add_route('GET', '/{path:.*}/health', self.health_check)

        # Direct API routes (for non-ingress access)
        self.app.router.add_get('/api/config', self.get_config)
        self.app.router.add_post('/api/config', self.save_config)
        self.app.router.add_get('/api/steps', self.get_step_sequences)
        self.app.router.add_get('/api/curve', self.get_curve_data)
        self.app.router.add_get('/api/time', self.get_time)
        self.app.router.add_get('/health', self.health_check)
        
        # Handle root and any other paths (catch-all must be last)
        self.app.router.add_get('/', self.serve_designer)
        self.app.router.add_get('/{path:.*}', self.serve_designer)
        
    async def serve_designer(self, request: Request) -> Response:
        """Serve the Light Designer HTML page."""
        try:
            # Read the current configuration (merged options + designer overrides)
            config = await self.load_config()
            
            # Read the designer HTML template
            html_path = Path(__file__).parent / "designer.html"
            async with aiofiles.open(html_path, 'r') as f:
                html_content = await f.read()
            
            # Inject current configuration into the HTML
            config_script = f"""
            <script>
            // Load saved configuration
            window.savedConfig = {json.dumps(config)};
            </script>
            """
            
            # Insert the config script before the closing body tag
            html_content = html_content.replace('</body>', f'{config_script}</body>')
            
            return web.Response(
                text=html_content, 
                content_type='text/html',
                headers={
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }
            )
        except Exception as e:
            logger.error(f"Error serving designer page: {e}")
            return web.Response(text=f"Error: {str(e)}", status=500)
    
    async def get_config(self, request: Request) -> Response:
        """Get current curve configuration."""
        try:
            config = await self.load_config()
            return web.json_response(config)
        except Exception as e:
            logger.error(f"Error getting config: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    async def save_config(self, request: Request) -> Response:
        """Save curve configuration."""
        try:
            data = await request.json()
            
            # Load existing config
            config = await self.load_config()
            
            # Update with new curve parameters
            config.update(data)
            
            # Save to file
            await self.save_config_to_file(config)
            
            return web.json_response({"status": "success", "config": config})
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    async def health_check(self, request: Request) -> Response:
        """Health check endpoint."""
        return web.json_response({"status": "healthy"})

    async def get_time(self, request: Request) -> Response:
        """Get current server time in Home Assistant timezone."""
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            from brain import get_adaptive_lighting

            # Get location from environment variables (set by main.py)
            latitude = float(os.getenv("HASS_LATITUDE", "35.0"))
            longitude = float(os.getenv("HASS_LONGITUDE", "-78.6"))
            timezone = os.getenv("HASS_TIME_ZONE", "US/Eastern")

            # Get current time in HA timezone
            try:
                tzinfo = ZoneInfo(timezone)
            except:
                tzinfo = None

            now = datetime.now(tzinfo)

            # Calculate current hour (0-24 scale)
            current_hour = now.hour + now.minute / 60.0

            # Load current configuration to use same parameters as UI
            config = await self.load_config()

            # Get current adaptive lighting values for comparison using same config as UI
            lighting_values = get_adaptive_lighting(
                latitude=latitude,
                longitude=longitude,
                timezone=timezone,
                current_time=now,
                min_color_temp=config.get('min_color_temp', 500),
                max_color_temp=config.get('max_color_temp', 6500),
                min_brightness=config.get('min_brightness', 1),
                max_brightness=config.get('max_brightness', 100),
                config=config
            )

            return web.json_response({
                "current_time": now.isoformat(),
                "current_hour": current_hour,
                "timezone": timezone,
                "latitude": latitude,
                "longitude": longitude,
                "lighting": {
                    "brightness": lighting_values.get('brightness', 0),
                    "kelvin": lighting_values.get('kelvin', 0),
                    "solar_position": lighting_values.get('solar_position', 0)
                }
            })

        except Exception as e:
            logger.error(f"Error getting time info: {e}")
            return web.json_response(
                {"error": f"Failed to get time info: {e}"},
                status=500
            )

    def apply_query_overrides(self, config: dict, query) -> dict:
        """Apply UI query parameters to a config dict for live previews."""
        numeric_params = [
            'month',
            'min_color_temp', 'max_color_temp',
            'min_brightness', 'max_brightness',
            'mid_bri_up', 'steep_bri_up', 'mid_cct_up', 'steep_cct_up',
            'mid_bri_dn', 'steep_bri_dn', 'mid_cct_dn', 'steep_cct_dn'
        ]

        for param_name in numeric_params:
            if param_name in query:
                raw_value = query[param_name]
                try:
                    if param_name == 'month':
                        config[param_name] = int(float(raw_value))
                    else:
                        config[param_name] = float(raw_value)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid value for {param_name}: {raw_value}")

        for param_name in ['mirror_up', 'mirror_dn']:
            if param_name in query:
                config[param_name] = query[param_name].lower() in ('true', '1', 'yes', 'on')

        return config

    async def get_step_sequences(self, request: Request) -> Response:
        """Calculate step sequences for visualization."""
        try:
            # Get parameters from query string
            current_hour = float(request.query.get('hour', 12.0))
            max_steps = int(request.query.get('max_steps', 10))

            # Load current configuration
            config = await self.load_config()

            # Apply overrides from UI for live preview
            config = self.apply_query_overrides(config, request.query)

            # Calculate step sequences in both directions
            step_up_sequence = calculate_step_sequence(current_hour, 'brighten', max_steps, config)
            step_down_sequence = calculate_step_sequence(current_hour, 'dim', max_steps, config)

            return web.json_response({
                "step_up": {"steps": step_up_sequence},
                "step_down": {"steps": step_down_sequence}
            })

        except Exception as e:
            logger.error(f"Error calculating step sequences: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def get_curve_data(self, request: Request) -> Response:
        """Generate and return curve data for visualization."""
        try:
            # Load base configuration (includes server location data)
            config = await self.load_config()

            # Override with UI parameters from query string
            config = self.apply_query_overrides(config, request.query)

            # Generate curve data using the merged configuration
            curve_data = generate_curve_data(config)

            return web.json_response(curve_data)

        except Exception as e:
            logger.error(f"Error generating curve data: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def load_config(self) -> dict:
        """Load configuration, merging HA options with designer overrides.

        Order of precedence (later wins):
          defaults -> options.json -> designer_config.json
        """
        # Defaults used by UI when nothing saved yet
        config: dict = {
            "color_mode": "kelvin",
            "min_color_temp": 500,
            "max_color_temp": 6500,
            "min_brightness": 1,
            "max_brightness": 100,
            # Morning (up) parameters - simplified, no gain/offset/decay
            "mid_bri_up": 6.0,
            "steep_bri_up": 1.5,
            "mid_cct_up": 6.0,
            "steep_cct_up": 1.5,
            # Evening (down) parameters - simplified, no gain/offset/decay
            "mid_bri_dn": 8.0,
            "steep_bri_dn": 1.3,
            "mid_cct_dn": 8.0,
            "steep_cct_dn": 1.3,
            # Mirror flags (default ON)
            "mirror_up": True,
            "mirror_dn": True,
            # Dimming steps
            "max_dim_steps": DEFAULT_MAX_DIM_STEPS,
            # Location settings (UI preview only)
            "latitude": 35.0,
            "longitude": -78.6,
            "timezone": "US/Eastern",
            "month": 6
        }

        # Merge supervisor-managed options.json (if present)
        try:
            if os.path.exists(self.options_file):
                async with aiofiles.open(self.options_file, 'r') as f:
                    content = await f.read()
                    opts = json.loads(content)
                    if isinstance(opts, dict):
                        config.update(opts)
        except Exception as e:
            logger.warning(f"Error loading {self.options_file}: {e}")

        # Merge user-saved designer config (persists across restarts)
        try:
            if os.path.exists(self.designer_file):
                async with aiofiles.open(self.designer_file, 'r') as f:
                    content = await f.read()
                    overrides = json.loads(content)
                    if isinstance(overrides, dict):
                        config.update(overrides)
        except Exception as e:
            logger.warning(f"Error loading {self.designer_file}: {e}")

        return config
    
    async def save_config_to_file(self, config: dict):
        """Save designer configuration to persistent file distinct from options.json."""
        try:
            async with aiofiles.open(self.designer_file, 'w') as f:
                await f.write(json.dumps(config, indent=2))
            logger.info(f"Configuration saved to {self.designer_file}")
        except Exception as e:
            logger.error(f"Error saving config to file: {e}")
            raise
    
    async def start(self):
        """Start the web server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        logger.info(f"Light Designer server started on port {self.port}")
        
        # Keep the server running
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            await runner.cleanup()

async def main():
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    port = int(os.getenv("INGRESS_PORT", "8099"))
    server = LightDesignerServer(port)
    await server.start()

if __name__ == "__main__":
    asyncio.run(main())
