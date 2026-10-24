"""Temperature sensor platform for Grill Master.

Exposes grill temperature, set point, and meat probe temperatures as
Home Assistant sensor entities with device_class=temperature for
automatic unit conversion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GrillMasterCoordinator


@dataclass(frozen=True, kw_only=True)
class GrillMasterSensorDescription(SensorEntityDescription):
    """Describes a Grill Master sensor entity."""

    data_key: str


SENSOR_DESCRIPTIONS: tuple[GrillMasterSensorDescription, ...] = (
    GrillMasterSensorDescription(
        key="grill_temp",
        translation_key="grill_temperature",
        name="Grill Temperature",
        data_key="grill_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        icon="mdi:thermometer",
    ),
    GrillMasterSensorDescription(
        key="grill_set_temp",
        translation_key="grill_set_point",
        name="Grill Set Point",
        data_key="grill_set_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        icon="mdi:thermometer-check",
    ),
    GrillMasterSensorDescription(
        key="p1_temp",
        translation_key="probe_1_temperature",
        name="Probe 1 Temperature",
        data_key="p1_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        icon="mdi:thermometer-probe",
    ),
    GrillMasterSensorDescription(
        key="p1_target",
        translation_key="probe_1_target",
        name="Probe 1 Target",
        data_key="p1_target",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        icon="mdi:thermometer-probe-off",
    ),
    GrillMasterSensorDescription(
        key="p2_temp",
        translation_key="probe_2_temperature",
        name="Probe 2 Temperature",
        data_key="p2_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        icon="mdi:thermometer-probe",
    ),
    GrillMasterSensorDescription(
        key="p3_temp",
        name="Probe 3 Temperature",
        data_key="p3_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        icon="mdi:thermometer-probe",
    ),
    GrillMasterSensorDescription(
        key="p4_temp",
        name="Probe 4 Temperature",
        data_key="p4_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        icon="mdi:thermometer-probe",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Grill Master sensor entities."""
    coordinator: GrillMasterCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        GrillMasterSensor(coordinator, description, entry)
        for description in SENSOR_DESCRIPTIONS
    )


class GrillMasterSensor(
    CoordinatorEntity[GrillMasterCoordinator], SensorEntity
):
    """Sensor entity for Grill Master temperature readings."""

    entity_description: GrillMasterSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GrillMasterCoordinator,
        description: GrillMasterSensorDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(coordinator, entry)

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self.entity_description.data_key)
        if value is None or value == 0:
            return None
        return value


def _device_info(
    coordinator: GrillMasterCoordinator, entry: ConfigEntry
) -> DeviceInfo:
    """Build device info for the device registry."""
    info = coordinator.device_info_data or {}
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer=coordinator.api.profile.manufacturer,
        model=coordinator.api.profile.model,
        sw_version=info.get("fw_version", ""),
        configuration_url=f"http://{coordinator.api.host}",
    )
