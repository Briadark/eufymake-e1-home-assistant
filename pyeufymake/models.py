"""Data models for eufyMake devices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, kw_only=True)
class Device:
    """A cached eufyMake device."""

    serial_number: str
    secret_key: str | None
    station_model: str
    sku_number: str | None
    product_name: str | None
    product_region: str | None
    firmware_version: str | None
    hardware_version: str | None
    ip_address: str | None
    mqtt_online: bool | None
    p2p_online: bool | None
    can_query: bool
    can_command: bool
    has_camera: bool
    params: dict[int, str]

    @classmethod
    def from_cache(cls, data: dict[str, Any]) -> Device:
        """Create a device from eufyMake Studio cache JSON."""
        return cls(
            serial_number=str(data.get("station_sn", "")),
            secret_key=_optional_str(data.get("secret_key")),
            station_model=str(data.get("station_model", "")),
            sku_number=_optional_str(data.get("sku_number")),
            product_name=_optional_str(data.get("product_name")),
            product_region=_optional_str(data.get("product_region")),
            firmware_version=_optional_str(data.get("main_sw_version")),
            hardware_version=_optional_str(data.get("main_hw_version")),
            ip_address=_optional_str(data.get("ip_addr")),
            mqtt_online=_status_to_bool(data.get("mqtt_status")),
            p2p_online=_status_to_bool(data.get("p2p_status")),
            can_query=bool(data.get("is_query")),
            can_command=bool(data.get("is_command")),
            has_camera=bool(data.get("is_camera")),
            params=_extract_params(data.get("params")),
        )

    @property
    def is_online(self) -> bool | None:
        """Return combined known online state."""
        states = [
            item
            for item in (self.mqtt_online, self.p2p_online)
            if item is not None
        ]
        return any(states) if states else None

    @property
    def is_e1(self) -> bool:
        """Return whether this device is a eufyMake E1."""
        return self.station_model == "V8260"


@dataclass(frozen=True, kw_only=True)
class MakerPart:
    """A consumable or service part reported by eufyMake."""

    key: str | None
    name: str | None
    remaining_percent: int | None
    remaining_work_life: str | None
    maintenance_required: bool
    support_reset: bool

    @classmethod
    def from_cache(cls, data: dict[str, Any]) -> MakerPart:
        """Create a maker part from eufyMake Studio cache JSON."""
        return cls(
            key=_optional_str(data.get("part_key")),
            name=_optional_str(data.get("part_name")),
            remaining_percent=_optional_int(data.get("remaining_percent")),
            remaining_work_life=_optional_str(data.get("remaining_work_life")),
            maintenance_required=bool(data.get("maintenance")),
            support_reset=bool(data.get("support_reset")),
        )


@dataclass(frozen=True, kw_only=True)
class DeviceSnapshot:
    """A combined device state snapshot."""

    device: Device
    parts: list[MakerPart]
    dsk_available: bool
    white_ink_enabled: bool | None


def _optional_str(value: Any) -> str | None:
    """Return a non-empty string or None."""
    if value is None:
        return None
    text = str(value)
    return text or None


def _optional_int(value: Any) -> int | None:
    """Return an integer or None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _status_to_bool(value: Any) -> bool | None:
    """Convert cached numeric online status to a bool."""
    parsed = _optional_int(value)
    if parsed is None:
        return None
    return parsed == 1


def _extract_params(value: Any) -> dict[int, str]:
    """Extract device param_type -> param_value mappings."""
    if not isinstance(value, list):
        return {}

    params: dict[int, str] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        param_type = _optional_int(item.get("param_type"))
        param_value = item.get("param_value")
        if param_type is not None and param_value is not None:
            params[param_type] = str(param_value)
    return params
