from __future__ import annotations
import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Not used in normal flow (we'll prefer IMPORT), but keep it no-form too."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        _LOGGER.info("[%s] Creating entry via USER step.", DOMAIN)
        return self.async_create_entry(title="MagicLight", data={})

    async def async_step_import(self, user_input: dict[str, Any]) -> FlowResult:
        """Called from __init__.py on startup."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        _LOGGER.info("[%s] Creating entry via IMPORT step.", DOMAIN)
        return self.async_create_entry(title="MagicLight", data={})

    async def async_step_hassio(self, discovery_info: dict[str, Any]) -> FlowResult:
        """Optional: auto-create via Supervisor discovery as well."""
        return await self.async_step_import({})