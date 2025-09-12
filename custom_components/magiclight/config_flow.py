"""Config flow for MagicLight integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MagicLight."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        _LOGGER.debug("[%s] config_flow: async_step_user called. user_input=%s", DOMAIN, user_input)
        errors = {}

        if user_input is not None:
            # Check if already configured
            await self.async_set_unique_id("magiclight_services")
            _LOGGER.debug("[%s] config_flow: set unique_id=magiclight_services", DOMAIN)
            self._abort_if_unique_id_configured()

            # Create the config entry
            _LOGGER.info("[%s] config_flow: creating entry 'MagicLight Services'", DOMAIN)
            return self.async_create_entry(
                title="MagicLight Services", 
                data=user_input or {}
            )

        # Show form (no configuration needed, just confirmation)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            description_placeholders={
                "addon_required": "Note: This integration requires the MagicLight addon to be installed and running."
            }
        )
