"""Simplified tests for ZHA parity checking functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock
import sys
from pathlib import Path

# Add magiclight directory to Python path
magiclight_path = Path(__file__).parent.parent.parent / 'magiclight'
sys.path.insert(0, str(magiclight_path))

# Create mock modules before importing
sys.modules['switch'] = Mock()
sys.modules['switch'].SwitchCommandProcessor = Mock

from light_controller import ZigBeeController


class TestZHAParitySimple:
    """Simplified tests for ZHA parity checking."""
    
    @pytest.fixture
    def mock_ws_client(self):
        """Create a mock WebSocket client."""
        client = MagicMock()
        client.send_message_wait_response = AsyncMock()
        client.get_states = AsyncMock()
        client.call_service = AsyncMock()
        return client
    
    @pytest.fixture
    def zigbee_controller(self, mock_ws_client):
        """Create a ZigBee controller instance."""
        return ZigBeeController(mock_ws_client)
    
    @pytest.mark.asyncio
    async def test_check_area_zha_parity_all_zha(self, zigbee_controller):
        """Test that an area with only ZHA lights has parity."""
        area_info = {
            'name': 'Living Room',
            'zha_lights': ['light.zha1', 'light.zha2'],
            'non_zha_lights': []
        }
        
        has_parity = await zigbee_controller.check_area_zha_parity(area_info)
        assert has_parity is True
    
    @pytest.mark.asyncio
    async def test_check_area_zha_parity_mixed(self, zigbee_controller):
        """Test that an area with mixed protocols doesn't have parity."""
        area_info = {
            'name': 'Kitchen',
            'zha_lights': ['light.zha1'],
            'non_zha_lights': ['light.wifi1']
        }
        
        has_parity = await zigbee_controller.check_area_zha_parity(area_info)
        assert has_parity is False
    
    @pytest.mark.asyncio
    async def test_check_area_zha_parity_no_zha(self, zigbee_controller):
        """Test that an area with no ZHA lights doesn't have parity."""
        area_info = {
            'name': 'Bedroom',
            'zha_lights': [],
            'non_zha_lights': ['light.wifi1', 'light.wifi2']
        }
        
        has_parity = await zigbee_controller.check_area_zha_parity(area_info)
        assert has_parity is False
    
    @pytest.mark.asyncio
    async def test_list_zha_groups(self, zigbee_controller, mock_ws_client):
        """Test listing ZHA groups."""
        mock_response = [
            {"group_id": 1, "name": "Group 1", "members": ["00:11:22:33:44:55:66:77"]},
            {"group_id": 2, "name": "Group 2", "members": []}
        ]
        mock_ws_client.send_message_wait_response.return_value = mock_response
        
        groups = await zigbee_controller.list_zha_groups()
        
        assert len(groups) == 2
        assert groups[0]["name"] == "Group 1"
        assert len(groups[0]["members"]) == 1
        assert groups[1]["name"] == "Group 2"
        assert len(groups[1]["members"]) == 0
    
    @pytest.mark.asyncio
    async def test_list_zha_devices(self, zigbee_controller, mock_ws_client):
        """Test listing ZHA devices."""
        mock_response = [
            {"ieee": "00:11:22:33:44:55:66:77", "device_id": "dev1", "name": "Light 1"},
            {"ieee": "00:11:22:33:44:55:66:88", "device_id": "dev2", "name": "Light 2"}
        ]
        mock_ws_client.send_message_wait_response.return_value = mock_response
        
        devices = await zigbee_controller.list_zha_devices()
        
        assert len(devices) == 2
        assert devices[0]["ieee"] == "00:11:22:33:44:55:66:77"
        assert devices[1]["name"] == "Light 2"