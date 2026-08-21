"""Run one live eufyMake E1 MQTT status probe."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyeufymake.cache import EufyMakeCacheError
from pyeufymake.ink import find_ink_status
from pyeufymake.mqtt_client import EufyMakeMqttClientError, EufyMakeMqttStatusClient
from pyeufymake.mqtt_probe import build_probe_plan
from pyeufymake.mqtt_protocol import EufyMakeMqttProtocolError
from pyeufymake.profile import EufyMakeProfileCacheError
from pyeufymake.redaction import redact

BLOCKED_QUERY_COMMANDS = {
    1154: (
        "blocked because it has been observed to trigger an E1 offline/change "
        "notice during purifier discovery"
    ),
}


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
    parser.add_argument(
        "--listen-after-ink",
        type=float,
        default=0,
        help="Keep listening this many seconds after the first ink status.",
    )
    parser.add_argument(
        "--query",
        action="append",
        help=(
            "JSON MQTT payload to publish. Can be repeated. "
            "Defaults to the normal status query."
        ),
    )
    parser.add_argument(
        "--query-command",
        action="append",
        type=int,
        help="Convenience form for publishing {'commandType': N}. Can be repeated.",
    )
    parser.add_argument(
        "--publish-topic",
        choices=("query", "command"),
        default="query",
        help="MQTT topic family to publish the payload to.",
    )
    parser.add_argument(
        "--allow-risky-query",
        action="store_true",
        help="Allow query commands blocked by prior unsafe observations.",
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
    query_payloads = _query_payloads(
        args.query,
        args.query_command,
        allow_risky=args.allow_risky_query,
    )

    print(f"  publish_variant: {args.publish_variant}")
    print(f"  publish_topic: {args.publish_topic}")
    if query_payloads is not None:
        print(f"  query_payloads: {query_payloads}")
    print(f"  ca_file: {args.ca_file if args.ca_file else '<system default>'}")

    try:
        result = EufyMakeMqttStatusClient(plan, ca_file=args.ca_file).fetch_once(
            timeout=args.timeout,
            publish_variant=args.publish_variant,
            listen_after_ink=args.listen_after_ink,
            query_payloads=query_payloads,
            publish_topic=args.publish_topic,
            on_decoded_message=_print_decoded_message,
        )
    except KeyboardInterrupt:
        print("Probe stopped by user.")
        return 130
    except EufyMakeMqttClientError as err:
        print(f"MQTT probe failed: {err}")
        return 2

    if result.ink_status is not None:
        _print_ink_status(result.ink_status)
        return 0

    print(
        "No ink status received "
        f"(messages={result.messages}, decoded={result.decoded}, "
        f"undecoded={result.undecoded})"
    )
    return 1


def _query_payloads(
    raw_queries: list[str] | None,
    command_types: list[int] | None,
    *,
    allow_risky: bool,
) -> tuple[dict[str, Any], ...] | None:
    payloads: list[dict[str, Any]] = []
    for command_type in command_types or []:
        _check_query_command(command_type, allow_risky=allow_risky)
        payloads.append({"commandType": command_type})
    for raw_query in raw_queries or []:
        try:
            payload = json.loads(raw_query)
        except json.JSONDecodeError as err:
            raise SystemExit(f"Invalid --query JSON: {err}") from err
        if not isinstance(payload, dict):
            raise SystemExit("--query JSON must be an object")
        command_type = payload.get("commandType")
        if isinstance(command_type, int):
            _check_query_command(command_type, allow_risky=allow_risky)
        payloads.append(payload)
    return tuple(payloads) if payloads else None


def _check_query_command(command_type: int, *, allow_risky: bool) -> None:
    reason = BLOCKED_QUERY_COMMANDS.get(command_type)
    if reason and not allow_risky:
        raise SystemExit(
            f"Refusing --query-command {command_type}: {reason}. "
            "Use --allow-risky-query only for deliberate manual testing."
        )


def _print_decoded_message(message: Any) -> None:
    if find_ink_status(message.payload) is not None:
        return
    print(
        "Decoded non-ink MQTT message "
        f"variant={message.variant} "
        f"topic={redact_topic(message.topic)}:",
        flush=True,
    )
    print(redact(message.payload), flush=True)


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
