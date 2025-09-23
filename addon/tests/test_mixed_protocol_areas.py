"""Integration tests for mixed-protocol area handling."""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, Mock

import pytest

# Add magiclight directory to Python path
magiclight_path = Path(__file__).parent.parent / 'magiclight'
sys.path.insert(0, str(magiclight_path))


from light_controller import ZigBeeController, Protocol
from brain import ColorMode
from main import HomeAssistantWebSocketClient


class TestMixedProtocolAreas:
    """Test handling of areas with mixed lighting protocols."""
    
    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket connection."""
        ws = AsyncMock()
        ws.recv = AsyncMock()
        ws.send = AsyncMock()
        return ws
    
    @pytest.fixture
    async def client_with_mixed_areas(self, mock_websocket):
        """Create a client with mixed protocol areas configured."""
        client = HomeAssistantWebSocketClient("localhost", 8123, "test_token")
        
        # Mock WebSocket connection
        client.websocket = mock_websocket
        client.call_service = AsyncMock()
        client.color_mode = ColorMode.XY
        
        
        # Set up parity cache
        client.area_parity_cache = {
            "living_room": True,   # ZHA-only
            "bedroom": False,      # Mixed
            "kitchen": False       # WiFi-only
        }
        
        # Mock area to light entity mapping (for ZHA groups)
        client.area_to_light_entity = {
            "living_room": "light.glo_living_room"  # Only ZHA areas get groups
        }
        
        return client
    
    @pytest.mark.asyncio
    async def test_mixed_area_scenarios(self, client_with_mixed_areas):
        """Test different area scenarios: ZHA-only, mixed, and WiFi-only."""
        client = await client_with_mixed_areas
        
        # Test adaptive values
        adaptive_values = {
            'kelvin': 3000,
            'brightness': 75,
            'rgb': (255, 200, 150),
            'xy': (0.4, 0.4)
        }
        
        # Test 1: ZHA-only area (living_room) should use ZHA group entity
        await client.turn_on_lights_adaptive("living_room", adaptive_values)
        assert client.call_service.call_count == 1
        call_args = client.call_service.call_args
        target = call_args[0][3]  # Fourth positional arg is target
        assert "entity_id" in target
        assert target["entity_id"] == "light.glo_living_room"
        
        # Test 2: Mixed area (bedroom) should use area-based control
        client.call_service.reset_mock()
        await client.turn_on_lights_adaptive("bedroom", adaptive_values)
        assert client.call_service.call_count == 1
        call_args = client.call_service.call_args
        target = call_args[0][3]  # Fourth positional arg is target
        assert "area_id" in target
        assert target["area_id"] == "bedroom"
        
        # Test 3: WiFi-only area (kitchen) should use area-based control
        client.call_service.reset_mock()
        await client.turn_on_lights_adaptive("kitchen", adaptive_values)
        assert client.call_service.call_count == 1
        call_args = client.call_service.call_args
        target = call_args[0][3]  # Fourth positional arg is target
        assert "area_id" in target
        assert target["area_id"] == "kitchen"


class TestEdgeCases:
    """Test edge cases in mixed protocol handling."""
    
    @pytest.mark.asyncio
    async def test_area_with_no_devices(self):
        """Test handling of area with no light devices."""
        controller = ZigBeeController(MagicMock())
        controller.ws_client.send_message_wait_response = AsyncMock(side_effect=[
            [{"area_id": "empty", "name": "Empty"}],
            [],  # No devices
            [],  # No entities
            []   # No ZHA devices
        ])
        controller.ws_client.get_states = AsyncMock(return_value=[])
        
        has_parity = await controller.check_area_zha_parity("empty")
        assert has_parity is False
    
    @pytest.mark.asyncio
    async def test_matter_devices_treated_as_non_zha(self):
        """Test that Matter devices are correctly identified as non-ZHA."""
        controller = ZigBeeController(MagicMock())
        controller.ws_client.send_message_wait_response = AsyncMock(side_effect=[
            [{"area_id": "office", "name": "Office"}],
            [
                {"id": "d1", "area_id": "office", "identifiers": [["zha", "00:11:22:33:44:55:66:77"]]},
                {"id": "d2", "area_id": "office", "identifiers": [["matter", "AABBCCDD"]]}
            ],
            [
                {"entity_id": "light.zha", "device_id": "d1"},
                {"entity_id": "light.matter", "device_id": "d2"}
            ],
            [{"device_id": "d1", "ieee": "00:11:22:33:44:55:66:77"}]
        ])
        controller.ws_client.get_states = AsyncMock(return_value=[
            {"entity_id": "light.zha", "attributes": {"area_id": "office"}},
            {"entity_id": "light.matter", "attributes": {"area_id": "office"}}
        ])
        
        has_parity = await controller.check_area_zha_parity("office")
        assert has_parity is False  # Matter device means no parity
    
    @pytest.mark.asyncio
    async def test_zwave_devices_treated_as_non_zha(self):
        """Test that Z-Wave devices are correctly identified as non-ZHA."""
        controller = ZigBeeController(MagicMock())
        controller.ws_client.send_message_wait_response = AsyncMock(side_effect=[
            [{"area_id": "garage", "name": "Garage"}],
            [
                {"id": "d1", "area_id": "garage", "identifiers": [["zha", "00:11:22:33:44:55:66:77"]]},
                {"id": "d2", "area_id": "garage", "identifiers": [["zwave_js", "3-7-0-1"]]}
            ],
            [
                {"entity_id": "light.zha", "device_id": "d1"},
                {"entity_id": "light.zwave", "device_id": "d2"}
            ],
            [{"device_id": "d1", "ieee": "00:11:22:33:44:55:66:77"}]
        ])
        controller.ws_client.get_states = AsyncMock(return_value=[
            {"entity_id": "light.zha", "attributes": {"area_id": "garage"}},
            {"entity_id": "light.zwave", "attributes": {"area_id": "garage"}}
        ])
        
        has_parity = await controller.check_area_zha_parity("garage")
        assert has_parity is False  # Z-Wave device means no parity