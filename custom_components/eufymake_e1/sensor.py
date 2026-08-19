"""Sensor platform for eufyMake E1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_SN, DOMAIN
from .coordinator import EufyMakeE1Coordinator


@dataclass(frozen=True, kw_only=True)
class EufyMakeSensorDescription(SensorEntityDescription):
    """Describe a eufyMake E1 sensor."""

    value_fn: Callable[[dict[str, Any]], Any]
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


SENSORS: tuple[EufyMakeSensorDescription, ...] = (
    EufyMakeSensorDescription(
        key="availability",
        name="Availability",
        translation_key="availability",
        value_fn=lambda data: data.get("availability"),
    ),
    EufyMakeSensorDescription(
        key="print_status",
        name="Print status",
        translation_key="print_status",
        value_fn=lambda data: data.get("print_status"),
    ),
    EufyMakeSensorDescription(
        key="firmware_version",
        name="Firmware version",
        translation_key="firmware_version",
        value_fn=lambda data: data.get("firmware_version"),
    ),
    EufyMakeSensorDescription(
        key="waste_ink",
        name="Waste ink",
        translation_key="waste_ink",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: data.get("waste_ink"),
        attributes_fn=lambda data: _waste_ink_attributes(data),
    ),
    EufyMakeSensorDescription(
        key="ink_c",
        name="Cyan ink",
        translation_key="ink_c",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: _ink_value(data, "C"),
        attributes_fn=lambda data: _ink_attributes(data, "C"),
    ),
    EufyMakeSensorDescription(
        key="ink_m",
        name="Magenta ink",
        translation_key="ink_m",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: _ink_value(data, "M"),
        attributes_fn=lambda data: _ink_attributes(data, "M"),
    ),
    EufyMakeSensorDescription(
        key="ink_y",
        name="Yellow ink",
        translation_key="ink_y",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: _ink_value(data, "Y"),
        attributes_fn=lambda data: _ink_attributes(data, "Y"),
    ),
    EufyMakeSensorDescription(
        key="ink_k",
        name="Black ink",
        translation_key="ink_k",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: _ink_value(data, "K"),
        attributes_fn=lambda data: _ink_attributes(data, "K"),
    ),
    EufyMakeSensorDescription(
        key="ink_w",
        name="White ink",
        translation_key="ink_w",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: _ink_value(data, "W"),
        attributes_fn=lambda data: _ink_attributes(data, "W"),
    ),
    EufyMakeSensorDescription(
        key="ink_g",
        name="Gloss ink",
        translation_key="ink_g",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: _ink_value(data, "G"),
        attributes_fn=lambda data: _ink_attributes(data, "G"),
    ),
    EufyMakeSensorDescription(
        key="mqtt_online",
        name="MQTT online",
        translation_key="mqtt_online",
        value_fn=lambda data: data.get("mqtt_online"),
    ),
    EufyMakeSensorDescription(
        key="p2p_online",
        name="P2P online",
        translation_key="p2p_online",
        value_fn=lambda data: data.get("p2p_online"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up eufyMake E1 sensors."""
    coordinator: EufyMakeE1Coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        EufyMakeE1Sensor(coordinator, entry, description) for description in SENSORS
    ]
    entities.extend(
        EufyMakeE1PartSensor(coordinator, entry, part)
        for part in _parts(coordinator)
    )
    async_add_entities(entities)


class EufyMakeE1Sensor(CoordinatorEntity[EufyMakeE1Coordinator], SensorEntity):
    """Representation of a eufyMake E1 sensor."""

    entity_description: EufyMakeSensorDescription

    def __init__(
        self,
        coordinator: EufyMakeE1Coordinator,
        entry: ConfigEntry,
        description: EufyMakeSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        device_sn = entry.data[CONF_DEVICE_SN]
        self.entity_description = description
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{device_sn}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_sn)},
            "manufacturer": "eufyMake",
            "model": "E1",
            "name": "eufyMake E1",
        }

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return sensor attributes."""
        if self.entity_description.attributes_fn is None:
            return {}
        return _clean_attributes(
            self.entity_description.attributes_fn(self.coordinator.data or {})
        )


class EufyMakeE1PartSensor(CoordinatorEntity[EufyMakeE1Coordinator], SensorEntity):
    """Representation of a eufyMake E1 consumable or service part."""

    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(
        self,
        coordinator: EufyMakeE1Coordinator,
        entry: ConfigEntry,
        part: dict[str, Any],
    ) -> None:
        """Initialize the part sensor."""
        super().__init__(coordinator)
        device_sn = entry.data[CONF_DEVICE_SN]
        key = part.get("key") or _slug(str(part.get("name") or "part"))
        name = part.get("name") or key
        self._part_key = key
        self._attr_has_entity_name = True
        self._attr_name = name
        self._attr_unique_id = f"{device_sn}_part_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_sn)},
            "manufacturer": "eufyMake",
            "model": "E1",
            "name": "eufyMake E1",
        }

    @property
    def native_value(self) -> Any:
        """Return the part remaining percentage."""
        for part in _parts(self.coordinator):
            if part.get("key") == self._part_key:
                return part.get("remaining_percent")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional part attributes."""
        for part in _parts(self.coordinator):
            if part.get("key") == self._part_key:
                return {
                    "remaining_work_life": part.get("remaining_work_life"),
                    "maintenance_required": part.get("maintenance_required"),
                    "support_reset": part.get("support_reset"),
                }
        return {}


def _parts(coordinator: EufyMakeE1Coordinator) -> list[dict[str, Any]]:
    """Return coordinator part data."""
    data = coordinator.data or {}
    parts = data.get("parts", [])
    return parts if isinstance(parts, list) else []


def _ink_value(data: dict[str, Any], channel: str) -> Any:
    ink = data.get("ink", {})
    if not isinstance(ink, dict):
        return None
    return ink.get(channel)


def _ink_attributes(data: dict[str, Any], channel: str) -> dict[str, Any]:
    details = data.get("ink_details", {})
    if not isinstance(details, dict):
        return {}
    attributes = details.get(channel, {})
    return attributes if isinstance(attributes, dict) else {}


def _waste_ink_attributes(data: dict[str, Any]) -> dict[str, Any]:
    attributes = data.get("waste_ink_details", {})
    return attributes if isinstance(attributes, dict) else {}


def _clean_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in attributes.items()
        if value is not None
    }


def _slug(value: str) -> str:
    """Return a simple entity-safe slug."""
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")
