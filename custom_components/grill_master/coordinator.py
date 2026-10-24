"""Data update coordinator for Grill Master integration.

Polls the grill at a configurable interval, decodes MCU payloads,
and optionally syncs data to a cloud PHP endpoint.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GrillConnectionError, GrillMasterApi
from .const import DEFAULT_POLL_INTERVAL, DOMAIN
from .decoder import decode_status, decode_temperatures

_LOGGER = logging.getLogger(__name__)


class GrillMasterCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls grill state and decodes MCU payloads."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: GrillMasterApi,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
        cloud_enabled: bool = False,
        cloud_url: str = "",
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance.
            api: Grill Master API client.
            poll_interval: Seconds between polls.
            cloud_enabled: Whether to sync data to a cloud endpoint.
            cloud_url: URL to POST temperature data to.
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self.api = api
        self._cloud_enabled = cloud_enabled
        self._cloud_url = cloud_url
        self._cloud_session: aiohttp.ClientSession | None = None
        self._device_info: dict[str, Any] | None = None

    @property
    def device_info_data(self) -> dict[str, Any] | None:
        """Return cached device info from Sys.GetInfo."""
        return self._device_info

    async def async_fetch_device_info(self) -> dict[str, Any]:
        """Fetch and cache device info from Sys.GetInfo.

        Called once during setup to get device ID, firmware version, etc.
        """
        try:
            self._device_info = await self.api.get_info()
            return self._device_info
        except GrillConnectionError as err:
            _LOGGER.error("Failed to fetch device info: %s", err)
            return {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll the grill and return decoded state.

        Returns:
            Merged dictionary of status and temperature data.

        Raises:
            UpdateFailed: If the grill cannot be reached.
        """
        try:
            raw_state = await self.api.get_state()
        except GrillConnectionError as err:
            raise UpdateFailed(f"Cannot reach grill: {err}") from err

        # Decode both payloads
        state: dict[str, Any] = {}

        sc_11 = raw_state.get("sc_11", "")
        sc_12 = raw_state.get("sc_12", "")

        status = decode_status(sc_11)
        if status:
            state.update(status)

        temperatures = decode_temperatures(sc_12)
        if temperatures:
            state.update(temperatures)

        if not state:
            # The grill firmware clears sc_11/sc_12 the instant any MCU command
            # is sent (turn on/off, set temp, light), and only refills them on
            # the next UART poll cycle a couple seconds later. A poll landing
            # in that gap is a transient empty read, not a real failure — keep
            # the last known state instead of flapping to unavailable.
            if self.data:
                _LOGGER.debug(
                    "Grill state empty (likely mid-command cache clear); "
                    "keeping last known state. sc_11=%r, sc_12=%r",
                    sc_11,
                    sc_12,
                )
                return self.data
            raise UpdateFailed(
                f"Failed to decode grill state. sc_11={sc_11!r}, sc_12={sc_12!r}"
            )

        # Add raw payloads for debugging
        state["_raw_sc_11"] = sc_11
        state["_raw_sc_12"] = sc_12

        # Cloud sync (fire-and-forget, never blocks polling)
        if self._cloud_enabled and self._cloud_url:
            self.hass.async_create_task(self._sync_to_cloud(state))

        return state

    async def _sync_to_cloud(self, state: dict[str, Any]) -> None:
        """POST temperature data to the configured cloud URL.

        This is fire-and-forget. Cloud sync failure must never break
        local monitoring. All errors are logged and swallowed.

        Args:
            state: Decoded grill state dictionary.
        """
        try:
            # Build a clean payload (exclude internal keys)
            payload = {
                k: v for k, v in state.items() if not k.startswith("_")
            }
            payload["timestamp"] = datetime.now(timezone.utc).isoformat()
            payload["host"] = self.api.host

            if self._cloud_session is None or self._cloud_session.closed:
                self._cloud_session = aiohttp.ClientSession()

            async with self._cloud_session.post(
                self._cloud_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status >= 400:
                    _LOGGER.warning(
                        "Cloud sync returned HTTP %s: %s",
                        resp.status,
                        await resp.text(),
                    )
        except Exception:
            _LOGGER.debug("Cloud sync failed (non-critical)", exc_info=True)

    async def async_shutdown(self) -> None:
        """Clean up resources."""
        if self._cloud_session and not self._cloud_session.closed:
            await self._cloud_session.close()
