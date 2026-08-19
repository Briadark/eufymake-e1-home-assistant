"""Run one live eufyMake E1 MQTT status probe."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyeufymake.cache import EufyMakeCacheError
from pyeufymake.ink import find_ink_status
from pyeufymake.mqtt_client import EufyMakeMqttClientError, EufyMakeMqttStatusClient
from pyeufymake.mqtt_probe import build_probe_plan
from pyeufymake.mqtt_protocol import EufyMakeMqttProtocolError
from pyeufymake.profile import EufyMakeProfileCacheError
from pyeufymake.redaction import redact


def default_profile_dir() -> Path:
    """Return the default eufyMake Studio profile directory."""
    return Path(os.environ["APPDATA"]) / "eufyMake Studio Profile"


def default_cache_dir(profile_dir: Path) -> Path:
    """Return the default eufyMake Studio device cache directory."""
    return profile_dir / "cache" / "offline" / "device_info"


def default_ca_file() -> Path | None:
    """Return the bundled eufyMake MQTT CA certificate when available."""
    bundled = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "eufymake_e1"
        / "certs"
        / "ankermake_mqtt_ca.pem"
    )
    if bundled.exists():
        return bundled

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    candidates = (
        Path(local_app_data)
        / "eufyMake Studio"
        / "resources"
        / "crt"
        / "make-us.crt",
        Path(local_app_data) / "eufyMake Studio" / "make-us.crt",
    )
    return next((path for path in candidates if path.exists()), None)


def redact_id(value: str | None) -> str:
    """Redact an identifier while keeping it recognizable."""
    if not value:
        return "<none>"
    return f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "<redacted>"


def redact_topic(topic: str) -> str:
    """Redact station/user ids inside a topic."""
    return "/".join(
        redact_id(part) if _looks_like_id(part) else part
        for part in topic.split("/")
    )


def main() -> int:
    """Run the live MQTT probe."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=25)
    parser.add_argument(
        "--publish-variant",
        choices=("cbc", "gcm", "both"),
        default="cbc",
    )
    parser.add_argument("--profile-dir", type=Path, default=default_profile_dir())
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--device-sn")
    parser.add_argument("--ca-file", type=Path, default=default_ca_file())
    args = parser.parse_args()

    cache_dir = args.cache_dir or default_cache_dir(args.profile_dir)
    try:
        plan = build_probe_plan(
            args.profile_dir,
            cache_dir,
            serial_number=args.device_sn,
        )
    except (
        EufyMakeCacheError,
        EufyMakeMqttProtocolError,
        EufyMakeProfileCacheError,
    ) as err:
        print(f"Unable to prepare MQTT probe: {err}")
        return 2

    if not plan.device.secret_key:
        print("Unable to run MQTT probe: cached E1 secret key is unavailable")
        return 2

    print("Live MQTT probe:")
    print(f"  target: {plan.host}:{plan.port}")
    print(f"  station_model: {plan.device.station_model}")
    print(f"  station_sn: {redact_id(plan.device.serial_number)}")
    print(f"  publish_variant: {args.publish_variant}")
    print(f"  ca_file: {args.ca_file if args.ca_file else '<system default>'}")

    try:
        result = EufyMakeMqttStatusClient(plan, ca_file=args.ca_file).fetch_once(
            timeout=args.timeout,
            publish_variant=args.publish_variant,
        )
    except EufyMakeMqttClientError as err:
        print(f"MQTT probe failed: {err}")
        return 2

    for message in result.decoded_messages:
        if find_ink_status(message.payload) is not None:
            continue
        print(
            "Decoded non-ink MQTT message "
            f"variant={message.variant} "
            f"topic={redact_topic(message.topic)}:"
        )
        print(redact(message.payload))

    if result.ink_status is not None:
        _print_ink_status(result.ink_status)
        return 0

    print(
        "No ink status received "
        f"(messages={result.messages}, decoded={result.decoded}, "
        f"undecoded={result.undecoded})"
    )
    return 1


def _print_ink_status(ink_status: object) -> None:
    print("Ink status received:")
    for channel in ink_status.channels:
        print(f"  {channel.channel}: {channel.remaining_percent}%")
    if ink_status.waste_tank is not None:
        print(f"  waste_tank: {ink_status.waste_tank.remaining_percent}%")


def _looks_like_id(value: str) -> bool:
    return len(value) > 8 and (
        value.startswith("AK")
        or value.startswith("AR")
        or value.startswith("eufy_")
        or any(char.isdigit() for char in value)
    )


if __name__ == "__main__":
    raise SystemExit(main())
