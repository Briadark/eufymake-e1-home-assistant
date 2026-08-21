"""Select platform for eufyMake E1."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_SN, DOMAIN
from .coordinator import EufyMakeE1Coordinator, PURIFIER_DELAY_VALUES
from .coordinator import PURIFIER_MODE_VALUES
from .device_info import p1_device_info

PURIFIER_DELAY_OPTIONS = {
    "Immediately": 0,
    "1 minute": 60,
    "3 minutes": 180,
    "5 minutes": 300,
    "10 minutes": 600,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up eufyMake select entities."""
    coordinator: EufyMakeE1Coordinator = hass.data[DOMAIN][entry.entry_id]
    if not _purifier(coordinator.data or {}):
        return
    async_add_entities(
        [
            EufyMakeP1ModeSelect(coordinator, entry),
            EufyMakeP1DelaySelect(coordinator, entry),
        ]
    )


class EufyMakeP1ModeSelect(
    CoordinatorEntity[EufyMakeE1Coordinator],
    SelectEntity,
):
    """Mode selector for a linked eufyMake Purifier P1."""

    _attr_has_entity_name = True
    _attr_name = "Purifier mode"
    _attr_options = list(PURIFIER_MODE_VALUES)

    def __init__(self, coordinator: EufyMakeE1Coordinator, entry: ConfigEntry) -> None:
        """Initialize the P1 mode selector."""
        super().__init__(coordinator)
        e1_sn = entry.data[CONF_DEVICE_SN]
        purifier = _purifier(coordinator.data or {})
        purifier_sn = _purifier_sn(coordinator, e1_sn)
        self._attr_unique_id = f"{purifier_sn}_mode"
        self._attr_device_info = p1_device_info(purifier, fallback_e1_sn=e1_sn)

    @property
    def current_option(self) -> str | None:
        """Return the current P1 mode."""
        mode = _purifier_state(self.coordinator.data or {}).get("work_mode")
        for name, value in PURIFIER_MODE_VALUES.items():
            if _optional_int(mode) == value:
                return name
        return None

    async def async_select_option(self, option: str) -> None:
        """Set the P1 mode."""
        await self.coordinator.async_set_purifier_mode(option)


class EufyMakeP1DelaySelect(
    CoordinatorEntity[EufyMakeE1Coordinator],
    SelectEntity,
):
    """Delay-off selector for a linked eufyMake Purifier P1."""

    _attr_has_entity_name = True
    _attr_name = "Purifier delay off"
    _attr_options = list(PURIFIER_DELAY_OPTIONS)

    def __init__(self, coordinator: EufyMakeE1Coordinator, entry: ConfigEntry) -> None:
        """Initialize the P1 delay selector."""
        super().__init__(coordinator)
        e1_sn = entry.data[CONF_DEVICE_SN]
        purifier = _purifier(coordinator.data or {})
        purifier_sn = _purifier_sn(coordinator, e1_sn)
        self._attr_unique_id = f"{purifier_sn}_delay_off"
        self._attr_device_info = p1_device_info(purifier, fallback_e1_sn=e1_sn)

    @property
    def current_option(self) -> str | None:
        """Return the current P1 delay-off option."""
        delay = _optional_int(_purifier_state(self.coordinator.data or {}).get("delay"))
        if delay not in PURIFIER_DELAY_VALUES:
            return None
        for name, value in PURIFIER_DELAY_OPTIONS.items():
            if delay == value:
                return name
        return None

    async def async_select_option(self, option: str) -> None:
        """Set the P1 Auto delay-off seconds."""
        await self.coordinator.async_set_purifier_delay(PURIFIER_DELAY_OPTIONS[option])


def _purifier(data: dict[str, Any]) -> dict[str, Any]:
    purifier = data.get("purifier", {})
    return purifier if isinstance(purifier, dict) else {}


def _purifier_state(data: dict[str, Any]) -> dict[str, Any]:
    state = _purifier(data).get("state", {})
    return state if isinstance(state, dict) else {}


def _purifier_sn(coordinator: EufyMakeE1Coordinator, fallback_e1_sn: str) -> str:
    purifier = _purifier(coordinator.data or {})
    return str(purifier.get("serial_number") or f"{fallback_e1_sn}_purifier_p1")


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
