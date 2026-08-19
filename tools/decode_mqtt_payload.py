"""Decode a saved eufyMake E1 MQTT payload capture."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyeufymake import EufyMakeCacheStore, find_ink_status
from pyeufymake.cache import EufyMakeCacheError
from pyeufymake.mqtt_protocol import (
    EufyMakeMqttProtocolError,
    decrypt_json_frame,
    decrypt_json_gcm_payload,
)
from pyeufymake.redaction import redact


def default_cache_dir() -> Path:
    """Return the default eufyMake Studio device cache directory."""
    return (
        Path(os.environ["APPDATA"])
        / "eufyMake Studio Profile"
        / "cache"
        / "offline"
        / "device_info"
    )


def main() -> int:
    """Decode a saved binary MQTT payload."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", type=Path, help="Path to a saved MQTT payload")
    parser.add_argument(
        "--variant",
        choices=("auto", "cbc", "gcm"),
        default="auto",
        help="Payload format to try",
    )
    parser.add_argument("--cache-dir", type=Path, default=default_cache_dir())
    parser.add_argument("--device-sn")
    args = parser.parse_args()

    try:
        snapshot = EufyMakeCacheStore(args.cache_dir).load_snapshot(args.device_sn)
    except EufyMakeCacheError as err:
        print(f"Unable to load device cache: {err}")
        return 2

    if not snapshot.device.secret_key:
        print("Unable to decode payload: cached E1 secret key is unavailable")
        return 2

    try:
        payload = args.payload.read_bytes()
    except OSError as err:
        print(f"Unable to read payload: {err}")
        return 2

    try:
        decoded = _decode(payload, snapshot.device.secret_key, args.variant)
    except EufyMakeMqttProtocolError as err:
        print(f"Unable to decode payload: {err}")
        return 2

    ink_status = find_ink_status(decoded)
    if ink_status is None:
        print(json.dumps(redact(decoded), indent=2, sort_keys=True))
        return 0

    print("Ink status:")
    for channel in ink_status.channels:
        print(f"  {channel.channel}: {channel.remaining_percent}%")
    if ink_status.waste_tank is not None:
        print(f"  waste_tank: {ink_status.waste_tank.remaining_percent}%")
    return 0


def _decode(payload: bytes, secret_key: str, variant: str) -> object:
    if variant in ("auto", "cbc"):
        try:
            return decrypt_json_frame(payload, secret_key)
        except EufyMakeMqttProtocolError:
            if variant == "cbc":
                raise
    return decrypt_json_gcm_payload(payload, secret_key)


if __name__ == "__main__":
    raise SystemExit(main())
