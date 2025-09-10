"""The HomeGlo integration."""
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
    SERVICE_RESET,
    SERVICE_HOMEGLO_ON,
    SERVICE_HOMEGLO_OFF,
    ATTR_AREA_ID,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the HomeGlo component."""
    _LOGGER.debug("[%s] async_setup called with config keys: %s", DOMAIN, list(config.keys()))

    hass.data.setdefault(DOMAIN, {})

    # Register services globally (not per config entry)
    # This ensures services are available even before adding the integration
    if "services_registered" not in hass.data[DOMAIN]:
        _LOGGER.info("[%s] Registering services from async_setup", DOMAIN)
        await _register_services(hass)
        hass.data[DOMAIN]["services_registered"] = True
    else:
        _LOGGER.debug("[%s] Services already registered; skipping registration in async_setup", DOMAIN)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HomeGlo from a config entry."""
    _LOGGER.info("[%s] async_setup_entry: id=%s title=%s", DOMAIN, entry.entry_id, entry.title)

    # Store the config entry for later use
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[entry.entry_id] = entry.data
    _LOGGER.debug("[%s] Stored config entry. Domain data keys now: %s", DOMAIN, list(domain_data.keys()))

    # Ensure services are registered even if async_setup wasn't called
    if not domain_data.get("services_registered"):
        _LOGGER.info("[%s] Registering services from async_setup_entry", DOMAIN)
        await _register_services(hass)
        domain_data["services_registered"] = True
    else:
        _LOGGER.debug("[%s] Services already registered; skipping registration in async_setup_entry", DOMAIN)

    return True


async def _register_services(hass: HomeAssistant) -> None:
    """Register HomeGlo services."""
    _LOGGER.debug("[%s] _register_services invoked", DOMAIN)
    
    async def handle_step_up(call: ServiceCall) -> None:
        """Handle the step_up service call.
        
        The addon listens for these service calls via WebSocket events,
        so we don't need to make any API calls here.
        """
        area_id = call.data.get(ATTR_AREA_ID)
        
        _LOGGER.info("[%s] step_up called: area_id=%s", DOMAIN, area_id)
        # The addon will receive this as a call_service event and handle it
    
    async def handle_step_down(call: ServiceCall) -> None:
        """Handle the step_down service call.
        
        The addon listens for these service calls via WebSocket events,
        so we don't need to make any API calls here.
        """
        area_id = call.data.get(ATTR_AREA_ID)
        
        _LOGGER.info("[%s] step_down called: area_id=%s", DOMAIN, area_id)
        # The addon will receive this as a call_service event and handle it
    
    async def handle_reset(call: ServiceCall) -> None:
        """Handle the reset service call.
        
        The addon listens for these service calls via WebSocket events,
        so we don't need to make any API calls here.
        """
        area_id = call.data.get(ATTR_AREA_ID)
        
        _LOGGER.info("[%s] reset called: area_id=%s", DOMAIN, area_id)
        # The addon will receive this as a call_service event and handle it
    
    async def handle_homeglo_on(call: ServiceCall) -> None:
        """Handle the homeglo_on service call.
        
        The addon listens for these service calls via WebSocket events,
        so we don't need to make any API calls here.
        """
        area_id = call.data.get(ATTR_AREA_ID)
        
        _LOGGER.info("[%s] homeglo_on called: area_id=%s", DOMAIN, area_id)
        # The addon will receive this as a call_service event and handle it
    
    async def handle_homeglo_off(call: ServiceCall) -> None:
        """Handle the homeglo_off service call.
        
        The addon listens for these service calls via WebSocket events,
        so we don't need to make any API calls here.
        """
        area_id = call.data.get(ATTR_AREA_ID)
        
        _LOGGER.info("[%s] homeglo_off called: area_id=%s", DOMAIN, area_id)
        # The addon will receive this as a call_service event and handle it
    
    # Schema for services - area_id can be a string or list of strings
    area_schema = vol.Schema({
        vol.Required(ATTR_AREA_ID): vol.Any(cv.string, [cv.string]),
    })
    
    # Register services
    hass.services.async_register(
        DOMAIN, SERVICE_STEP_UP, handle_step_up, schema=area_schema
    )
    _LOGGER.debug("[%s] Registered service: %s.%s", DOMAIN, DOMAIN, SERVICE_STEP_UP)
    hass.services.async_register(
        DOMAIN, SERVICE_STEP_DOWN, handle_step_down, schema=area_schema
    )
    _LOGGER.debug("[%s] Registered service: %s.%s", DOMAIN, DOMAIN, SERVICE_STEP_DOWN)
    hass.services.async_register(
        DOMAIN, SERVICE_RESET, handle_reset, schema=area_schema
    )
    _LOGGER.debug("[%s] Registered service: %s.%s", DOMAIN, DOMAIN, SERVICE_RESET)
    hass.services.async_register(
        DOMAIN, SERVICE_HOMEGLO_ON, handle_homeglo_on, schema=area_schema
    )
    _LOGGER.debug("[%s] Registered service: %s.%s", DOMAIN, DOMAIN, SERVICE_HOMEGLO_ON)
    hass.services.async_register(
        DOMAIN, SERVICE_HOMEGLO_OFF, handle_homeglo_off, schema=area_schema
    )
    _LOGGER.debug("[%s] Registered service: %s.%s", DOMAIN, DOMAIN, SERVICE_HOMEGLO_OFF)

    _LOGGER.info("[%s] Services registered successfully", DOMAIN)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("[%s] async_unload_entry: id=%s title=%s", DOMAIN, entry.entry_id, entry.title)

    # Remove config entry from domain
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("[%s] Removed entry. Remaining keys: %s", DOMAIN, list(hass.data[DOMAIN].keys()))

    # Check if this is the last config entry
    config_entries = [key for key in hass.data.get(DOMAIN, {}).keys() if key != "services_registered"]
    if not config_entries:
        _LOGGER.info("[%s] No config entries remain; unregistering services", DOMAIN)
        # Unregister services only if no config entries remain
        hass.services.async_remove(DOMAIN, SERVICE_STEP_UP)
        hass.services.async_remove(DOMAIN, SERVICE_STEP_DOWN)
        hass.services.async_remove(DOMAIN, SERVICE_RESET)
        hass.services.async_remove(DOMAIN, SERVICE_HOMEGLO_ON)
        hass.services.async_remove(DOMAIN, SERVICE_HOMEGLO_OFF)
        hass.data[DOMAIN].pop("services_registered", None)

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    _LOGGER.info("[%s] async_reload_entry: id=%s title=%s", DOMAIN, entry.entry_id, entry.title)
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
