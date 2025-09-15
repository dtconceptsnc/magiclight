#!/usr/bin/env python3
"""Test suite for main.py event handling functionality."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from main import HomeAssistantWebSocketClient


class TestMainEventHandling:
    """Test cases for event handling in HomeAssistantWebSocketClient."""

    def setup_method(self):
        """Set up test environment for each test."""
        self.client = HomeAssistantWebSocketClient(
            host="localhost", port=8123, access_token="token"
        )

        # Mock components
        self.client.switch_processor = MagicMock()
        self.client.switch_processor.process_button_press = AsyncMock()
        self.client.primitives = MagicMock()
        self.client.primitives.magiclight_on = AsyncMock()
        self.client.primitives.magiclight_off = AsyncMock()
        self.client.primitives.magiclight_toggle = AsyncMock()
        self.client.primitives.magiclight_toggle_multiple = AsyncMock()
        self.client.primitives.step_up = AsyncMock()
        self.client.primitives.step_down = AsyncMock()
        self.client.primitives.reset = AsyncMock()

        # Set up device mapping
        self.client.device_to_area_mapping = {
            "00:12:34:56:78:90": "kitchen",
            "aa:bb:cc:dd:ee:ff": "living_room"
        }

    @pytest.mark.asyncio
    async def test_handle_zha_event_on_press(self):
        """Test handling ZHA event for on_press."""
        message = {
            "type": "event",
            "event": {
                "event_type": "zha_event",
                "data": {
                    "device_id": "device_123",
                    "device_ieee": "00:12:34:56:78:90",
                    "command": "on_press",
                    "args": {"press_type": "press", "button": "on"}
                }
            }
        }

        await self.client.handle_message(message)

        # Should call switch processor
        self.client.switch_processor.process_button_press.assert_called_once_with(
            "device_123", "on_press", "on"
        )

    @pytest.mark.asyncio
    async def test_handle_zha_event_off_press(self):
        """Test handling ZHA event for off_press."""
        message = {
            "type": "event",
            "event": {
                "event_type": "zha_event",
                "data": {
                    "device_id": "device_456",
                    "device_ieee": "aa:bb:cc:dd:ee:ff",
                    "command": "off_press",
                    "args": {"press_type": "press", "button": "off"}
                }
            }
        }

        await self.client.handle_message(message)

        self.client.switch_processor.process_button_press.assert_called_once_with(
            "device_456", "off_press", "off"
        )

    @pytest.mark.asyncio
    async def test_handle_zha_event_up_down_press(self):
        """Test handling ZHA event for up/down press."""
        # Test up press
        message_up = {
            "type": "event",
            "event": {
                "event_type": "zha_event",
                "data": {
                    "device_id": "device_123",
                    "device_ieee": "00:12:34:56:78:90",
                    "command": "up_press",
                    "args": {"press_type": "press", "button": "up"}
                }
            }
        }

        await self.client.handle_message(message_up)

        self.client.switch_processor.process_button_press.assert_called_with(
            "device_123", "up_press", "up"
        )

        # Test down press
        message_down = {
            "type": "event",
            "event": {
                "event_type": "zha_event",
                "data": {
                    "device_id": "device_123",
                    "device_ieee": "00:12:34:56:78:90",
                    "command": "down_press",
                    "args": {"press_type": "press", "button": "down"}
                }
            }
        }

        await self.client.handle_message(message_down)

        self.client.switch_processor.process_button_press.assert_called_with(
            "device_123", "down_press", "down"
        )

    @pytest.mark.asyncio
    async def test_handle_zha_event_unsupported_command(self):
        """Test handling ZHA event with unsupported command."""
        message = {
            "type": "event",
            "event": {
                "event_type": "zha_event",
                "data": {
                    "device_id": "device_123",
                    "device_ieee": "00:12:34:56:78:90",
                    "command": "unsupported_command",
                    "args": {}
                }
            }
        }

        await self.client.handle_message(message)

        # Should not call switch processor for unsupported commands
        self.client.switch_processor.process_button_press.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_magiclight_service_on(self):
        """Test handling magiclight.magiclight_on service call."""
        message = {
            "type": "event",
            "event": {
                "event_type": "call_service",
                "data": {
                    "domain": "magiclight",
                    "service": "magiclight_on",
                    "service_data": {"area_id": "kitchen"}
                }
            }
        }

        await self.client.handle_message(message)

        self.client.primitives.magiclight_on.assert_called_once_with("kitchen", "service_call")

    @pytest.mark.asyncio
    async def test_handle_magiclight_service_off(self):
        """Test handling magiclight.magiclight_off service call."""
        message = {
            "type": "event",
            "event": {
                "event_type": "call_service",
                "data": {
                    "domain": "magiclight",
                    "service": "magiclight_off",
                    "service_data": {"area_id": "living_room"}
                }
            }
        }

        await self.client.handle_message(message)

        self.client.primitives.magiclight_off.assert_called_once_with("living_room", "service_call")

    @pytest.mark.asyncio
    async def test_handle_magiclight_service_toggle_single(self):
        """Test handling magiclight.magiclight_toggle service call for single area."""
        message = {
            "type": "event",
            "event": {
                "event_type": "call_service",
                "data": {
                    "domain": "magiclight",
                    "service": "magiclight_toggle",
                    "service_data": {"area_id": "kitchen"}
                }
            }
        }

        await self.client.handle_message(message)

        self.client.primitives.magiclight_toggle_multiple.assert_called_once_with(
            ["kitchen"], "service_call"
        )

    @pytest.mark.asyncio
    async def test_handle_magiclight_service_toggle_multiple(self):
        """Test handling magiclight.magiclight_toggle service call for multiple areas."""
        message = {
            "type": "event",
            "event": {
                "event_type": "call_service",
                "data": {
                    "domain": "magiclight",
                    "service": "magiclight_toggle",
                    "service_data": {"area_id": ["kitchen", "living_room"]}
                }
            }
        }

        await self.client.handle_message(message)

        self.client.primitives.magiclight_toggle_multiple.assert_called_once_with(
            ["kitchen", "living_room"], "service_call"
        )

    @pytest.mark.asyncio
    async def test_handle_magiclight_service_step_up(self):
        """Test handling magiclight.step_up service call."""
        message = {
            "type": "event",
            "event": {
                "event_type": "call_service",
                "data": {
                    "domain": "magiclight",
                    "service": "step_up",
                    "service_data": {"area_id": "kitchen"}
                }
            }
        }

        await self.client.handle_message(message)

        self.client.primitives.step_up.assert_called_once_with("kitchen", "service_call")

    @pytest.mark.asyncio
    async def test_handle_magiclight_service_step_down(self):
        """Test handling magiclight.step_down service call."""
        message = {
            "type": "event",
            "event": {
                "event_type": "call_service",
                "data": {
                    "domain": "magiclight",
                    "service": "step_down",
                    "service_data": {"area_id": "living_room"}
                }
            }
        }

        await self.client.handle_message(message)

        self.client.primitives.step_down.assert_called_once_with("living_room", "service_call")

    @pytest.mark.asyncio
    async def test_handle_magiclight_service_reset(self):
        """Test handling magiclight.reset service call."""
        message = {
            "type": "event",
            "event": {
                "event_type": "call_service",
                "data": {
                    "domain": "magiclight",
                    "service": "reset",
                    "service_data": {"area_id": "kitchen"}
                }
            }
        }

        await self.client.handle_message(message)

        self.client.primitives.reset.assert_called_once_with("kitchen", "service_call")

    @pytest.mark.asyncio
    async def test_handle_magiclight_service_missing_area_id(self):
        """Test handling magiclight service call without area_id."""
        message = {
            "type": "event",
            "event": {
                "event_type": "call_service",
                "data": {
                    "domain": "magiclight",
                    "service": "magiclight_on",
                    "service_data": {}
                }
            }
        }

        await self.client.handle_message(message)

        # Should not call primitive without area_id
        self.client.primitives.magiclight_on.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_magiclight_service_unsupported(self):
        """Test handling unsupported magiclight service call."""
        message = {
            "type": "event",
            "event": {
                "event_type": "call_service",
                "data": {
                    "domain": "magiclight",
                    "service": "unsupported_service",
                    "service_data": {"area_id": "kitchen"}
                }
            }
        }

        await self.client.handle_message(message)

        # Should not call any primitives
        self.client.primitives.magiclight_on.assert_not_called()
        self.client.primitives.magiclight_off.assert_not_called()
        self.client.primitives.step_up.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_non_magiclight_service_call(self):
        """Test handling non-magiclight service call."""
        message = {
            "type": "event",
            "event": {
                "event_type": "call_service",
                "data": {
                    "domain": "light",
                    "service": "turn_on",
                    "service_data": {"entity_id": "light.kitchen"}
                }
            }
        }

        await self.client.handle_message(message)

        # Should not call any magiclight primitives
        self.client.primitives.magiclight_on.assert_not_called()
        self.client.primitives.step_up.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_state_changed_event(self):
        """Test handling state_changed event."""
        message = {
            "type": "event",
            "event": {
                "event_type": "state_changed",
                "data": {
                    "entity_id": "sun.sun",
                    "new_state": {
                        "state": "above_horizon",
                        "attributes": {
                            "elevation": 45.0,
                            "azimuth": 180.0
                        }
                    }
                }
            }
        }

        await self.client.handle_message(message)

        # Should update sun data
        assert "elevation" in self.client.sun_data
        assert self.client.sun_data["elevation"] == 45.0

    @pytest.mark.asyncio
    async def test_handle_message_non_event_type(self):
        """Test handling non-event message types."""
        message = {
            "type": "result",
            "id": 1,
            "success": True,
            "result": {}
        }

        # Should not raise exception
        await self.client.handle_message(message)

    @pytest.mark.asyncio
    async def test_handle_message_malformed(self):
        """Test handling malformed messages."""
        # Missing event key
        message = {
            "type": "event"
        }

        await self.client.handle_message(message)

        # Missing event_type
        message2 = {
            "type": "event",
            "event": {}
        }

        await self.client.handle_message(message2)

        # Should not call any primitives
        self.client.primitives.magiclight_on.assert_not_called()

    @pytest.mark.asyncio
    async def test_zha_event_button_extraction(self):
        """Test ZHA event button extraction from args."""
        # Test with button in args
        message = {
            "type": "event",
            "event": {
                "event_type": "zha_event",
                "data": {
                    "device_id": "device_123",
                    "device_ieee": "00:12:34:56:78:90",
                    "command": "on_press",
                    "args": {"button": "on", "press_type": "press"}
                }
            }
        }

        await self.client.handle_message(message)

        self.client.switch_processor.process_button_press.assert_called_once_with(
            "device_123", "on_press", "on"
        )

    @pytest.mark.asyncio
    async def test_zha_event_button_from_command(self):
        """Test ZHA event button extraction from command when args missing."""
        # Test with no button in args, should NOT be processed without button
        message = {
            "type": "event",
            "event": {
                "event_type": "zha_event",
                "data": {
                    "device_id": "device_123",
                    "device_ieee": "00:12:34:56:78:90",
                    "command": "off_hold",
                    "args": {}
                }
            }
        }

        await self.client.handle_message(message)

        # Should NOT call switch processor without button in args
        self.client.switch_processor.process_button_press.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_with_logging(self):
        """Test that message handling includes proper logging."""
        message = {
            "type": "event",
            "event": {
                "event_type": "call_service",
                "data": {
                    "domain": "light",
                    "service": "turn_on",
                    "service_data": {"brightness": 100}
                }
            }
        }

        with patch('main.logger') as mock_logger:
            await self.client.handle_message(message)

            # Should log service call details
            mock_logger.info.assert_called()
            log_call = mock_logger.info.call_args_list[0][0][0]
            assert "Service called" in log_call
            assert "light.turn_on" in log_call

    @pytest.mark.asyncio
    async def test_sun_entity_state_update(self):
        """Test sun entity state update handling."""
        message = {
            "type": "event",
            "event": {
                "event_type": "state_changed",
                "data": {
                    "entity_id": "sun.sun",
                    "new_state": {
                        "state": "below_horizon",
                        "attributes": {
                            "elevation": -10.5,
                            "azimuth": 90.0,
                            "rising": False
                        }
                    }
                }
            }
        }

        await self.client.handle_message(message)

        # Should update sun data with attributes only (not state)
        expected_data = {
            "elevation": -10.5,
            "azimuth": 90.0,
            "rising": False
        }

        for key, value in expected_data.items():
            assert self.client.sun_data[key] == value