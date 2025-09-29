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
        self.client.primitives = MagicMock()
        self.client.primitives.magiclight_on = AsyncMock()
        self.client.primitives.magiclight_off = AsyncMock()
        self.client.primitives.magiclight_toggle = AsyncMock()
        self.client.primitives.magiclight_toggle_multiple = AsyncMock()
        self.client.primitives.step_up = AsyncMock()
        self.client.primitives.step_down = AsyncMock()
        self.client.primitives.dim_up = AsyncMock()
        self.client.primitives.dim_down = AsyncMock()
        self.client.primitives.reset = AsyncMock()



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
    async def test_handle_magiclight_service_dim_up(self):
        """Test handling magiclight.dim_up service call."""
        message = {
            "type": "event",
            "event": {
                "event_type": "call_service",
                "data": {
                    "domain": "magiclight",
                    "service": "dim_up",
                    "service_data": {"area_id": "den"}
                }
            }
        }

        await self.client.handle_message(message)

        self.client.primitives.dim_up.assert_called_once_with("den", "service_call")

    @pytest.mark.asyncio
    async def test_handle_magiclight_service_dim_down(self):
        """Test handling magiclight.dim_down service call."""
        message = {
            "type": "event",
            "event": {
                "event_type": "call_service",
                "data": {
                    "domain": "magiclight",
                    "service": "dim_down",
                    "service_data": {"area_id": ["den", "hall"]}
                }
            }
        }

        await self.client.handle_message(message)

        self.client.primitives.dim_down.assert_any_call("den", "service_call")
        self.client.primitives.dim_down.assert_any_call("hall", "service_call")

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

            # Should log service call details at debug level
            mock_logger.debug.assert_any_call(
                "Service called: light.turn_on with data: {'brightness': 100}"
            )
            mock_logger.info.assert_not_called()

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
