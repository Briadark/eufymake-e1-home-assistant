"""Build and parse Home Assistant setup exports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .cache import EufyMakeCacheError
from .models import Device
from .mqtt_probe import build_probe_plan
from .profile import EufyMakeProfileCacheError

EXPORT_VERSION = 1


class EufyMakeSetupExportError(Exception):
    """Raised when a setup export cannot be created or parsed."""


def build_setup_export(
    profile_dir: str | Path,
    cache_dir: str | Path,
    *,
    serial_number: str | None = None,
) -> dict[str, Any]:
    """Build the JSON object Home Assistant needs for MQTT setup."""
    try:
        plan = build_probe_plan(profile_dir, cache_dir, serial_number=serial_number)
    except (EufyMakeCacheError, EufyMakeProfileCacheError) as err:
        raise EufyMakeSetupExportError(str(err)) from err

    _validate_e1_device(plan.device)
    if not plan.device.secret_key:
        raise EufyMakeSetupExportError("The selected E1 has no cached secret key")

    return {
        "version": EXPORT_VERSION,
        "region": _region_from_host(plan.host),
        "device_sn": plan.device.serial_number,
        "user_id": _user_id_from_username(plan.credentials.username),
        "email": plan.credentials.password,
        "secret_key": plan.device.secret_key,
        "mqtt_host": plan.host,
        "station_model": plan.device.station_model,
        "product_name": plan.device.product_name,
        "firmware_version": plan.device.firmware_version,
    }


def parse_setup_export(value: str | dict[str, Any]) -> dict[str, Any]:
    """Parse and validate a setup export."""
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except json.JSONDecodeError as err:
            raise EufyMakeSetupExportError(
                f"Setup export is not valid JSON: {err.msg}"
            ) from err
    else:
        data = value

    if not isinstance(data, dict):
        raise EufyMakeSetupExportError("Setup export must be a JSON object")

    version = data.get("version", EXPORT_VERSION)
    if version != EXPORT_VERSION:
        raise EufyMakeSetupExportError(f"Unsupported setup export version: {version}")

    for key in ("device_sn", "user_id", "email", "secret_key", "mqtt_host"):
        if not data.get(key):
            raise EufyMakeSetupExportError(f"Setup export is missing {key}")

    station_model = str(data.get("station_model", "V8260"))
    _validate_e1_station_model(station_model)

    parsed = {
        "region": str(data.get("region") or _region_from_host(data["mqtt_host"])),
        "device_sn": str(data["device_sn"]),
        "user_id": str(data["user_id"]),
        "email": str(data["email"]),
        "secret_key": str(data["secret_key"]),
        "mqtt_host": str(data["mqtt_host"]),
    }
    if data.get("firmware_version"):
        parsed["firmware_version"] = str(data["firmware_version"])
    return parsed


def _validate_e1_device(device: Device) -> None:
    _validate_e1_station_model(device.station_model)


def _validate_e1_station_model(station_model: str) -> None:
    if station_model != "V8260":
        raise EufyMakeSetupExportError(
            f"Only eufyMake E1 devices are supported, got {station_model}"
        )


def _region_from_host(host: str) -> str:
    return "eu" if "-eu." in host else "us"


def _user_id_from_username(username: str) -> str:
    return username.removeprefix("eufy_")
