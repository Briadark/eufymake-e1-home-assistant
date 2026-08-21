"""Device registry helpers for eufyMake entities."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_DEVICE_MODEL,
    CONF_DEVICE_SN,
    CONF_FIRMWARE_VERSION,
    CONF_HARDWARE_VERSION,
    DOMAIN,
)


def e1_device_info(
    entry: ConfigEntry,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return Home Assistant device info for the eufyMake E1."""
    serial_number = str(entry.data[CONF_DEVICE_SN])
    info = {
        "identifiers": {(DOMAIN, serial_number)},
        "manufacturer": "eufyMake",
        "model": _model_label("E1", entry.data.get(CONF_DEVICE_MODEL)),
        "name": "eufyMake E1",
        "serial_number": serial_number,
        "sw_version": _first_value(data, "firmware_version")
        or entry.data.get(CONF_FIRMWARE_VERSION),
        "hw_version": entry.data.get(CONF_HARDWARE_VERSION),
    }
    return _clean_device_info(info)


def p1_device_info(
    purifier: dict[str, Any],
    *,
    fallback_e1_sn: str,
) -> dict[str, Any]:
    """Return Home Assistant device info for a linked Purifier P1."""
    serial_number = str(
        purifier.get("serial_number") or f"{fallback_e1_sn}_purifier_p1"
    )
    info = {
        "identifiers": {(DOMAIN, serial_number)},
        "manufacturer": "eufyMake",
        "model": _model_label("Purifier P1", _first_value(purifier, "model")),
        "name": _first_value(purifier, "product_name") or "eufyMake Purifier P1",
        "serial_number": serial_number,
        "sw_version": _first_value(purifier, "firmware_version"),
        "hw_version": _first_value(purifier, "hardware_version"),
        "via_device": (DOMAIN, fallback_e1_sn),
    }
    return _clean_device_info(info)


def _first_value(data: dict[str, Any] | None, key: str) -> str | None:
    if not isinstance(data, dict):
        return None
    value = data.get(key)
    if value is None:
        return None
    string = str(value)
    return string if string else None


def _model_label(product: str, model: Any) -> str:
    model_value = str(model or "")
    if not model_value:
        return product
    if model_value.lower() in product.lower():
        return product
    return f"{product} ({model_value})"


def _clean_device_info(info: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in info.items() if value not in (None, "")}
