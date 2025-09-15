#!/usr/bin/env python3
"""Test suite for webserver.py - Light Designer interface."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open, AsyncMock
import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from webserver import LightDesignerServer


class TestLightDesignerServer(AioHTTPTestCase):
    """Test cases for LightDesignerServer."""

    async def get_application(self):
        """Create test application."""
        # Create temp directory for test data before creating server
        self.test_dir = tempfile.mkdtemp()

        # Create server instance
        self.light_server = LightDesignerServer(port=8099)

        # Override paths to use test directory
        self.light_server.data_dir = self.test_dir
        self.light_server.options_file = os.path.join(self.test_dir, "options.json")
        self.light_server.designer_file = os.path.join(self.test_dir, "designer_config.json")

        # Store for tests to access
        self.options_file = self.light_server.options_file
        self.designer_file = self.light_server.designer_file

        return self.light_server.app

    def setUp(self):
        """Set up test environment."""
        super().setUp()

    def tearDown(self):
        """Clean up test environment."""
        super().tearDown()
        # Clean up temp directory if it exists
        if hasattr(self, 'test_dir'):
            import shutil
            shutil.rmtree(self.test_dir, ignore_errors=True)

    @unittest_run_loop
    async def test_health_check(self):
        """Test health check endpoint."""
        resp = await self.client.request("GET", "/health")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "healthy")

    @unittest_run_loop
    async def test_health_check_with_ingress_path(self):
        """Test health check endpoint with ingress path."""
        resp = await self.client.request("GET", "/some/ingress/path/health")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "healthy")

    @unittest_run_loop
    async def test_get_config_default(self):
        """Test getting default configuration."""
        resp = await self.client.request("GET", "/api/config")
        self.assertEqual(resp.status, 200)
        data = await resp.json()

        # Check default values are present
        self.assertEqual(data["color_mode"], "kelvin")
        self.assertEqual(data["min_color_temp"], 500)
        self.assertEqual(data["max_color_temp"], 6500)
        self.assertIn("mid_bri_up", data)
        self.assertIn("steep_bri_up", data)

    @unittest_run_loop
    async def test_get_config_with_options_file(self):
        """Test configuration loading with options.json."""
        # Create options.json
        options = {"color_mode": "rgb", "min_brightness": 5}
        with open(self.options_file, 'w') as f:
            json.dump(options, f)

        resp = await self.client.request("GET", "/api/config")
        self.assertEqual(resp.status, 200)
        data = await resp.json()

        # Check that options override defaults
        self.assertEqual(data["color_mode"], "rgb")
        self.assertEqual(data["min_brightness"], 5)
        # Defaults should still be present
        self.assertEqual(data["max_color_temp"], 6500)

    @unittest_run_loop
    async def test_get_config_with_designer_file(self):
        """Test configuration loading with designer overrides."""
        # Create designer_config.json
        designer_config = {"mid_bri_up": 7.5, "steep_cct_dn": 2.0}
        with open(self.designer_file, 'w') as f:
            json.dump(designer_config, f)

        resp = await self.client.request("GET", "/api/config")
        self.assertEqual(resp.status, 200)
        data = await resp.json()

        # Check that designer config overrides defaults
        self.assertEqual(data["mid_bri_up"], 7.5)
        self.assertEqual(data["steep_cct_dn"], 2.0)

    @unittest_run_loop
    async def test_get_config_precedence(self):
        """Test configuration precedence: defaults < options < designer."""
        # Create options.json
        options = {"color_mode": "xy", "mid_bri_up": 5.0}
        with open(self.options_file, 'w') as f:
            json.dump(options, f)

        # Create designer_config.json (should override options)
        designer_config = {"mid_bri_up": 8.0, "max_brightness": 95}
        with open(self.designer_file, 'w') as f:
            json.dump(designer_config, f)

        resp = await self.client.request("GET", "/api/config")
        self.assertEqual(resp.status, 200)
        data = await resp.json()

        # Designer should win over options
        self.assertEqual(data["mid_bri_up"], 8.0)
        self.assertEqual(data["max_brightness"], 95)
        # Options should win over defaults
        self.assertEqual(data["color_mode"], "xy")

    @unittest_run_loop
    async def test_save_config(self):
        """Test saving configuration."""
        new_config = {
            "mid_bri_up": 7.0,
            "steep_bri_dn": 1.8,
            "color_mode": "rgb"
        }

        resp = await self.client.request("POST", "/api/config", json=new_config)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "success")

        # Check that file was saved
        self.assertTrue(os.path.exists(self.designer_file))
        with open(self.designer_file, 'r') as f:
            saved_config = json.load(f)

        # Should include new values plus defaults
        self.assertEqual(saved_config["mid_bri_up"], 7.0)
        self.assertEqual(saved_config["steep_bri_dn"], 1.8)
        self.assertEqual(saved_config["color_mode"], "rgb")

    @unittest_run_loop
    async def test_save_config_with_ingress_path(self):
        """Test saving configuration with ingress path."""
        new_config = {"mid_bri_up": 6.5}

        resp = await self.client.request("POST", "/ingress/prefix/api/config", json=new_config)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "success")

    @unittest_run_loop
    async def test_save_config_invalid_json(self):
        """Test saving configuration with invalid JSON."""
        resp = await self.client.request("POST", "/api/config", data="invalid json")
        self.assertEqual(resp.status, 500)
        data = await resp.json()
        self.assertIn("error", data)

    @unittest_run_loop
    async def test_serve_designer_page(self):
        """Test serving the designer HTML page."""
        # Mock the designer.html file
        mock_html = """<!DOCTYPE html>
<html>
<head><title>Light Designer</title></head>
<body>
<div id="app">Light Designer</div>
</body>
</html>"""

        # Create async mock for aiofiles
        class AsyncMockFile:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def read(self):
                return mock_html

        with patch("aiofiles.open", return_value=AsyncMockFile()):
            resp = await self.client.request("GET", "/")
            self.assertEqual(resp.status, 200)
            content = await resp.text()

            # Should contain the HTML
            self.assertIn("Light Designer", content)
            # Should contain injected config script
            self.assertIn("window.savedConfig", content)
            self.assertIn("color_mode", content)

            # Check cache headers
            self.assertEqual(resp.headers.get("Cache-Control"), "no-cache, no-store, must-revalidate")

    @unittest_run_loop
    async def test_serve_designer_with_path(self):
        """Test serving designer page with path."""
        mock_html = "<html><body>Test</body></html>"

        # Create async mock for aiofiles
        class AsyncMockFile:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def read(self):
                return mock_html

        with patch("aiofiles.open", return_value=AsyncMockFile()):
            resp = await self.client.request("GET", "/some/path")
            self.assertEqual(resp.status, 200)
            content = await resp.text()
            self.assertIn("Test", content)

    def test_init_development_mode(self):
        """Test initialization in development mode."""
        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = False  # /data doesn't exist

            server = LightDesignerServer(port=8100)

            # Should use local .data directory
            self.assertIn(".data", server.data_dir)
            self.assertEqual(server.port, 8100)

    def test_init_homeassistant_mode(self):
        """Test initialization in Home Assistant mode."""
        with patch("os.path.exists") as mock_exists:
            mock_exists.side_effect = lambda path: path == "/data"

            server = LightDesignerServer()

            # Should use /data directory
            self.assertEqual(server.data_dir, "/data")
            self.assertEqual(server.port, 8099)

    @unittest_run_loop
    async def test_load_config_file_error(self):
        """Test configuration loading with file errors."""
        # Create invalid JSON file
        with open(self.options_file, 'w') as f:
            f.write("invalid json {")

        config = await self.light_server.load_config()

        # Should fall back to defaults
        self.assertEqual(config["color_mode"], "kelvin")
        self.assertEqual(config["min_color_temp"], 500)

    @unittest_run_loop
    async def test_save_config_file_error(self):
        """Test configuration saving with file errors."""
        # Make directory read-only to cause write error
        os.chmod(self.test_dir, 0o444)

        try:
            config = {"test": "value"}
            with pytest.raises(Exception):
                await self.light_server.save_config_to_file(config)
        finally:
            # Restore permissions for cleanup
            os.chmod(self.test_dir, 0o755)


class TestLightDesignerServerIntegration:
    """Integration tests for LightDesignerServer."""

    def test_setup_routes(self):
        """Test that all routes are properly configured."""
        server = LightDesignerServer()

        # Get all registered routes
        routes = []
        for resource in server.app.router.resources():
            for route in resource:
                routes.append((route.method, str(route.resource.canonical)))

        # Check that expected routes exist
        route_paths = [path for method, path in routes]

        # API routes with ingress support
        assert "/{path}/api/config" in route_paths or "/{path:.*}/api/config" in route_paths
        assert "/{path}/health" in route_paths or "/{path:.*}/health" in route_paths

        # Direct API routes
        assert "/api/config" in route_paths
        assert "/health" in route_paths

        # Catch-all routes
        assert "/" in route_paths
        assert "/{path}" in route_paths or "/{path:.*}" in route_paths

    def test_server_start_integration(self):
        """Test server start method (without actually starting)."""
        server = LightDesignerServer(port=8099)

        # Should not raise exception during setup
        assert server.app is not None
        assert server.port == 8099