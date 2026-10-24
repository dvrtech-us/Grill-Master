"""Config flow for Grill Master integration.

Supports two discovery paths:
1. Manual setup: User enters grill IP address
2. DHCP discovery: HA detects the grill's MAC on the network and auto-fills IP

Both paths validate against the live device, store the MAC address,
and support automatic IP updates when DHCP assigns a new address.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

try:
    # HA 2024.6+
    from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
except ImportError:
    # HA < 2024.6
    from homeassistant.components.dhcp import DhcpServiceInfo

from .api import GrillConnectionError, GrillMasterApi
from .const import (
    CONF_CLOUD_ENABLED,
    CONF_CLOUD_URL,
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_MAC,
    CONF_POLL_INTERVAL,
    DEFAULT_CLOUD_URL,
    DEFAULT_NAME,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional("name", default=DEFAULT_NAME): str,
        vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): vol.All(
            int, vol.Range(min=2, max=60)
        ),
    }
)

STEP_CLOUD_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CLOUD_ENABLED, default=False): bool,
        vol.Optional(CONF_CLOUD_URL, default=DEFAULT_CLOUD_URL): str,
    }
)


def _format_mac(raw_mac: str) -> str:
    """Normalize a MAC address to lowercase colon-separated format.

    Handles:
      "943CC6AABBCC"       -> "94:3c:c6:aa:bb:cc"
      "94:3C:C6:AA:BB:CC" -> "94:3c:c6:aa:bb:cc"
    """
    mac = raw_mac.replace(":", "").replace("-", "").lower()
    return ":".join(mac[i : i + 2] for i in range(0, 12, 2))


class GrillMasterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Grill Master."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._host: str = ""
        self._name: str = DEFAULT_NAME
        self._poll_interval: int = DEFAULT_POLL_INTERVAL
        self._firmware_version: str = "unknown"
        self._device_id: str = ""
        self._mac: str = ""

    async def _validate_grill(self, host: str) -> dict[str, Any]:
        """Validate connection to a grill and return device info.

        Args:
            host: IP address of the grill.

        Returns:
            Device info dict from Sys.GetInfo.

        Raises:
            GrillConnectionError: If the grill cannot be reached.
        """
        session = async_get_clientsession(self.hass)
        api = GrillMasterApi(session, host)

        if not await api.ping():
            raise GrillConnectionError("Grill did not respond to ping")

        info = await api.get_info()
        self._device_id = str(info.get("id") or "")
        self._mac = _format_mac(info.get("mac", ""))

        if self._device_id.upper().startswith("NXP-"):
            self._firmware_version = info.get("fw_version", "unknown")
        else:
            self._firmware_version = await api.get_firmware_version()

        return info

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Handle DHCP discovery.

        HA detected a device with an Espressif MAC (94:3C:C6:*) on the network.
        We need to verify it's actually a supported grill by calling Sys.GetInfo.
        If it matches an existing entry, update the IP address.
        """
        host = discovery_info.ip
        mac = _format_mac(discovery_info.macaddress)

        _LOGGER.debug(
            "DHCP discovery: host=%s, mac=%s, hostname=%s",
            host,
            mac,
            discovery_info.hostname,
        )

        # Check if we already have an entry for this MAC
        for entry in self._async_current_entries():
            entry_mac = entry.data.get(CONF_MAC, "")
            if _format_mac(entry_mac) == mac:
                # Same grill, check if IP changed
                if entry.data.get(CONF_HOST) != host:
                    _LOGGER.info(
                        "Grill %s IP changed from %s to %s (DHCP)",
                        entry.data.get(CONF_DEVICE_ID, mac),
                        entry.data.get(CONF_HOST),
                        host,
                    )
                    # Update the config entry with the new IP
                    new_data = {**entry.data, CONF_HOST: host}
                    self.hass.config_entries.async_update_entry(entry, data=new_data)
                # Already configured, abort
                return self.async_abort(reason="already_configured")

        # Not yet configured — verify it's a supported grill
        try:
            await self._validate_grill(host)
        except GrillConnectionError:
            return self.async_abort(reason="cannot_connect")

        # Only proceed if Sys.GetInfo returned a PB device ID (starts with "LBL-" etc.)
        if not self._device_id or not self._device_id.upper().startswith(
            ("LBL-", "LPB-", "PB", "NXP-")
        ):
            # Not a supported grill — just a random Espressif device
            return self.async_abort(reason="not_supported_grill")

        # Set unique ID and check for duplicates
        await self.async_set_unique_id(self._device_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self._host = host
        self._name = f"Grill Master ({self._device_id})"

        # Show confirmation before adding
        return await self.async_step_cloud()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: grill IP and basic config."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            self._name = user_input.get("name", DEFAULT_NAME)
            self._poll_interval = user_input.get(
                CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
            )

            try:
                await self._validate_grill(host)

                if self._device_id:
                    await self.async_set_unique_id(self._device_id)
                    self._abort_if_unique_id_configured()

                self._host = host
                return await self.async_step_cloud()

            except GrillConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during setup")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the cloud sync configuration step."""
        if user_input is not None:
            data = {
                CONF_HOST: self._host,
                CONF_MAC: self._mac,
                CONF_DEVICE_ID: self._device_id,
                CONF_POLL_INTERVAL: self._poll_interval,
                CONF_CLOUD_ENABLED: user_input.get(CONF_CLOUD_ENABLED, False),
                CONF_CLOUD_URL: user_input.get(CONF_CLOUD_URL, ""),
            }

            return self.async_create_entry(
                title=self._name,
                data=data,
            )

        return self.async_show_form(
            step_id="cloud",
            data_schema=STEP_CLOUD_DATA_SCHEMA,
        )
