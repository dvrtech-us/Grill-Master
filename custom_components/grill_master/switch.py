"""Switch platform for Grill Master.

Exposes the grill light as a controllable switch entity.
Not all models have a physical light (e.g., LG1000BL does not).
The switch will show a friendly error if the command fails.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import GrillCommandError, GrillConnectionError, GrillMasterApi
from .const import CONF_DEVICE_ID, DOMAIN
from .coordinator import GrillMasterCoordinator

_LOGGER = logging.getLogger(__name__)

# Device ID prefixes for models known to have a physical light (Founders series)
_LIGHT_SUPPORTED_PREFIXES = ("LFS-",)

_LIGHT_NOT_SUPPORTED_MSG = (
    "This grill model may not have a light. "
    "The LG1000BL, LG0800BL, LG1200BL, and most Pit Boss models "
    "do not have an internal light. "
    "Models with a light include the LG800FL and LG1200FL (Founders series)."
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Grill Master switch entities."""
    coordinator: GrillMasterCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        GrillMasterLightSwitch(coordinator, entry),
    ])


class GrillMasterLightSwitch(
    CoordinatorEntity[GrillMasterCoordinator], SwitchEntity
):
    """Switch entity for the grill light.

    Not all grill models have a physical light. If the command fails or the
    light_state never changes after toggling, the grill likely doesn't have one.
    """

    _attr_has_entity_name = True
    _attr_name = "Light"
    _attr_icon = "mdi:lightbulb"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(
        self,
        coordinator: GrillMasterCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the light switch."""
        super().__init__(coordinator)
        self._api: GrillMasterApi = coordinator.api
        self._attr_unique_id = f"{entry.entry_id}_light_switch"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=coordinator.api.profile.manufacturer,
            model=coordinator.api.profile.model,
        )
        self._light_failed = False

        # Disable by default for models that don't have a physical light.
        # Users can enable it manually in the entity registry if needed.
        device_id = entry.data.get(CONF_DEVICE_ID, "")
        self._attr_entity_registry_enabled_default = device_id.startswith(
            _LIGHT_SUPPORTED_PREFIXES
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if the light is on."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("light_state", False)

    async def _toggle_light(self, on: bool) -> None:
        """Toggle the light with error handling for unsupported models."""
        action = "on" if on else "off"
        try:
            await self._api.set_light(on)
            await self.coordinator.async_request_refresh()

            # Check if the light_state actually changed after refresh.
            # If it didn't, the grill probably doesn't have a light.
            actual_state = self.coordinator.data.get("light_state", False)
            if actual_state != on and not self._light_failed:
                self._light_failed = True
                _LOGGER.warning(
                    "Light command sent but state did not change. %s",
                    _LIGHT_NOT_SUPPORTED_MSG,
                )
                raise HomeAssistantError(
                    f"Light did not turn {action}. {_LIGHT_NOT_SUPPORTED_MSG}"
                )

        except (GrillConnectionError, GrillCommandError) as err:
            _LOGGER.warning(
                "Failed to turn light %s: %s. %s",
                action,
                err,
                _LIGHT_NOT_SUPPORTED_MSG,
            )
            raise HomeAssistantError(
                f"Failed to turn light {action}. {_LIGHT_NOT_SUPPORTED_MSG}"
            ) from err

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        _LOGGER.debug("Turning grill light on")
        await self._toggle_light(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        _LOGGER.debug("Turning grill light off")
        await self._toggle_light(False)
