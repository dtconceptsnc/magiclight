"""The MagicLight integration."""
from __future__ import annotations

import logging
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    SERVICE_STEP_UP,
    SERVICE_STEP_DOWN,
    SERVICE_DIM_UP,
    SERVICE_DIM_DOWN,
    SERVICE_RESET,
    SERVICE_MAGICLIGHT_ON,
    SERVICE_MAGICLIGHT_OFF,
    SERVICE_MAGICLIGHT_TOGGLE,
    ATTR_AREA_ID,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the MagicLight component."""
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

    # 🚀 Auto-create a config entry on startup if none exists.
    # This triggers your ConfigFlow.async_step_import which should immediately create the entry.
    if not hass.config_entries.async_entries(DOMAIN):
        _LOGGER.info("[%s] No config entries found; starting IMPORT flow to auto-create one.", DOMAIN)
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_IMPORT},
                data={},  # nothing to configure
            )
        )
    else:
        _LOGGER.debug("[%s] Config entry already exists; not starting IMPORT flow.", DOMAIN)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MagicLight from a config entry."""
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
    """Register MagicLight services."""
    _LOGGER.debug("[%s] _register_services invoked", DOMAIN)

    async def handle_step_up(call: ServiceCall) -> None:
        """Handle the step_up service call."""
        area_id = call.data.get(ATTR_AREA_ID)
        _LOGGER.info("[%s] step_up called: area_id=%s", DOMAIN, area_id)

    async def handle_step_down(call: ServiceCall) -> None:
        """Handle the step_down service call."""
        area_id = call.data.get(ATTR_AREA_ID)
        _LOGGER.info("[%s] step_down called: area_id=%s", DOMAIN, area_id)

    async def handle_dim_up(call: ServiceCall) -> None:
        """Handle the dim_up service call."""
        area_id = call.data.get(ATTR_AREA_ID)
        _LOGGER.info("[%s] dim_up called: area_id=%s", DOMAIN, area_id)

    async def handle_dim_down(call: ServiceCall) -> None:
        """Handle the dim_down service call."""
        area_id = call.data.get(ATTR_AREA_ID)
        _LOGGER.info("[%s] dim_down called: area_id=%s", DOMAIN, area_id)

    async def handle_reset(call: ServiceCall) -> None:
        """Handle the reset service call."""
        area_id = call.data.get(ATTR_AREA_ID)
        _LOGGER.info("[%s] reset called: area_id=%s", DOMAIN, area_id)

    async def handle_magiclight_on(call: ServiceCall) -> None:
        """Handle the magiclight_on service call."""
        area_id = call.data.get(ATTR_AREA_ID)
        _LOGGER.info("[%s] magiclight_on called: area_id=%s", DOMAIN, area_id)

    async def handle_magiclight_off(call: ServiceCall) -> None:
        """Handle the magiclight_off service call."""
        area_id = call.data.get(ATTR_AREA_ID)
        _LOGGER.info("[%s] magiclight_off called: area_id=%s", DOMAIN, area_id)

    async def handle_magiclight_toggle(call: ServiceCall) -> None:
        """Handle the magiclight_toggle service call."""
        area_id = call.data.get(ATTR_AREA_ID)
        _LOGGER.info("[%s] magiclight_toggle called: area_id=%s", DOMAIN, area_id)

    # Schema for services - area_id can be a string or list of strings
    area_schema = vol.Schema({
        vol.Required(ATTR_AREA_ID): vol.Any(cv.string, [cv.string]),
    })

    # Register services
    hass.services.async_register(DOMAIN, SERVICE_STEP_UP, handle_step_up, schema=area_schema)
    _LOGGER.debug("[%s] Registered service: %s.%s", DOMAIN, DOMAIN, SERVICE_STEP_UP)

    hass.services.async_register(DOMAIN, SERVICE_STEP_DOWN, handle_step_down, schema=area_schema)
    _LOGGER.debug("[%s] Registered service: %s.%s", DOMAIN, DOMAIN, SERVICE_STEP_DOWN)

    hass.services.async_register(DOMAIN, SERVICE_DIM_UP, handle_dim_up, schema=area_schema)
    _LOGGER.debug("[%s] Registered service: %s.%s", DOMAIN, DOMAIN, SERVICE_DIM_UP)

    hass.services.async_register(DOMAIN, SERVICE_DIM_DOWN, handle_dim_down, schema=area_schema)
    _LOGGER.debug("[%s] Registered service: %s.%s", DOMAIN, DOMAIN, SERVICE_DIM_DOWN)

    hass.services.async_register(DOMAIN, SERVICE_RESET, handle_reset, schema=area_schema)
    _LOGGER.debug("[%s] Registered service: %s.%s", DOMAIN, DOMAIN, SERVICE_RESET)

    hass.services.async_register(DOMAIN, SERVICE_MAGICLIGHT_ON, handle_magiclight_on, schema=area_schema)
    _LOGGER.debug("[%s] Registered service: %s.%s", DOMAIN, DOMAIN, SERVICE_MAGICLIGHT_ON)

    hass.services.async_register(DOMAIN, SERVICE_MAGICLIGHT_OFF, handle_magiclight_off, schema=area_schema)
    _LOGGER.debug("[%s] Registered service: %s.%s", DOMAIN, DOMAIN, SERVICE_MAGICLIGHT_OFF)

    hass.services.async_register(DOMAIN, SERVICE_MAGICLIGHT_TOGGLE, handle_magiclight_toggle, schema=area_schema)
    _LOGGER.debug("[%s] Registered service: %s.%s", DOMAIN, DOMAIN, SERVICE_MAGICLIGHT_TOGGLE)

    _LOGGER.info("[%s] Services registered successfully", DOMAIN)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("[%s] async_unload_entry: id=%s title=%s", DOMAIN, entry.entry_id, entry.title)

    # Remove config entry from domain
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("[%s] Removed entry. Remaining keys: %s", DOMAIN, list(hass.data[DOMAIN].keys()))

    # Check if this is the last config entry
    config_entries_left = [key for key in hass.data.get(DOMAIN, {}).keys() if key != "services_registered"]
    if not config_entries_left:
        _LOGGER.info("[%s] No config entries remain; unregistering services", DOMAIN)
        # Unregister services only if no config entries remain
        hass.services.async_remove(DOMAIN, SERVICE_STEP_UP)
        hass.services.async_remove(DOMAIN, SERVICE_STEP_DOWN)
        hass.services.async_remove(DOMAIN, SERVICE_DIM_UP)
        hass.services.async_remove(DOMAIN, SERVICE_DIM_DOWN)
        hass.services.async_remove(DOMAIN, SERVICE_RESET)
        hass.services.async_remove(DOMAIN, SERVICE_MAGICLIGHT_ON)
        hass.services.async_remove(DOMAIN, SERVICE_MAGICLIGHT_OFF)
        hass.services.async_remove(DOMAIN, SERVICE_MAGICLIGHT_TOGGLE)
        hass.data[DOMAIN].pop("services_registered", None)

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    _LOGGER.info("[%s] async_reload_entry: id=%s title=%s", DOMAIN, entry.entry_id, entry.title)
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)