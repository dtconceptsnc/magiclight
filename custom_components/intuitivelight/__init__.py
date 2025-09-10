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
    
    # Register services globally (not per config entry)
    # This ensures services are available even before adding the integration
    if DOMAIN not in hass.data or "services_registered" not in hass.data[DOMAIN]:
        await _register_services(hass)
        hass.data[DOMAIN]["services_registered"] = True
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Intuitive Light from a config entry."""
    _LOGGER.info("Setting up Intuitive Light integration")
    
    # Store the config entry for later use
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[entry.entry_id] = entry.data

    # Ensure services are registered even if async_setup wasn't called
    if not domain_data.get("services_registered"):
        await _register_services(hass)
        domain_data["services_registered"] = True
    
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
    # Remove config entry from domain
    if entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    # Check if this is the last config entry
    config_entries = [key for key in hass.data[DOMAIN].keys() if key != "services_registered"]
    if not config_entries:
        # Unregister services only if no config entries remain
        hass.services.async_remove(DOMAIN, SERVICE_STEP_UP)
        hass.services.async_remove(DOMAIN, SERVICE_STEP_DOWN)
        hass.data[DOMAIN].pop("services_registered", None)
    
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
