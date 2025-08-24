#!/usr/bin/env python3
"""Web server for Home Assistant ingress - Light Designer interface."""

import asyncio
import json
import logging
import os
from aiohttp import web
from aiohttp.web import Request, Response
import aiofiles
from pathlib import Path

from brain import DEFAULT_MAX_DIM_STEPS

logger = logging.getLogger(__name__)

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
        self.app.router.add_route('GET', '/{path:.*}/health', self.health_check)
        
        # Direct API routes (for non-ingress access)
        self.app.router.add_get('/api/config', self.get_config)
        self.app.router.add_post('/api/config', self.save_config)
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
    
    async def load_config(self) -> dict:
        """Load configuration, merging HA options with designer overrides.

        Order of precedence (later wins):
          defaults -> options.json -> designer_config.json
        """
        # Defaults used by UI when nothing saved yet
        config: dict = {
            "color_mode": "rgb",
            "min_color_temp": 500,
            "max_color_temp": 6500,
            "min_brightness": 1,
            "max_brightness": 100,
            # Morning brightness
            "morning_bri_mid": 6.0,
            "morning_bri_steep": 1.0,
            "morning_bri_decay": 0.02,
            "morning_bri_gain": 1.0,
            "morning_bri_offset": 0,
            # Morning CCT
            "morning_cct_mid": 6.0,
            "morning_cct_steep": 1.0,
            "morning_cct_decay": 0.02,
            "morning_cct_gain": 1.0,
            "morning_cct_offset": 0,
            # Evening brightness
            "evening_bri_mid": 6.0,
            "evening_bri_steep": 1.0,
            "evening_bri_decay": 0.02,
            "evening_bri_gain": 1.0,
            "evening_bri_offset": 0,
            # Evening CCT
            "evening_cct_mid": 6.0,
            "evening_cct_steep": 1.0,
            "evening_cct_decay": 0.02,
            "evening_cct_gain": 1.0,
            "evening_cct_offset": 0,
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
