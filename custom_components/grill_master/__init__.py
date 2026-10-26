"""Grill Master integration for Home Assistant.

Monitors and controls pellet grills over local HTTP JSON-RPC.
Supports Control Board 8 and NXP Mongoose OS board profiles.

Handles automatic IP updates via DHCP discovery when the grill's
IP address changes on the network.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GrillMasterApi
from .board_profiles import profile_for_device_id, resolve_poll_interval
from .const import (
    CONF_CLOUD_ENABLED,
    CONF_CLOUD_URL,
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_POLL_INTERVAL,
    DOMAIN,
)
from .coordinator import GrillMasterCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Grill Master from a config entry."""
    host = entry.data[CONF_HOST]
    cloud_enabled = entry.data.get(CONF_CLOUD_ENABLED, False)
    cloud_url = entry.data.get(CONF_CLOUD_URL, "")

    session = async_get_clientsession(hass)
    profile = profile_for_device_id(entry.data.get(CONF_DEVICE_ID, ""))
    poll_interval = resolve_poll_interval(
        profile, entry.data.get(CONF_POLL_INTERVAL)
    )
    api = GrillMasterApi(session, host, profile=profile)

    coordinator = GrillMasterCoordinator(
        hass,
        api,
        poll_interval=poll_interval,
        cloud_enabled=cloud_enabled,
        cloud_url=cloud_url,
    )

    # Fetch device info (for device registry) and do first data refresh
    await coordinator.async_fetch_device_info()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Listen for config entry updates (e.g., DHCP detected a new IP)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry updates (e.g., IP address changed via DHCP).

    When the DHCP discovery handler detects the grill at a new IP,
    it updates the config entry data. This listener picks up that
    change and swaps the API client to the new address so polling
    continues without requiring an HA restart.
    """
    coordinator: GrillMasterCoordinator = hass.data[DOMAIN][entry.entry_id]
    new_host = entry.data[CONF_HOST]

    if coordinator.api.host != new_host:
        _LOGGER.info(
            "Grill IP updated from %s to %s, switching API client",
            coordinator.api.host,
            new_host,
        )
        session = async_get_clientsession(hass)
        profile = profile_for_device_id(entry.data.get(CONF_DEVICE_ID, ""))
        coordinator.api = GrillMasterApi(session, new_host, profile=profile)
        # Trigger an immediate refresh with the new IP
        await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: GrillMasterCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok
