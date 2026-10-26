"""Binary sensor platform for Grill Master.

Exposes grill status flags (power, errors, fan, light, motor, pellets)
as Home Assistant binary sensor entities.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GrillMasterCoordinator


@dataclass(frozen=True, kw_only=True)
class GrillMasterBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a Grill Master binary sensor entity."""

    data_key: str


BINARY_SENSOR_DESCRIPTIONS: tuple[GrillMasterBinarySensorDescription, ...] = (
    # Power / Running state
    GrillMasterBinarySensorDescription(
        key="module_is_on",
        name="Grill Power",
        data_key="module_is_on",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:grill",
    ),
    # Component states
    GrillMasterBinarySensorDescription(
        key="fan_state",
        name="Fan",
        data_key="fan_state",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:fan",
    ),
    GrillMasterBinarySensorDescription(
        key="light_state",
        name="Light",
        data_key="light_state",
        device_class=BinarySensorDeviceClass.LIGHT,
        icon="mdi:lightbulb",
    ),
    GrillMasterBinarySensorDescription(
        key="motor_state",
        name="Auger Motor",
        data_key="motor_state",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:cog",
    ),
    GrillMasterBinarySensorDescription(
        key="hot_state",
        name="Heater",
        data_key="hot_state",
        device_class=BinarySensorDeviceClass.HEAT,
        icon="mdi:fire",
    ),
    GrillMasterBinarySensorDescription(
        key="prime_state",
        name="Primer",
        data_key="prime_state",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:water-pump",
    ),
    # Error / Problem states
    GrillMasterBinarySensorDescription(
        key="no_pellets",
        name="No Pellets",
        data_key="no_pellets",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:alert-circle",
    ),
    GrillMasterBinarySensorDescription(
        key="high_temp_err",
        name="High Temperature Error",
        data_key="high_temp_err",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:thermometer-alert",
    ),
    GrillMasterBinarySensorDescription(
        key="fan_err",
        name="Fan Error",
        data_key="fan_err",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:fan-alert",
    ),
    GrillMasterBinarySensorDescription(
        key="hot_err",
        name="Igniter Error",
        data_key="hot_err",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:fire-alert",
    ),
    GrillMasterBinarySensorDescription(
        key="motor_err",
        name="Motor Error",
        data_key="motor_err",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:cog-off",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Grill Master binary sensor entities."""
    coordinator: GrillMasterCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        GrillMasterBinarySensor(coordinator, description, entry)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class GrillMasterBinarySensor(
    CoordinatorEntity[GrillMasterCoordinator], BinarySensorEntity
):
    """Binary sensor entity for Grill Master status flags."""

    entity_description: GrillMasterBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GrillMasterCoordinator,
        description: GrillMasterBinarySensorDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=coordinator.api.profile.manufacturer,
            model=coordinator.api.profile.model,
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if the binary sensor is on."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.data_key)
