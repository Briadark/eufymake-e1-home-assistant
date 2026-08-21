"""Listen to linked Purifier P1 MQTT messages using cached auth."""

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
    build_client_id,
    build_topics,
    decrypt_json_frame,
    decrypt_json_gcm_payload,
    resolve_mqtt_host,
)
from pyeufymake.profile import EufyMakeProfileCacheError, EufyMakeProfileCacheStore
from pyeufymake.redaction import redact


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
    """Listen to P1 MQTT topics without publishing commands."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--profile-dir", type=Path, default=default_profile_dir())
    parser.add_argument("--ca-file", type=Path, default=default_ca_file())
    args = parser.parse_args()

    auth = _load_auth_module()
    try:
        login = EufyMakeProfileCacheStore(args.profile_dir).load_login()
    except EufyMakeProfileCacheError as err:
        print(f"Unable to load cached login: {err}")
        return 2

    try:
        context = _load_purifier_context(auth, login)
    except auth.EufyMakeAuthError as err:
        print(f"Unable to load purifier from cloud: {err}")
        return 2

    if context is None:
        print("No linked Purifier P1 found.")
        return 1

    station_ids = tuple(
        value
        for value in (
            str(context["purifier"].get("station_sn") or ""),
            str(context["purifier"].get("relate_sn") or ""),
            str(context["parent"].get("station_sn") or ""),
        )
        if value
    )
    secrets = tuple(
        (label, key)
        for label, key in (
            ("purifier", str(context["purifier"].get("secret_key") or "")),
            ("linked_e1", str(context["parent"].get("secret_key") or "")),
        )
        if key
    )
    if not station_ids or not secrets:
        print("Linked Purifier P1 is missing MQTT credentials.")
        return 2

    topics = _subscription_topics(station_ids, login.user_id)
    host = resolve_mqtt_host(login)
    print("Purifier MQTT listener:")
    print(f"  target: {host}:8789")
    print(f"  purifier: {context['purifier'].get('product_name') or 'Purifier P1'}")
    print(
        "  topic_ids: "
        + ", ".join(redact_id(station_id) for station_id in sorted(set(station_ids)))
    )
    print(f"  ca_file: {args.ca_file if args.ca_file else '<system default>'}")
    print("  publish: disabled")
    print("Change the purifier mode in the app now.")

    return _listen(
        host=host,
        user_id=login.user_id,
        email=login.email or "",
        topics=topics,
        secrets=secrets,
        ca_file=args.ca_file,
        timeout=args.timeout,
    )


def _load_purifier_context(auth: Any, login: Any) -> dict[str, dict[str, Any]] | None:
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
                return {"parent": device, "purifier": accessory}
    return None


def _listen(
    *,
    host: str,
    user_id: str,
    email: str,
    topics: tuple[str, ...],
    secrets: tuple[tuple[str, str], ...],
    ca_file: Path | None,
    timeout: float,
) -> int:
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("paho-mqtt is not installed.")
        return 2

    done = Event()
    counters = {"messages": 0, "decoded": 0, "undecoded": 0}
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
        for topic in topics:
            client.subscribe(topic, qos=0)

    def on_message(client: Any, userdata: Any, message: Any) -> None:
        counters["messages"] += 1
        decoded = _try_decode(message.payload, secrets)
        if decoded is None:
            counters["undecoded"] += 1
            print(f"Undecoded message topic={redact_topic(message.topic)}", flush=True)
            return
        counters["decoded"] += 1
        key_label, variant, payload = decoded
        print(
            "Decoded P1 MQTT message "
            f"key={key_label} variant={variant} "
            f"topic={redact_topic(message.topic)}:",
            flush=True,
        )
        print(redact(payload), flush=True)

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
        print("Listener stopped by user.")
        return 130
    except Exception as err:
        print(f"MQTT listener failed: {err}")
        return 2
    finally:
        client.loop_stop()
        client.disconnect()

    print(
        "Done "
        f"(messages={counters['messages']}, decoded={counters['decoded']}, "
        f"undecoded={counters['undecoded']})"
    )
    return 0


def _subscription_topics(station_ids: tuple[str, ...], user_id: str) -> tuple[str, ...]:
    """Return exact and wildcard subscriptions for linked P1 discovery."""
    topics: set[str] = {
        f"/phone/user/{user_id}/change_notice",
        "/phone/maker/+/notice",
        "/phone/maker/+/command/reply",
        "/phone/maker/+/query/reply",
        "/phone/maker/+/change_notice",
        "/phone/maker/field/notice",
        "/phone/maker/field/command/reply",
        "/phone/maker/field/query/reply",
    }
    for station_id in station_ids:
        topics.update(build_topics(station_id, user_id).subscriptions)
    return tuple(sorted(topics))


def _try_decode(
    payload: bytes,
    secrets: tuple[tuple[str, str], ...],
) -> tuple[str, str, Any] | None:
    for key_label, secret_key in secrets:
        for variant, decoder in (
            ("cbc", decrypt_json_frame),
            ("gcm", decrypt_json_gcm_payload),
        ):
            try:
                return key_label, variant, decoder(payload, secret_key)
            except Exception:
                pass
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
