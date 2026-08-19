"""Summarize eufyMake Studio cache data without printing secrets."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyeufymake import EufyMakeCacheStore, EufyMakeProfileCacheStore
from pyeufymake.cache import EufyMakeCacheError
from pyeufymake.profile import EufyMakeProfileCacheError


def default_profile_dir() -> Path:
    """Return the default eufyMake Studio profile directory."""
    return Path(os.environ["APPDATA"]) / "eufyMake Studio Profile"


def redact_id(value: str | None) -> str:
    """Redact an identifier while keeping it recognizable in logs."""
    if not value:
        return "<none>"
    if len(value) <= 8:
        return "<redacted>"
    return f"{value[:4]}...{value[-4:]}"


def format_expiry(value: int | None) -> str:
    """Format a unix timestamp."""
    if value is None:
        return "<unknown>"
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def main() -> None:
    """Print a safe operational summary."""
    profile_dir = Path(os.environ.get("EUFYMAKE_PROFILE_DIR", default_profile_dir()))
    cache_dir = Path(
        os.environ.get(
            "EUFYMAKE_CACHE_DIR",
            profile_dir / "cache" / "offline" / "device_info",
        )
    )

    try:
        login = EufyMakeProfileCacheStore(profile_dir).load_login()
    except EufyMakeProfileCacheError as err:
        print(f"Login cache: unavailable ({err})")
    else:
        print("Login cache:")
        print(f"  user_id: {redact_id(login.user_id)}")
        print(f"  token_expires_at: {format_expiry(login.token_expires_at)}")
        print(f"  app_domain: {login.app_domain or '<unknown>'}")
        print(f"  make_it_real_domain: {login.make_it_real_domain or '<unknown>'}")
        print(f"  country_code: {login.country_code or '<unknown>'}")
        print(f"  geo_key_available: {bool(login.geo_key)}")
        print(f"  test_flag: {login.test_flag or '<unknown>'}")

    try:
        snapshot = EufyMakeCacheStore(cache_dir).load_snapshot()
    except EufyMakeCacheError as err:
        print(f"\nDevice cache: unavailable ({err})")
        return

    device = snapshot.device
    print("\nDevice cache:")
    print(f"  serial_number: {redact_id(device.serial_number)}")
    print(f"  station_model: {device.station_model}")
    print(f"  sku_number: {device.sku_number or '<unknown>'}")
    print(f"  product_region: {device.product_region or '<unknown>'}")
    print(f"  firmware_version: {device.firmware_version or '<unknown>'}")
    print(f"  hardware_version: {device.hardware_version or '<unknown>'}")
    print(f"  mqtt_online: {device.mqtt_online}")
    print(f"  p2p_online: {device.p2p_online}")
    print(f"  can_query: {device.can_query}")
    print(f"  can_command: {device.can_command}")
    print(f"  has_camera: {device.has_camera}")
    print(f"  dsk_available: {snapshot.dsk_available}")
    print(f"  white_ink_enabled: {snapshot.white_ink_enabled}")

    print("\nParts:")
    for part in snapshot.parts:
        label = part.name or part.key or "<unnamed>"
        print(
            "  "
            f"{label}: {part.remaining_percent}% "
            f"({part.remaining_work_life or '<unknown>'})"
        )


if __name__ == "__main__":
    main()
