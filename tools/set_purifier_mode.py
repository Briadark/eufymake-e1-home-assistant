"""Set linked Purifier P1 mode through MQTT using cached auth."""

from __future__ import annotations

import argparse
import importlib.util
import os
import ssl
import sys
import time
from pathlib import Path
from threading import Event
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyeufymake.mqtt_protocol import (
    build_app_frame,
    build_client_id,
    build_topics,
    decrypt_json_frame,
    decrypt_json_gcm_payload,
    resolve_mqtt_host,
)
from pyeufymake.profile import EufyMakeProfileCacheError, EufyMakeProfileCacheStore
from pyeufymake.redaction import redact

MODES = {
    "standby": 0,
    "silent": 1,
    "high": 2,
    "full_power": 3,
    "auto": 4,
}
DELAYS = {0, 60, 180, 300, 600}


def default_profile_dir() -> Path:
    """Return the default eufyMake Studio profile directory."""
    return Path(os.environ["APPDATA"]) / "eufyMake Studio Profile"


def default_ca_file() -> Path | None:
    """Return the bundled eufyMake MQTT CA certificate when available."""
    bundled = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "eufymake_e1"
        / "certs"
        / "ankermake_mqtt_ca.pem"
    )
    return bundled if bundled.exists() else None


def main() -> int:
    """Set linked P1 mode and print decoded reply/state messages."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=tuple(MODES))
    parser.add_argument(
        "--delay",
        type=int,
        default=0,
        choices=sorted(DELAYS),
        help="Delay-off seconds for Auto mode.",
    )
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--profile-dir", type=Path, default=default_profile_dir())
    parser.add_argument("--ca-file", type=Path, default=default_ca_file())
    args = parser.parse_args()

    if args.mode != "auto" and args.delay != 0:
        print("--delay is only valid for auto mode.")
        return 2

    auth = _load_auth_module()
    try:
        login = EufyMakeProfileCacheStore(args.profile_dir).load_login()
    except EufyMakeProfileCacheError as err:
        print(f"Unable to load cached login: {err}")
        return 2

    try:
        purifier = _load_purifier(auth, login)
    except auth.EufyMakeAuthError as err:
        print(f"Unable to load purifier from cloud: {err}")
        return 2

    if purifier is None:
        print("No linked Purifier P1 found.")
        return 1

    station_sn = _purifier_station_sn(purifier)
    secret_key = str(purifier.get("secret_key") or "")
    if not station_sn or not secret_key:
        print("Linked Purifier P1 is missing MQTT credentials.")
        return 2

    payload = {
        "commandType": 1600,
        "mode": MODES[args.mode],
        "delay": args.delay if args.mode == "auto" else 0,
    }
    topics = build_topics(station_sn, login.user_id)
    host = resolve_mqtt_host(login)

    print("Purifier mode command:")
    print(f"  target: {host}:8789")
    print(f"  station_sn: {redact_id(station_sn)}")
    print(f"  mode: {args.mode} ({MODES[args.mode]})")
    print(f"  delay: {payload['delay']}")
    print(f"  command: {redact(payload)}")

    return _publish_and_listen(
        host=host,
        user_id=login.user_id,
        email=login.email or "",
        topics=topics,
        secret_key=secret_key,
        payload=payload,
        ca_file=args.ca_file,
        timeout=args.timeout,
    )


def _load_purifier(auth: Any, login: Any) -> dict[str, Any] | None:
    country = (login.country_code or "NL").strip().upper()
    session_key = auth._perform_key_exchange(
        app_domain=login.app_domain,
        timeout=15,
    )
    response = auth._post_encrypted(
        app_domain=login.app_domain,
        path="/v1/app/query_fdm_list",
        body={},
        entry_id=session_key.entry_id,
        share_key_hex=session_key.share_key_hex,
        auth_token=login.auth_token,
        user_id=login.user_id,
        timeout=20,
        country=country,
        extra_headers=auth._desktop_headers(country),
    )
    if response.get("code") not in (0, 200):
        raise auth.EufyMakeAuthError(
            f"API error: code={response.get('code')} msg={response.get('msg')}"
        )

    data = response.get("data")
    if not isinstance(data, list):
        return None
    for device in data:
        if not isinstance(device, dict):
            continue
        for accessory in device.get("accessories") or ():
            if isinstance(accessory, dict) and _is_purifier(accessory):
                return accessory
    return None


def _publish_and_listen(
    *,
    host: str,
    user_id: str,
    email: str,
    topics: Any,
    secret_key: str,
    payload: dict[str, Any],
    ca_file: Path | None,
    timeout: float,
) -> int:
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("paho-mqtt is not installed.")
        return 2

    done = Event()
    state = {"reply": False, "notice": False}
    client = _build_client(mqtt, build_client_id(user_id))
    client.username_pw_set(f"eufy_{user_id}", password=email)
    if ca_file and ca_file.exists():
        client.tls_set(ca_certs=str(ca_file), tls_version=ssl.PROTOCOL_TLS_CLIENT)
    else:
        client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)

    def on_connect(
        client: Any,
        userdata: Any,
        flags: Any,
        rc: Any,
        *extra: Any,
    ) -> None:
        code = _reason_code_value(rc)
        if code != 0:
            print(f"MQTT connect failed with code {code}")
            done.set()
            return
        for topic in topics.subscriptions:
            client.subscribe(topic, qos=0)
        client.publish(topics.command, build_app_frame(payload, secret_key), qos=0)

    def on_message(client: Any, userdata: Any, message: Any) -> None:
        decoded = _try_decode(message.payload, secret_key)
        if decoded is None:
            return
        variant, decoded_payload = decoded
        command_type = decoded_payload.get("commandType")
        print(
            "Decoded P1 MQTT message "
            f"variant={variant} topic={redact_topic(message.topic)}:",
            flush=True,
        )
        print(redact(decoded_payload), flush=True)
        if command_type == 1600:
            state["reply"] = True
        if command_type == 1601:
            state["notice"] = True
        if state["reply"] and state["notice"]:
            done.set()

    def on_disconnect(
        client: Any,
        userdata: Any,
        disconnect_flags: Any,
        reason_code: Any,
        *extra: Any,
    ) -> None:
        code = _reason_code_value(reason_code)
        if code != 0:
            print(f"MQTT disconnected with code {code}", flush=True)
            done.set()

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    try:
        client.connect(host, 8789, keepalive=30)
        client.loop_start()
        done.wait(timeout)
    except KeyboardInterrupt:
        print("Command stopped by user.")
        return 130
    except Exception as err:
        print(f"MQTT command failed: {err}")
        return 2
    finally:
        client.loop_stop()
        client.disconnect()

    if not state["reply"]:
        print("No command reply received.")
        return 1
    return 0


def _try_decode(payload: bytes, secret_key: str) -> tuple[str, Any] | None:
    for variant, decoder in (
        ("cbc", decrypt_json_frame),
        ("gcm", decrypt_json_gcm_payload),
    ):
        try:
            decoded = decoder(payload, secret_key)
        except Exception:
            continue
        if isinstance(decoded, dict):
            return variant, decoded
    return None


def _load_auth_module():
    component_dir = (
        Path(__file__).resolve().parents[1] / "custom_components" / "eufymake_e1"
    )
    package_name = "custom_components.eufymake_e1"

    import types

    package = types.ModuleType(package_name)
    package.__path__ = [str(component_dir)]
    sys.modules[package_name] = package
    _load_module(f"{package_name}.const", component_dir / "const.py")
    return _load_module(f"{package_name}.auth", component_dir / "auth.py")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _is_purifier(accessory: dict[str, Any]) -> bool:
    product_name = str(accessory.get("product_name") or "").lower()
    model = str(
        accessory.get("device_model")
        or accessory.get("device_name")
        or accessory.get("machine_name")
        or ""
    ).upper()
    return (
        "purifier p1" in product_name
        or model in {"T5216", "TS5216"}
        or accessory.get("device_type") == 101
    )


def _purifier_station_sn(accessory: dict[str, Any]) -> str:
    """Return the P1 MQTT station id, preferring the purifier-owned id."""
    candidates = [
        str(accessory.get("station_sn") or ""),
        str(accessory.get("relate_sn") or ""),
    ]
    for candidate in candidates:
        if candidate.startswith("AS"):
            return candidate
    return next((candidate for candidate in candidates if candidate), "")


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


def _looks_like_id(value: str) -> bool:
    return len(value) > 8 and (
        value.startswith("AK")
        or value.startswith("AS")
        or value.startswith("AR")
        or value.startswith("eufy_")
        or any(char.isdigit() for char in value)
    )


def _build_client(mqtt: Any, client_id: str) -> Any:
    try:
        return mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
        )
    except AttributeError:
        return mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)


def _reason_code_value(reason_code: Any) -> int:
    return int(getattr(reason_code, "value", reason_code))


if __name__ == "__main__":
    raise SystemExit(main())
