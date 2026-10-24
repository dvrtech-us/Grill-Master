"""HTTP JSON-RPC client for Grill Master Mongoose OS controller.

Communicates with the ESP32 controller via HTTP at http://<ip>/rpc/<method>.
No authentication required on firmware 0.2.3.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import (
    CMD_LIGHT_OFF,
    CMD_LIGHT_ON,
    CMD_POWER_OFF,
    DEFAULT_TIMEOUT,
)
from .board_profiles import (
    CONTROL_BOARD_8,
    BoardProfile,
    build_nexgrill_command,
)
from .decoder import encode_set_temperature

_LOGGER = logging.getLogger(__name__)


class GrillConnectionError(Exception):
    """Raised when the grill cannot be reached."""


class GrillCommandError(Exception):
    """Raised when a command fails."""


class GrillMasterApi:
    """HTTP JSON-RPC client for Grill Master ESP32 controller."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        timeout: int = DEFAULT_TIMEOUT,
        profile: BoardProfile = CONTROL_BOARD_8,
    ) -> None:
        """Initialize the API client.

        Args:
            session: aiohttp client session (from HA core).
            host: IP address or hostname of the grill.
            timeout: HTTP request timeout in seconds.
        """
        self._session = session
        self._host = host
        self.profile = profile
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._base_url = f"http://{host}/rpc"

    @property
    def host(self) -> str:
        """Return the grill host address."""
        return self._host

    async def _rpc_get(self, method: str) -> dict[str, Any]:
        """Execute an RPC GET request.

        Args:
            method: RPC method name (e.g., "PB.GetState").

        Returns:
            Parsed JSON response.

        Raises:
            GrillConnectionError: If the grill is unreachable.
        """
        url = f"{self._base_url}/{method}"
        try:
            async with self._session.get(url, timeout=self._timeout) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except asyncio.TimeoutError as err:
            raise GrillConnectionError(
                f"Timeout connecting to grill at {self._host}"
            ) from err
        except aiohttp.ClientError as err:
            raise GrillConnectionError(
                f"Error connecting to grill at {self._host}: {err}"
            ) from err

    async def _rpc_post(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute an RPC POST request with parameters.

        Args:
            method: RPC method name.
            params: Request parameters.

        Returns:
            Parsed JSON response.

        Raises:
            GrillConnectionError: If the grill is unreachable.
            GrillCommandError: If the command fails.
        """
        url = f"{self._base_url}/{method}"
        try:
            async with self._session.post(
                url, json=params, timeout=self._timeout
            ) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except asyncio.TimeoutError as err:
            raise GrillConnectionError(
                f"Timeout sending command to grill at {self._host}"
            ) from err
        except aiohttp.ClientError as err:
            raise GrillConnectionError(
                f"Error sending command to grill at {self._host}: {err}"
            ) from err

    async def get_state(self) -> dict[str, Any]:
        """Get the current grill state."""
        if self.profile.decoded_state:
            return await self._rpc_post(self.profile.state_rpc, {"reply": "full"})
        return await self._rpc_get(self.profile.state_rpc)

    async def get_firmware_version(self) -> str:
        """Get the grill firmware version.

        Returns:
            Firmware version string, e.g., "0.2.3".
        """
        if self.profile.firmware_rpc is None:
            return "unknown"
        resp = await self._rpc_get(self.profile.firmware_rpc)
        return resp.get("firmwareVersion", "unknown")

    async def get_info(self) -> dict[str, Any]:
        """Get device info (ID, firmware, WiFi, memory stats).

        Uses a longer timeout because Sys.GetInfo returns a large JSON
        response and the ESP32 can be slow to serialize it.

        Returns:
            Sys.GetInfo response dict.
        """
        url = f"{self._base_url}/Sys.GetInfo"
        long_timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with self._session.get(url, timeout=long_timeout) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except asyncio.TimeoutError as err:
            raise GrillConnectionError(
                f"Timeout fetching device info from {self._host}"
            ) from err
        except aiohttp.ClientError as err:
            raise GrillConnectionError(
                f"Error fetching device info from {self._host}: {err}"
            ) from err

    async def send_command(self, command: str) -> dict[str, Any]:
        """Send a board-specific command to the grill.

        Args:
            command: Hex or decimal-byte command string.

        Returns:
            RPC response dict.
        """
        _LOGGER.debug("Sending grill command: %s", command)
        if self.profile.decoded_state:
            try:
                return await self._rpc_post(
                    self.profile.command_rpc, {"command": command}
                )
            except GrillConnectionError as err:
                if not self._is_http_500(err):
                    raise
                await asyncio.sleep(1)
                return await self._rpc_post(
                    self.profile.command_rpc, {"command": command}
                )
        return await self._rpc_post(self.profile.command_rpc, {"command": command})

    async def set_temperature(self, temp_f: int) -> dict[str, Any]:
        """Set the grill target temperature.

        Args:
            temp_f: Target temperature in Fahrenheit (180-600, increments of 5).

        Returns:
            RPC response dict.
        """
        if self.profile.decoded_state:
            command = build_nexgrill_command(
                0x05, (temp_f // 256, temp_f % 256)
            )
            return await self.send_command(command)
        command = encode_set_temperature(temp_f)
        return await self.send_command(command)

    async def turn_off(self) -> dict[str, Any]:
        """Turn the grill off."""
        if self.profile.decoded_state:
            return await self.send_command(build_nexgrill_command(0x02, (0,)))
        return await self.send_command(CMD_POWER_OFF)

    async def set_light(self, on: bool) -> dict[str, Any]:
        """Toggle the grill light.

        Args:
            on: True to turn on, False to turn off.
        """
        if self.profile.decoded_state:
            raise GrillCommandError("Light control is not supported by this board")
        command = CMD_LIGHT_ON if on else CMD_LIGHT_OFF
        return await self.send_command(command)

    async def set_mode(self, mode: int) -> dict[str, Any]:
        """Set the Nexgrill operating mode (standby, smoke, cook, or high)."""
        if not self.profile.decoded_state:
            raise GrillCommandError("Mode control is not supported by this board")
        if mode not in (0, 1, 2, 3):
            raise ValueError(
                "Mode must be 0 (standby), 1 (smoke), 2 (cook), or 3 (high)"
            )
        return await self.send_command(build_nexgrill_command(0x07, (mode,)))

    async def start(self, start: bool = True) -> dict[str, Any]:
        """Start or pause Nexgrill cooking after the controller is powered on."""
        if not self.profile.decoded_state:
            raise GrillCommandError("Start control is not supported by this board")
        return await self.send_command(build_nexgrill_command(0x33, (int(start),)))

    async def set_display_unit(self, celsius: bool) -> dict[str, Any]:
        """Change the Nexgrill display unit without changing wire temperatures."""
        if not self.profile.decoded_state:
            raise GrillCommandError("Display-unit control is not supported by this board")
        return await self.send_command(
            build_nexgrill_command(0x03, (int(celsius),))
        )

    async def set_timer(self, hours: int, minutes: int) -> dict[str, Any]:
        """Set or clear the Nexgrill cook timer."""
        if self.profile.timer_rpc is None:
            raise GrillCommandError("Timer control is not supported by this board")
        if hours < 0 or not 0 <= minutes <= 59:
            raise ValueError("Timer hours must be non-negative and minutes 0-59")
        return await self._rpc_post(
            self.profile.timer_rpc, {"hours": hours, "minutes": minutes}
        )

    @staticmethod
    def _is_http_500(err: GrillConnectionError) -> bool:
        """Return whether a connection error was caused by an HTTP 500."""
        cause = err.__cause__
        return isinstance(cause, aiohttp.ClientResponseError) and cause.status == 500

    async def ping(self) -> bool:
        """Check if the grill is reachable.

        Returns:
            True if the grill responds to RPC.Ping.
        """
        try:
            await self._rpc_get("RPC.Ping")
            return True
        except GrillConnectionError:
            return False
