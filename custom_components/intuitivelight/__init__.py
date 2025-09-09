"""The Intuitive Light integration."""
from __future__ import annotations

import logging
from typing import Any
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    SERVICE_STEP_UP,
    SERVICE_STEP_DOWN,
    ATTR_AREA_ID,
    ATTR_DEVICE_ID,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Intuitive Light component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Intuitive Light from a config entry."""
    _LOGGER.info("Setting up Intuitive Light integration")
    
    # Store the config entry for later use
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data
    
    # Register services
    await _register_services(hass)
    
    return True


async def _register_services(hass: HomeAssistant) -> None:
    """Register Intuitive Light services."""
    
    async def handle_step_up(call: ServiceCall) -> None:
        """Handle the step_up service call.
        
        The addon listens for these service calls via WebSocket events,
        so we don't need to make any API calls here.
        """
        area_id = call.data.get(ATTR_AREA_ID)
        device_id = call.data.get(ATTR_DEVICE_ID)
        
        _LOGGER.info(f"Step up service called for area: {area_id}, device: {device_id}")
        # The addon will receive this as a call_service event and handle it
    
    async def handle_step_down(call: ServiceCall) -> None:
        """Handle the step_down service call.
        
        The addon listens for these service calls via WebSocket events,
        so we don't need to make any API calls here.
        """
        area_id = call.data.get(ATTR_AREA_ID)
        device_id = call.data.get(ATTR_DEVICE_ID)
        
        _LOGGER.info(f"Step down service called for area: {area_id}, device: {device_id}")
        # The addon will receive this as a call_service event and handle it
    
    # Schema for services that require area_id or device_id
    area_device_schema = vol.Schema({
        vol.Optional(ATTR_AREA_ID): cv.string,
        vol.Optional(ATTR_DEVICE_ID): cv.string,
    })
    
    # Register services
    hass.services.async_register(
        DOMAIN, SERVICE_STEP_UP, handle_step_up, schema=area_device_schema
    )
    hass.services.async_register(
        DOMAIN, SERVICE_STEP_DOWN, handle_step_down, schema=area_device_schema
    )
    
    _LOGGER.info("Intuitive Light services registered")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unregister services
    hass.services.async_remove(DOMAIN, SERVICE_STEP_UP)
    hass.services.async_remove(DOMAIN, SERVICE_STEP_DOWN)
    
    # Remove config entry from domain
    hass.data[DOMAIN].pop(entry.entry_id)
    
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)