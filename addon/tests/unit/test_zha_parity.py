"""Tests for ZHA parity checking and control method selection."""

import asyncio
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, Mock

import pytest

# Add magiclight directory to Python path
magiclight_path = Path(__file__).parent.parent.parent / 'magiclight'
sys.path.insert(0, str(magiclight_path))


from light_controller import ZigBeeController, Protocol, HomeAssistantController, MultiProtocolController, LightCommand
from brain import ColorMode
from main import HomeAssistantWebSocketClient


class TestZHAParity:
    """Test ZHA parity checking functionality."""
    
    @pytest.fixture
    def mock_ws_client(self):
        """Create a mock WebSocket client."""
        client = MagicMock(spec=HomeAssistantWebSocketClient)
        client.send_message_wait_response = AsyncMock()
        client.get_states = AsyncMock()
        return client
    
    @pytest.fixture
    def zigbee_controller(self, mock_ws_client):
        """Create a ZigBee controller instance."""
        return ZigBeeController(mock_ws_client)
    
    @pytest.mark.asyncio
    async def test_area_with_only_zha_lights_has_parity(self, zigbee_controller, mock_ws_client):
        """Test that an area with only ZHA lights returns True for parity."""
        # Mock area registry response
        mock_ws_client.send_message_wait_response.side_effect = [
            # Area registry response
            [{"area_id": "living_room", "name": "Living Room"}],
            # Device registry response
            [
                {
                    "id": "device1",
                    "area_id": "living_room",
                    "identifiers": [["zha", "00:11:22:33:44:55:66:77"]]
                },
                {
                    "id": "device2",
                    "area_id": "living_room",
                    "identifiers": [["zha", "00:11:22:33:44:55:66:88"]]
                }
            ],
            # Entity registry response
            [
                {"entity_id": "light.living_room_1", "device_id": "device1"},
                {"entity_id": "light.living_room_2", "device_id": "device2"}
            ],
            # ZHA devices response
            [
                {"device_id": "device1", "ieee": "00:11:22:33:44:55:66:77", "name": "Light 1"},
                {"device_id": "device2", "ieee": "00:11:22:33:44:55:66:88", "name": "Light 2"}
            ]
        ]
        
        # Mock states response
        mock_ws_client.get_states.return_value = [
            {
                "entity_id": "light.living_room_1",
                "attributes": {"area_id": "living_room", "manufacturer": "Philips", "model": "Hue"}
            },
            {
                "entity_id": "light.living_room_2",
                "attributes": {"area_id": "living_room", "manufacturer": "IKEA", "model": "TRADFRI"}
            }
        ]
        
        # Check parity
        has_parity = await zigbee_controller.check_area_zha_parity("living_room")
        assert has_parity is True
    
    @pytest.mark.asyncio
    async def test_area_with_mixed_lights_no_parity(self, zigbee_controller, mock_ws_client):
        """Test that an area with mixed ZHA and non-ZHA lights returns False for parity."""
        # Mock area registry response
        mock_ws_client.send_message_wait_response.side_effect = [
            # Area registry response
            [{"area_id": "bedroom", "name": "Bedroom"}],
            # Device registry response
            [
                {
                    "id": "device1",
                    "area_id": "bedroom",
                    "identifiers": [["zha", "00:11:22:33:44:55:66:77"]]
                },
                {
                    "id": "device2",
                    "area_id": "bedroom",
                    "identifiers": [["wiz", "AA:BB:CC:DD:EE:FF"]]  # WiFi device
                }
            ],
            # Entity registry response
            [
                {"entity_id": "light.bedroom_zha", "device_id": "device1"},
                {"entity_id": "light.bedroom_wifi", "device_id": "device2"}
            ],
            # ZHA devices response
            [
                {"device_id": "device1", "ieee": "00:11:22:33:44:55:66:77", "name": "ZHA Light"}
            ]
        ]
        
        # Mock states response
        mock_ws_client.get_states.return_value = [
            {
                "entity_id": "light.bedroom_zha",
                "attributes": {"area_id": "bedroom", "manufacturer": "Philips", "model": "Hue"}
            },
            {
                "entity_id": "light.bedroom_wifi",
                "attributes": {"area_id": "bedroom", "manufacturer": "WiZ", "model": "WiFi Bulb"}
            }
        ]
        
        # Check parity
        has_parity = await zigbee_controller.check_area_zha_parity("bedroom")
        assert has_parity is False
    
    @pytest.mark.asyncio
    async def test_area_with_no_lights_returns_false(self, zigbee_controller, mock_ws_client):
        """Test that an area with no lights returns False."""
        # Mock area registry response
        mock_ws_client.send_message_wait_response.side_effect = [
            # Area registry response
            [{"area_id": "bathroom", "name": "Bathroom"}],
            # Device registry response (no light devices)
            [],
            # Entity registry response
            [],
            # ZHA devices response
            []
        ]
        
        # Mock states response (no light entities)
        mock_ws_client.get_states.return_value = []
        
        # Check parity
        has_parity = await zigbee_controller.check_area_zha_parity("bathroom")
        assert has_parity is False
    
    @pytest.mark.asyncio
    async def test_nonexistent_area_returns_false(self, zigbee_controller, mock_ws_client):
        """Test that a non-existent area returns False."""
        # Mock area registry response with no matching area
        mock_ws_client.send_message_wait_response.side_effect = [
            # Area registry response
            [{"area_id": "other_room", "name": "Other Room"}],
            # Device registry response
            [],
            # Entity registry response
            [],
            # ZHA devices response
            []
        ]
        
        # Mock states response
        mock_ws_client.get_states.return_value = []
        
        # Check parity for non-existent area
        has_parity = await zigbee_controller.check_area_zha_parity("nonexistent_area")
        assert has_parity is False
    
    @pytest.mark.asyncio
    async def test_sync_groups_only_for_parity_areas(self, zigbee_controller, mock_ws_client):
        """Test that ZHA groups are only created for areas with ZHA parity."""
        # Mock responses for sync_zha_groups_with_areas
        # The order matters - sync_zha_groups_with_areas calls:
        # 1. list_zha_groups() 
        # 2. get_areas() which calls multiple WebSocket methods
        # 3. list_zha_devices()
        # 4. create_group() for areas with parity
        # 5. list_zha_groups() again after creation
        
        mock_ws_client.send_message_wait_response.side_effect = [
            # First call: Get area registry for ensure_glo_area_exists
            [],  # No existing areas
            # Second call: Create Magic_Zigbee_Groups area
            {"area_id": "glo_area"},
            # Third call: list existing ZHA groups (empty)
            [],
            # get_areas() calls start here:
            # 4. Get area registry
            [
                {"area_id": "room1", "name": "Room 1"},
                {"area_id": "room2", "name": "Room 2"},
                {"area_id": "glo_area", "name": "Magic_Zigbee_Groups"}
            ],
            # 5. Get device registry
            [
                {
                    "id": "dev1",
                    "area_id": "room1",
                    "identifiers": [["zha", "00:11:22:33:44:55:66:77"]]
                },
                {
                    "id": "dev2",
                    "area_id": "room2",
                    "identifiers": [["zha", "00:11:22:33:44:55:66:88"]]
                },
                {
                    "id": "dev3",
                    "area_id": "room2",
                    "identifiers": [["wifi", "AA:BB:CC:DD:EE:FF"]]
                }
            ],
            # 6. Get entity registry
            [
                {"entity_id": "light.room1_light", "device_id": "dev1"},
                {"entity_id": "light.room2_zha", "device_id": "dev2"},
                {"entity_id": "light.room2_wifi", "device_id": "dev3"}
            ],
            # 7. List ZHA devices (for get_areas)
            [
                {"device_id": "dev1", "ieee": "00:11:22:33:44:55:66:77", "name": "Light 1"},
                {"device_id": "dev2", "ieee": "00:11:22:33:44:55:66:88", "name": "Light 2"}
            ],
            # Back to sync_zha_groups_with_areas:
            # 8. List ZHA devices again (for member lookup)
            [
                {"device_id": "dev1", "ieee": "00:11:22:33:44:55:66:77", "name": "Light 1"},
                {"device_id": "dev2", "ieee": "00:11:22:33:44:55:66:88", "name": "Light 2"}
            ],
            # 9. Create group response for room1 (has parity)
            {"success": True},
            # 10. List groups after creation
            [{"name": "Magic_Room_1", "group_id": 1001}]
        ]
        
        mock_ws_client.get_states.return_value = [
            {
                "entity_id": "light.room1_light",
                "attributes": {"area_id": "room1"}
            },
            {
                "entity_id": "light.room2_zha",
                "attributes": {"area_id": "room2"}
            },
            {
                "entity_id": "light.room2_wifi",
                "attributes": {"area_id": "room2"}
            }
        ]
        
        # Run sync
        success, areas_dict = await zigbee_controller.sync_zha_groups_with_areas()
        
        assert success is True
        # Verify that only room1 got a group (has ZHA parity)
        assert "Room 1" in zigbee_controller.area_to_group_id


class TestControlMethodSelection:
    """Test control method selection based on ZHA parity."""
    
    @pytest.mark.asyncio
    async def test_turn_on_lights_uses_zha_for_parity_area(self):
        """Test that areas with ZHA parity use ZHA group control."""
        client = HomeAssistantWebSocketClient("localhost", 8123, "test_token")
        
        # Set up the parity cache and area mappings
        client.area_parity_cache = {"living_room": True}
        client.area_to_light_entity = {"living_room": "light.glo_living_room"}
        client.call_service = AsyncMock()
        client.color_mode = ColorMode.XY
        
        # Call turn_on_lights_adaptive
        adaptive_values = {
            'kelvin': 3000,
            'brightness': 75,
            'rgb': (255, 200, 150),
            'xy': (0.4, 0.4)
        }
        
        await client.turn_on_lights_adaptive("living_room", adaptive_values)
        
        # Verify entity_id was used (not area_id)
        client.call_service.assert_called_once()
        call_args = client.call_service.call_args
        # call_service is called with (domain, service, service_data, target)
        assert call_args[0][0] == "light"  # domain
        assert call_args[0][1] == "turn_on"  # service
        service_data = call_args[0][2]  # service_data
        target = call_args[0][3]  # target
        assert "entity_id" in target
        assert target["entity_id"] == "light.glo_living_room"
    
    @pytest.mark.asyncio
    async def test_turn_on_lights_uses_area_for_mixed_lights(self):
        """Test that areas with mixed lights use area-based control."""
        client = HomeAssistantWebSocketClient("localhost", 8123, "test_token")
        
        # Set up the parity cache and area mappings
        client.area_parity_cache = {"bedroom": False}  # No parity
        client.area_to_light_entity = {"bedroom": "light.glo_bedroom"}
        client.call_service = AsyncMock()
        client.color_mode = ColorMode.XY
        
        # Call turn_on_lights_adaptive
        adaptive_values = {
            'kelvin': 3000,
            'brightness': 75,
            'rgb': (255, 200, 150),
            'xy': (0.4, 0.4)
        }
        
        await client.turn_on_lights_adaptive("bedroom", adaptive_values)
        
        # Verify area_id was used (not entity_id)
        client.call_service.assert_called_once()
        call_args = client.call_service.call_args
        # call_service is called with (domain, service, service_data, target)
        assert call_args[0][0] == "light"  # domain
        assert call_args[0][1] == "turn_on"  # service
        service_data = call_args[0][2]  # service_data
        target = call_args[0][3]  # target
        assert "area_id" in target
        assert target["area_id"] == "bedroom"
    
    @pytest.mark.asyncio
    async def test_fallback_when_no_zha_group(self):
        """Test fallback to area control when no ZHA group entity exists."""
        client = HomeAssistantWebSocketClient("localhost", 8123, "test_token")
        
        # Set up with no ZHA group entity
        client.area_parity_cache = {}  # No parity info
        client.area_to_light_entity = {}  # No ZHA group entities
        client.call_service = AsyncMock()
        client.color_mode = ColorMode.XY
        
        # Call turn_on_lights_adaptive
        adaptive_values = {
            'kelvin': 3000,
            'brightness': 75,
            'rgb': (255, 200, 150),
            'xy': (0.4, 0.4)
        }
        
        await client.turn_on_lights_adaptive("any_room", adaptive_values)
        
        # Verify area_id was used as fallback
        client.call_service.assert_called_once()
        call_args = client.call_service.call_args
        # call_service is called with (domain, service, service_data, target)
        assert call_args[0][0] == "light"  # domain
        assert call_args[0][1] == "turn_on"  # service
        service_data = call_args[0][2]  # service_data
        target = call_args[0][3]  # target
        assert "area_id" in target
        assert target["area_id"] == "any_room"