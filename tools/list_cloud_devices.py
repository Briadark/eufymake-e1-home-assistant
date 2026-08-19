"""List eufyMake cloud devices without printing secrets."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyeufymake import EufyMakeCloudClient, EufyMakeProfileCacheStore
from pyeufymake.cloud import EufyMakeCloudProbeError
from pyeufymake.profile import EufyMakeProfileCacheError


def default_profile_dir() -> Path:
    """Return the default eufyMake Studio profile directory."""
    return Path(os.environ["APPDATA"]) / "eufyMake Studio Profile"


def redact_id(value: str) -> str:
    """Redact an identifier while keeping it recognizable."""
    return f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "<redacted>"


def main() -> int:
    """Print a safe cloud device summary."""
    profile_dir = Path(os.environ.get("EUFYMAKE_PROFILE_DIR", default_profile_dir()))

    try:
        login = EufyMakeProfileCacheStore(profile_dir).load_login()
        devices = EufyMakeCloudClient(login).get_e1_devices()
    except (EufyMakeProfileCacheError, EufyMakeCloudProbeError) as err:
        print(f"Unable to list cloud devices: {err}")
        return 2

    print(f"Cloud eufyMake E1 devices from {login.app_domain}:")
    for device in devices:
        print(
            "  "
            f"{redact_id(device.serial_number)} "
            f"model={device.station_model} "
            f"sku={device.sku_number or '<unknown>'} "
            f"firmware={device.firmware_version or '<unknown>'} "
            f"mqtt_online={device.mqtt_online} "
            f"p2p_online={device.p2p_online}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
