#!/usr/bin/env python3
"""Test suite for main.py WebSocket client functionality."""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from websockets.client import WebSocketClientProtocol

from main import HomeAssistantWebSocketClient
from brain import ColorMode


class TestHomeAssistantWebSocketClient:
    """Test cases for HomeAssistantWebSocketClient initialization and basic functionality."""

    def setup_method(self):
        """Set up test environment for each test."""
        # Store original environment for restoration
        self.original_env = os.environ.copy()

    def teardown_method(self):
        """Clean up after each test."""
        # Restore original environment
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_init_basic(self):
        """Test basic initialization."""
        client = HomeAssistantWebSocketClient(
            host="localhost",
            port=8123,
            access_token="test_token",
            use_ssl=False
        )

        assert client.host == "localhost"
        assert client.port == 8123
        assert client.access_token == "test_token"
        assert client.use_ssl is False
        assert client.websocket is None
        assert client.message_id == 1
        assert isinstance(client.sun_data, dict)
        assert isinstance(client.magic_mode_areas, set)
        assert isinstance(client.magic_mode_time_offsets, dict)

    def test_init_with_ssl(self):
        """Test initialization with SSL enabled."""
        client = HomeAssistantWebSocketClient(
            host="homeassistant.local",
            port=8123,
            access_token="token",
            use_ssl=True
        )

        assert client.use_ssl is True

    def test_color_mode_default(self):
        """Test default color mode is KELVIN."""
        client = HomeAssistantWebSocketClient(
            host="localhost", port=8123, access_token="token"
        )

        assert client.color_mode == ColorMode.KELVIN

    def test_color_mode_from_env_valid(self):
        """Test color mode from environment variable."""
        with patch.dict(os.environ, {"COLOR_MODE": "rgb"}):
            client = HomeAssistantWebSocketClient(
                host="localhost", port=8123, access_token="token"
            )

        assert client.color_mode == ColorMode.RGB

    def test_color_mode_from_env_uppercase(self):
        """Test color mode from environment variable uppercase."""
        with patch.dict(os.environ, {"COLOR_MODE": "XY"}):
            client = HomeAssistantWebSocketClient(
                host="localhost", port=8123, access_token="token"
            )

        assert client.color_mode == ColorMode.XY

    def test_color_mode_from_env_invalid(self):
        """Test invalid color mode defaults to KELVIN."""
        with patch.dict(os.environ, {"COLOR_MODE": "invalid"}):
            client = HomeAssistantWebSocketClient(
                host="localhost", port=8123, access_token="token"
            )

        assert client.color_mode == ColorMode.KELVIN

    def test_websocket_url_from_host_port(self):
        """Test WebSocket URL construction from host/port."""
        client = HomeAssistantWebSocketClient(
            host="192.168.1.100", port=8123, access_token="token", use_ssl=False
        )

        expected_url = "ws://192.168.1.100:8123/api/websocket"
        assert client.websocket_url == expected_url

    def test_websocket_url_with_ssl(self):
        """Test WebSocket URL construction with SSL."""
        client = HomeAssistantWebSocketClient(
            host="homeassistant.local", port=8123, access_token="token", use_ssl=True
        )

        expected_url = "wss://homeassistant.local:8123/api/websocket"
        assert client.websocket_url == expected_url

    def test_websocket_url_from_env(self):
        """Test WebSocket URL from environment variable."""
        custom_url = "wss://custom.homeassistant.io/api/websocket"
        with patch.dict(os.environ, {"HA_WEBSOCKET_URL": custom_url}):
            client = HomeAssistantWebSocketClient(
                host="localhost", port=8123, access_token="token"
            )

            assert client.websocket_url == custom_url

    def test_get_next_message_id(self):
        """Test message ID generation."""
        client = HomeAssistantWebSocketClient(
            host="localhost", port=8123, access_token="token"
        )

        # Initial message ID should be 1
        assert client._get_next_message_id() == 1
        assert client.message_id == 2

        # Next should be 2
        assert client._get_next_message_id() == 2
        assert client.message_id == 3

    @patch('main.HomeAssistantWebSocketClient.load_saved_offsets')
    def test_init_calls_load_saved_offsets(self, mock_load):
        """Test that initialization calls load_saved_offsets."""
        HomeAssistantWebSocketClient(
            host="localhost", port=8123, access_token="token"
        )

        mock_load.assert_called_once()

    def test_update_zha_group_mapping_magic_prefix(self):
        """Test ZHA group mapping with Magic_ prefix."""
        client = HomeAssistantWebSocketClient(
            host="localhost", port=8123, access_token="token"
        )

        # Test with Magic_ prefix in friendly name
        client._update_zha_group_mapping(
            "light.magic_kitchen_lights",
            "Magic_Kitchen Lights"
        )

        # Should create mappings with multiple variations
        assert "Kitchen Lights" in client.area_to_light_entity
        assert "kitchen lights" in client.area_to_light_entity
        assert client.area_to_light_entity["Kitchen Lights"] == "light.magic_kitchen_lights"

    def test_update_zha_group_mapping_lowercase(self):
        """Test ZHA group mapping with lowercase magic prefix."""
        client = HomeAssistantWebSocketClient(
            host="localhost", port=8123, access_token="token"
        )

        client._update_zha_group_mapping(
            "light.magic_living_room",
            "magic_living room group"
        )

        assert "living room group" in client.area_to_light_entity

    def test_update_zha_group_mapping_entity_id_extraction(self):
        """Test ZHA group mapping from entity ID when friendly name lacks magic prefix."""
        client = HomeAssistantWebSocketClient(
            host="localhost", port=8123, access_token="token"
        )

        client._update_zha_group_mapping(
            "light.magic_bedroom",
            "Bedroom Group"  # No magic prefix
        )

        assert "bedroom" in client.area_to_light_entity

    def test_update_zha_group_mapping_no_magic(self):
        """Test ZHA group mapping ignores non-magic entities."""
        client = HomeAssistantWebSocketClient(
            host="localhost", port=8123, access_token="token"
        )

        initial_count = len(client.area_to_light_entity)

        client._update_zha_group_mapping(
            "light.regular_kitchen_light",
            "Kitchen Light"
        )

        # Should not add anything
        assert len(client.area_to_light_entity) == initial_count

    def test_update_zha_group_mapping_underscore_to_space(self):
        """Test ZHA group mapping converts underscores to spaces."""
        client = HomeAssistantWebSocketClient(
            host="localhost", port=8123, access_token="token"
        )

        client._update_zha_group_mapping(
            "light.magic_home_office",
            "Magic_home_office"
        )

        # Should have both underscore and space versions
        assert "home_office" in client.area_to_light_entity
        assert "home office" in client.area_to_light_entity

    def test_components_initialization(self):
        """Test that all required components are initialized."""
        import sys
        from unittest.mock import Mock

        # Skip test if modules are mocked (happens when running with other tests)
        if any(isinstance(sys.modules.get(m), Mock) for m in ['primitives']):
            pytest.skip("Modules are mocked by other tests, skipping to avoid interference")

        # Import the classes we need
        from primitives import MagicLightPrimitives

        client = HomeAssistantWebSocketClient(
            host="localhost", port=8123, access_token="token"
        )

        # Check that all components are properly initialized
        assert client.primitives is not None, "primitives should not be None"

        assert isinstance(client.primitives, MagicLightPrimitives), \
            f"primitives should be MagicLightPrimitives, got {type(client.primitives)}"

        assert hasattr(client.primitives, 'client'), \
            "primitives should have 'client' attribute"
        assert client.primitives.client is client, \
            "primitives.client should reference the HomeAssistantWebSocketClient instance"


class TestHomeAssistantWebSocketClientAsync:
    """Test cases for async WebSocket client methods."""

    def setup_method(self):
        """Set up test environment for each test."""
        self.client = HomeAssistantWebSocketClient(
            host="localhost", port=8123, access_token="token"
        )

        # Mock the websocket
        self.mock_websocket = AsyncMock(spec=WebSocketClientProtocol)
        self.client.websocket = self.mock_websocket

    @pytest.mark.asyncio
    async def test_authenticate_success(self):
        """Test successful authentication."""
        # Mock successful auth response
        self.mock_websocket.recv.return_value = json.dumps({
            "type": "auth_required"
        })

        # Mock auth_ok response for send
        auth_response = json.dumps({"type": "auth_ok"})
        self.mock_websocket.recv.side_effect = [
            json.dumps({"type": "auth_required"}),
            auth_response
        ]

        result = await self.client.authenticate()

        assert result is True

        # Verify auth message was sent
        self.mock_websocket.send.assert_called_once()
        sent_data = json.loads(self.mock_websocket.send.call_args[0][0])
        assert sent_data["type"] == "auth"
        assert sent_data["access_token"] == "token"

    @pytest.mark.asyncio
    async def test_authenticate_failure(self):
        """Test authentication failure."""
        self.mock_websocket.recv.side_effect = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_invalid", "message": "Invalid token"})
        ]

        result = await self.client.authenticate()

        assert result is False

    @pytest.mark.asyncio
    async def test_subscribe_events_all(self):
        """Test subscribing to all events."""
        message_id = await self.client.subscribe_events()

        assert message_id == 1
        self.mock_websocket.send.assert_called_once()

        sent_data = json.loads(self.mock_websocket.send.call_args[0][0])
        assert sent_data["type"] == "subscribe_events"
        assert sent_data["id"] == 1
        assert "event_type" not in sent_data

    @pytest.mark.asyncio
    async def test_subscribe_events_specific_type(self):
        """Test subscribing to specific event type."""
        message_id = await self.client.subscribe_events("zha_event")

        assert message_id == 1
        self.mock_websocket.send.assert_called_once()

        sent_data = json.loads(self.mock_websocket.send.call_args[0][0])
        assert sent_data["event_type"] == "zha_event"

    @pytest.mark.asyncio
    async def test_call_service_basic(self):
        """Test basic service call."""
        message_id = await self.client.call_service(
            "light", "turn_on", {"brightness": 100}
        )

        assert message_id == 1
        self.mock_websocket.send.assert_called_once()

        sent_data = json.loads(self.mock_websocket.send.call_args[0][0])
        assert sent_data["type"] == "call_service"
        assert sent_data["domain"] == "light"
        assert sent_data["service"] == "turn_on"
        assert sent_data["service_data"]["brightness"] == 100

    @pytest.mark.asyncio
    async def test_call_service_with_target(self):
        """Test service call with target."""
        message_id = await self.client.call_service(
            "light", "turn_on",
            {"brightness": 100},
            {"area_id": "kitchen"}
        )

        sent_data = json.loads(self.mock_websocket.send.call_args[0][0])
        assert sent_data["target"]["area_id"] == "kitchen"
        assert sent_data["service_data"]["brightness"] == 100

    @pytest.mark.asyncio
    async def test_call_service_legacy_area_id(self):
        """Test service call with area_id in service_data (legacy)."""
        message_id = await self.client.call_service(
            "light", "turn_on",
            {"brightness": 100, "area_id": "kitchen"}
        )

        sent_data = json.loads(self.mock_websocket.send.call_args[0][0])
        assert sent_data["target"]["area_id"] == "kitchen"
        assert "area_id" not in sent_data["service_data"]

    @pytest.mark.asyncio
    async def test_call_service_legacy_entity_id(self):
        """Test service call with entity_id in service_data (legacy)."""
        message_id = await self.client.call_service(
            "light", "turn_on",
            {"brightness": 100, "entity_id": "light.kitchen"}
        )

        sent_data = json.loads(self.mock_websocket.send.call_args[0][0])
        assert sent_data["target"]["entity_id"] == "light.kitchen"
        assert "entity_id" not in sent_data["service_data"]

    @pytest.mark.asyncio
    async def test_determine_light_target_zha_group_with_parity(self):
        """Test determine_light_target with ZHA group and parity."""
        area_id = "kitchen"
        self.client.area_to_light_entity[area_id] = "light.magic_kitchen"
        self.client.area_parity_cache[area_id] = True

        target_type, target_value = await self.client.determine_light_target(area_id)

        assert target_type == "entity_id"
        assert target_value == "light.magic_kitchen"

    @pytest.mark.asyncio
    async def test_determine_light_target_zha_group_no_parity(self):
        """Test determine_light_target with ZHA group but no parity."""
        area_id = "kitchen"
        self.client.area_to_light_entity[area_id] = "light.magic_kitchen"
        self.client.area_parity_cache[area_id] = False

        target_type, target_value = await self.client.determine_light_target(area_id)

        assert target_type == "area_id"
        assert target_value == area_id

    @pytest.mark.asyncio
    async def test_determine_light_target_no_zha_group(self):
        """Test determine_light_target with no ZHA group."""
        area_id = "kitchen"

        target_type, target_value = await self.client.determine_light_target(area_id)

        assert target_type == "area_id"
        assert target_value == area_id

    @pytest.mark.asyncio
    async def test_determine_light_target_lowercase_fallback(self):
        """Test determine_light_target with lowercase area matching."""
        area_id = "Kitchen"  # Capitalized
        self.client.area_to_light_entity["kitchen"] = "light.magic_kitchen"  # lowercase
        self.client.area_parity_cache[area_id] = True

        target_type, target_value = await self.client.determine_light_target(area_id)

        assert target_type == "entity_id"
        assert target_value == "light.magic_kitchen"

    @pytest.mark.asyncio
    async def test_turn_on_lights_adaptive_basic(self):
        """Test turn_on_lights_adaptive basic functionality."""
        area_id = "kitchen"
        adaptive_values = {
            "kelvin": 3000,
            "brightness": 80,
            "rgb": [255, 200, 150]
        }

        await self.client.turn_on_lights_adaptive(area_id, adaptive_values, transition=2)

        # Should call the websocket send (through call_service)
        self.mock_websocket.send.assert_called_once()

        # Verify the message structure
        sent_data = json.loads(self.mock_websocket.send.call_args[0][0])
        assert sent_data["type"] == "call_service"
        assert sent_data["domain"] == "light"
        assert sent_data["service"] == "turn_on"
        assert sent_data["service_data"]["transition"] == 2
        assert sent_data["service_data"]["brightness_pct"] == 80
        assert sent_data["service_data"]["kelvin"] == 3000