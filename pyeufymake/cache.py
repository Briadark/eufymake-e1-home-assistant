"""Read eufyMake Studio cache files.

This module is intentionally read-only. It exists to understand the data model
before the live cloud/MQTT client is implemented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Device, DeviceSnapshot, MakerPart

E1_STATION_MODEL = "V8260"


class EufyMakeCacheError(Exception):
    """Raised when eufyMake cache data cannot be loaded."""


class EufyMakeCacheStore:
    """Load device data from a eufyMake Studio cache directory."""

    def __init__(self, cache_dir: str | Path) -> None:
        """Initialize the cache store."""
        self.cache_dir = Path(cache_dir)

    def load_snapshot(self, serial_number: str | None = None) -> DeviceSnapshot:
        """Load one device snapshot.

        If no serial number is supplied, the first E1/V8260 device is returned.
        """
        devices = self.load_devices()
        if serial_number:
            device = next(
                (
                    item
                    for item in devices
                    if item.serial_number.lower() == serial_number.lower()
                ),
                None,
            )
        else:
            device = next(
                (item for item in devices if item.station_model == E1_STATION_MODEL),
                None,
            )

        if device is None:
            raise EufyMakeCacheError("No matching eufyMake E1 device found in cache")

        return DeviceSnapshot(
            device=device,
            parts=self.load_parts(device.serial_number),
            dsk_available=self.has_dsk_key(device.serial_number),
            white_ink_enabled=self.load_white_ink_enabled(device.serial_number),
        )

    def load_devices(self) -> list[Device]:
        """Load cached devices."""
        payload = self._load_signed_json("device_list.json")
        data = payload.get("data", [])
        if not isinstance(data, list):
            raise EufyMakeCacheError("device_list.json data is not a list")
        return [Device.from_cache(item) for item in data if isinstance(item, dict)]

    def load_parts(self, serial_number: str) -> list[MakerPart]:
        """Load cached maker part records for a device."""
        payload = self._load_signed_json("makerpart.json")
        data = payload.get("data", [])
        if not isinstance(data, list):
            return []
        return [
            MakerPart.from_cache(item)
            for item in data
            if isinstance(item, dict) and item.get("station_sn") == serial_number
        ]

    def has_dsk_key(self, serial_number: str) -> bool:
        """Return whether a DSK key is cached for a device."""
        payload = self._load_signed_json("device_dsk.json", required=False)
        data = payload.get("data", {})
        dsk_keys = data.get("dsk_keys", []) if isinstance(data, dict) else []
        return any(
            isinstance(item, dict) and item.get("station_sn") == serial_number
            for item in dsk_keys
        )

    def load_white_ink_enabled(self, serial_number: str) -> bool | None:
        """Load cached white ink type state when present."""
        path = self.cache_dir / "white_ink_type.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        value = data.get(serial_number) if isinstance(data, dict) else None
        return value if isinstance(value, bool) else None

    def _load_signed_json(
        self, filename: str, *, required: bool = True
    ) -> dict[str, Any]:
        """Load a JSON cache file with the common signed response shape."""
        path = self.cache_dir / filename
        if not path.exists():
            if required:
                raise EufyMakeCacheError(f"Missing cache file: {filename}")
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as err:
            raise EufyMakeCacheError(f"Could not read {filename}: {err}") from err
        except json.JSONDecodeError as err:
            raise EufyMakeCacheError(f"Invalid JSON in {filename}: {err}") from err

        if not isinstance(payload, dict):
            raise EufyMakeCacheError(f"{filename} does not contain a JSON object")
        return payload

