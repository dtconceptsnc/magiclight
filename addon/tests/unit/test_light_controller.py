#!/usr/bin/env python3
"""Test suite for light_controller.py - Light control logic."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from light_controller import (
    LightController, ZigBeeController, HomeAssistantController,
    MultiProtocolController, LightControllerFactory,
    LightCommand, GroupCommand, Protocol
)


class TestLightCommand:
    """Test cases for LightCommand dataclass."""

    def test_light_command_defaults(self):
        """Test LightCommand default values."""
        cmd = LightCommand()

        assert cmd.area is None
        assert cmd.entity_ids is None
        assert cmd.brightness is None
        assert cmd.color_temp is None
        assert cmd.rgb_color is None
        assert cmd.xy_color is None
        assert cmd.transition is None
        assert cmd.on is True

    def test_light_command_with_values(self):
        """Test LightCommand with specified values."""
        cmd = LightCommand(
            area="kitchen",
            brightness=200,
            color_temp=3000,
            rgb_color=(255, 128, 64),
            transition=1.5,
            on=False
        )

        assert cmd.area == "kitchen"
        assert cmd.brightness == 200
        assert cmd.color_temp == 3000
        assert cmd.rgb_color == (255, 128, 64)
        assert cmd.transition == 1.5
        assert cmd.on is False


class TestGroupCommand:
    """Test cases for GroupCommand dataclass."""

    def test_group_command_defaults(self):
        """Test GroupCommand default values."""
        cmd = GroupCommand(name="test_group")

        assert cmd.name == "test_group"
        assert cmd.group_id is None
        assert cmd.members is None
        assert cmd.operation == "create"

    def test_group_command_with_values(self):
        """Test GroupCommand with specified values."""
        members = [{"ieee": "00:11:22:33:44:55", "endpoint_id": 1}]
        cmd = GroupCommand(
            name="magic_kitchen",
            group_id=100,
            members=members,
            operation="add_members"
        )

        assert cmd.name == "magic_kitchen"
        assert cmd.group_id == 100
        assert cmd.members == members
        assert cmd.operation == "add_members"


class TestZigBeeController:
    """Test cases for ZigBeeController."""

    def setup_method(self):
        """Set up test environment for each test."""
        self.mock_ws_client = MagicMock()
        self.mock_ws_client.call_service = AsyncMock()
        self.mock_ws_client.send_message_wait_response = AsyncMock()
        self.mock_ws_client.get_states = AsyncMock()
        self.controller = ZigBeeController(self.mock_ws_client)

    def test_init(self):
        """Test ZigBeeController initialization."""
        assert self.controller.protocol == Protocol.ZIGBEE
        assert isinstance(self.controller.area_to_group_id, dict)
        assert self.controller.ws_client is self.mock_ws_client

    @pytest.mark.asyncio
    async def test_turn_on_lights_with_brightness(self):
        """Test turning on lights with brightness."""
        command = LightCommand(
            entity_ids=["light.kitchen_1", "light.kitchen_2"],
            brightness=150,
            transition=1.0
        )

        result = await self.controller.turn_on_lights(command)

        assert result is True
        self.mock_ws_client.call_service.assert_called_once_with(
            "light", "turn_on",
            {
                "brightness": 150,
                "transition": 1.0
            },
            {"entity_id": ["light.kitchen_1", "light.kitchen_2"]}
        )

    @pytest.mark.asyncio
    async def test_turn_on_lights_with_color_temp(self):
        """Test turning on lights with color temperature."""
        command = LightCommand(
            entity_ids=["light.bedroom"],
            color_temp=3000,
            brightness=100
        )

        result = await self.controller.turn_on_lights(command)

        assert result is True
        call_args = self.mock_ws_client.call_service.call_args
        service_data = call_args[0][2]
        # ZigBee uses color_temp in mireds (1000000 / kelvin)
        assert service_data["color_temp"] == int(1000000 / 3000)
        assert service_data["brightness"] == 100

    @pytest.mark.asyncio
    async def test_turn_on_lights_with_rgb(self):
        """Test turning on lights with RGB color."""
        command = LightCommand(
            entity_ids=["light.living_room"],
            rgb_color=(255, 128, 64),
            brightness=200
        )

        result = await self.controller.turn_on_lights(command)

        assert result is True
        call_args = self.mock_ws_client.call_service.call_args
        service_data = call_args[0][2]
        assert service_data["rgb_color"] == [255, 128, 64]
        assert service_data["brightness"] == 200

    @pytest.mark.asyncio
    async def test_turn_on_lights_with_xy(self):
        """Test turning on lights with XY color."""
        command = LightCommand(
            entity_ids=["light.office"],
            xy_color=(0.5, 0.4),
            brightness=180
        )

        result = await self.controller.turn_on_lights(command)

        assert result is True
        call_args = self.mock_ws_client.call_service.call_args
        service_data = call_args[0][2]
        assert service_data["xy_color"] == [0.5, 0.4]

    @pytest.mark.asyncio
    async def test_turn_off_lights(self):
        """Test turning off lights."""
        command = LightCommand(
            entity_ids=["light.kitchen"],
            transition=2.0
        )

        result = await self.controller.turn_off_lights(command)

        assert result is True
        self.mock_ws_client.call_service.assert_called_once_with(
            "light", "turn_off",
            {"transition": 2.0},
            {"entity_id": ["light.kitchen"]}
        )

    @pytest.mark.asyncio
    async def test_turn_lights_service_call_exception(self):
        """Test turn on lights with service call exception."""
        command = LightCommand(entity_ids=["light.kitchen"])
        self.mock_ws_client.call_service.side_effect = Exception("Service call failed")

        result = await self.controller.turn_on_lights(command)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_light_state(self):
        """Test getting light state."""
        # The method calls get_states() and expects a list of states
        mock_response = [{
            "entity_id": "light.kitchen",
            "state": "on",
            "attributes": {
                "brightness": 150,
                "color_temp": 300
            }
        }]
        self.mock_ws_client.get_states.return_value = mock_response

        result = await self.controller.get_light_state("light.kitchen")

        # Should return formatted state data
        expected = {
            'entity_id': 'light.kitchen',
            'state': 'on',
            'brightness': 150,
            'color_temp': 300,
            'rgb_color': None,
            'xy_color': None,
            'is_on': True
        }
        assert result == expected
        self.mock_ws_client.get_states.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_lights(self):
        """Test listing lights."""
        # The method calls get_states() and filters for ZHA lights
        mock_entities = [
            {"entity_id": "light.kitchen", "state": "on", "attributes": {"platform": "zha"}},
            {"entity_id": "light.living_room", "state": "off", "attributes": {"platform": "zha"}},
            {"entity_id": "light.other", "state": "on", "attributes": {"platform": "hue"}}  # Should be filtered out
        ]
        self.mock_ws_client.get_states.return_value = mock_entities

        result = await self.controller.list_lights()

        # Should only return ZHA lights
        assert len(result) == 2
        assert result[0]["entity_id"] == "light.kitchen"
        assert result[1]["entity_id"] == "light.living_room"

    @pytest.mark.asyncio
    async def test_supports_groups(self):
        """Test that ZigBee controller supports groups."""
        result = await self.controller.supports_groups()
        assert result is True

    @pytest.mark.asyncio
    async def test_create_group_success(self):
        """Test successful group creation."""
        command = GroupCommand(
            name="Magic_Kitchen",
            members=[{"ieee": "00:11:22:33:44:55", "endpoint_id": 1}]
        )

        self.mock_ws_client.send_message_wait_response.return_value = {"success": True}

        result = await self.controller.create_group(command)

        assert result is True
        self.mock_ws_client.send_message_wait_response.assert_called_once_with({
            "type": "zha/group/add",
            "group_name": "Magic_Kitchen",
            "members": command.members
        })

    @pytest.mark.asyncio
    async def test_manage_group_add_members(self):
        """Test adding members to group."""
        command = GroupCommand(
            name="Magic_Kitchen",
            group_id=100,
            members=[{"ieee": "00:11:22:33:44:66", "endpoint_id": 1}],
            operation="add_members"
        )

        self.mock_ws_client.send_message_wait_response.return_value = {"success": True}

        result = await self.controller.manage_group(command)

        assert result is True
        self.mock_ws_client.send_message_wait_response.assert_called_once_with({
            "type": "zha/group/members/add",
            "group_id": 100,
            "members": [{"ieee": "00:11:22:33:44:66", "endpoint_id": 1}]
        })

    @pytest.mark.asyncio
    async def test_manage_group_remove_members(self):
        """Test removing members from group."""
        command = GroupCommand(
            name="Magic_Kitchen",
            group_id=100,
            members=[{"ieee": "00:11:22:33:44:55", "endpoint_id": 1}],
            operation="remove_members"
        )

        self.mock_ws_client.send_message_wait_response.return_value = {"success": True}

        result = await self.controller.manage_group(command)

        assert result is True
        self.mock_ws_client.send_message_wait_response.assert_called_once_with({
            "type": "zha/group/members/remove",
            "group_id": 100,
            "members": [{"ieee": "00:11:22:33:44:55", "endpoint_id": 1}]
        })


class TestHomeAssistantController:
    """Test cases for HomeAssistantController."""

    def setup_method(self):
        """Set up test environment for each test."""
        self.mock_ws_client = MagicMock()
        self.mock_ws_client.call_service = AsyncMock()
        self.controller = HomeAssistantController(self.mock_ws_client)

    def test_init(self):
        """Test HomeAssistantController initialization."""
        assert self.controller.protocol == Protocol.HOMEASSISTANT

    @pytest.mark.asyncio
    async def test_turn_on_lights_area_based(self):
        """Test turning on lights using area-based control."""
        command = LightCommand(
            area="kitchen",
            brightness=150,
            color_temp=3000
        )

        result = await self.controller.turn_on_lights(command)

        assert result is True
        call_args = self.mock_ws_client.call_service.call_args
        assert call_args[0][0] == "light"  # domain
        assert call_args[0][1] == "turn_on"  # service
        # service_data is third arg, target is fourth arg
        service_data = call_args[0][2]
        target = call_args[0][3]
        assert target["area_id"] == "kitchen"
        assert service_data["brightness"] == 150
        assert service_data["color_temp"] == int(1000000 / 3000)  # Converted to mireds

    @pytest.mark.asyncio
    async def test_turn_on_lights_entity_based(self):
        """Test turning on lights using entity IDs."""
        command = LightCommand(
            entity_ids=["light.kitchen_1", "light.kitchen_2"],
            brightness=100
        )

        result = await self.controller.turn_on_lights(command)

        assert result is True
        call_args = self.mock_ws_client.call_service.call_args
        # service_data is third arg, target is fourth arg
        service_data = call_args[0][2]
        target = call_args[0][3]
        assert target["entity_id"] == ["light.kitchen_1", "light.kitchen_2"]
        assert service_data["brightness"] == 100

    @pytest.mark.asyncio
    async def test_supports_groups(self):
        """Test that HomeAssistant controller doesn't support groups."""
        result = await self.controller.supports_groups()
        assert result is False

    @pytest.mark.asyncio
    async def test_create_group_not_supported(self):
        """Test that group creation raises NotImplementedError."""
        command = GroupCommand(name="test_group")

        with pytest.raises(NotImplementedError):
            await self.controller.create_group(command)


class TestMultiProtocolController:
    """Test cases for MultiProtocolController."""

    def setup_method(self):
        """Set up test environment for each test."""
        self.mock_ws_client = MagicMock()
        self.mock_ws_client.area_parity_cache = {}
        self.controller = MultiProtocolController(self.mock_ws_client)

    def test_init(self):
        """Test MultiProtocolController initialization."""
        assert self.controller.ws_client is self.mock_ws_client
        assert isinstance(self.controller.controllers, dict)
        # Controllers start empty and are added on demand
        assert len(self.controller.controllers) == 0
        assert self.controller.default_protocol == Protocol.HOMEASSISTANT

    def test_add_controller(self):
        """Test adding a controller."""
        self.controller.add_controller(Protocol.ZIGBEE)

        assert Protocol.ZIGBEE in self.controller.controllers
        assert isinstance(self.controller.controllers[Protocol.ZIGBEE], ZigBeeController)

    def test_set_default_protocol(self):
        """Test setting default protocol."""
        self.controller.set_default_protocol(Protocol.ZIGBEE)

        assert self.controller.default_protocol == Protocol.ZIGBEE


class TestLightControllerFactory:
    """Test cases for LightControllerFactory."""

    def test_create_controller_zigbee(self):
        """Test creating ZigBee controller."""
        mock_ws_client = MagicMock()

        controller = LightControllerFactory.create_controller(Protocol.ZIGBEE, mock_ws_client)

        assert isinstance(controller, ZigBeeController)
        assert controller.protocol == Protocol.ZIGBEE

    def test_create_controller_homeassistant(self):
        """Test creating HomeAssistant controller."""
        mock_ws_client = MagicMock()

        controller = LightControllerFactory.create_controller(Protocol.HOMEASSISTANT, mock_ws_client)

        assert isinstance(controller, HomeAssistantController)
        assert controller.protocol == Protocol.HOMEASSISTANT

    def test_create_controller_unsupported(self):
        """Test creating controller for unsupported protocol."""
        mock_ws_client = MagicMock()

        with pytest.raises(NotImplementedError, match="Protocol Protocol.ZWAVE not yet implemented"):
            LightControllerFactory.create_controller(Protocol.ZWAVE, mock_ws_client)

    def test_create_multi_protocol_controller(self):
        """Test creating multi-protocol controller."""
        mock_ws_client = MagicMock()

        controller = LightControllerFactory.create_multi_protocol_controller(mock_ws_client)

        assert isinstance(controller, MultiProtocolController)
        assert controller.ws_client is mock_ws_client
        assert isinstance(controller.controllers, dict)


class TestProtocolEnum:
    """Test cases for Protocol enum."""

    def test_protocol_values(self):
        """Test protocol enum values."""
        assert Protocol.ZIGBEE.value == "zigbee"
        assert Protocol.ZWAVE.value == "zwave"
        assert Protocol.HOMEASSISTANT.value == "homeassistant"
        assert Protocol.WIFI.value == "wifi"
        assert Protocol.MATTER.value == "matter"

    def test_protocol_from_string(self):
        """Test creating protocol from string."""
        assert Protocol("zigbee") == Protocol.ZIGBEE
        assert Protocol("homeassistant") == Protocol.HOMEASSISTANT