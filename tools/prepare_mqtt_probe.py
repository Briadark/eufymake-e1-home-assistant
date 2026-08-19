"""Prepare a redacted eufyMake E1 MQTT probe summary without connecting."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyeufymake.cache import EufyMakeCacheError
from pyeufymake.mqtt_probe import build_probe_plan
from pyeufymake.mqtt_protocol import EufyMakeMqttProtocolError
from pyeufymake.profile import EufyMakeProfileCacheError


def default_profile_dir() -> Path:
    """Return the default eufyMake Studio profile directory."""
    return Path(os.environ["APPDATA"]) / "eufyMake Studio Profile"


def redact_id(value: str | None) -> str:
    """Redact an identifier while keeping it recognizable."""
    if not value:
        return "<none>"
    return f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "<redacted>"


def main() -> int:
    """Print a safe MQTT probe plan."""
    profile_dir = Path(os.environ.get("EUFYMAKE_PROFILE_DIR", default_profile_dir()))
    cache_dir = Path(
        os.environ.get(
            "EUFYMAKE_CACHE_DIR",
            profile_dir / "cache" / "offline" / "device_info",
        )
    )
    serial_number = os.environ.get("EUFYMAKE_DEVICE_SN")

    try:
        plan = build_probe_plan(profile_dir, cache_dir, serial_number=serial_number)
    except (
        EufyMakeCacheError,
        EufyMakeMqttProtocolError,
        EufyMakeProfileCacheError,
    ) as err:
        print(f"Unable to prepare MQTT probe: {err}")
        return 2

    print("MQTT probe plan:")
    print(f"  target: {plan.host}:{plan.port}")
    print(f"  station_model: {plan.device.station_model}")
    print(f"  station_sn: {redact_id(plan.device.serial_number)}")
    print(f"  username: {redact_id(plan.credentials.username)}")
    print("  password: <redacted>")
    print(f"  client_id: {redact_id(plan.credentials.client_id)}")
    print(f"  secret_key_available: {plan.has_secret_key}")
    print(f"  status_query: {plan.status_query}")
    print("  subscriptions:")
    for topic in plan.topics.subscriptions:
        print(f"    {redact_topic(topic)}")
    print(f"  publish_query: {redact_topic(plan.topics.query)}")
    return 0


def redact_topic(topic: str) -> str:
    """Redact station/user ids inside a topic."""
    parts = topic.split("/")
    redacted = [redact_id(part) if _looks_like_id(part) else part for part in parts]
    return "/".join(redacted)


def _looks_like_id(value: str) -> bool:
    return len(value) > 8 and (
        value.startswith("AK")
        or value.startswith("AR")
        or value.startswith("eufy_")
        or any(char.isdigit() for char in value)
    )


if __name__ == "__main__":
    raise SystemExit(main())
