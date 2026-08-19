"""Live MQTT client for eufyMake E1 status."""

from __future__ import annotations

import ssl
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Any, Callable

from .ink import InkStatus, find_ink_status
from .mqtt_probe import MqttProbePlan
from .mqtt_protocol import (
    EufyMakeMqttProtocolError,
    build_app_frame,
    build_gcm_payload,
    decrypt_json_frame,
    decrypt_json_gcm_payload,
)


class EufyMakeMqttClientError(Exception):
    """Raised when live MQTT communication fails."""


@dataclass(frozen=True, kw_only=True)
class DecodedMqttMessage:
    """A decoded MQTT message."""

    topic: str
    variant: str
    payload: Any
    command_type: int | None


@dataclass(frozen=True, kw_only=True)
class MqttStatusResult:
    """Result from one MQTT status probe."""

    messages: int
    decoded: int
    undecoded: int
    ink_status: InkStatus | None
    decoded_messages: tuple[DecodedMqttMessage, ...] = field(default_factory=tuple)


class EufyMakeMqttStatusClient:
    """Fetch one live E1 status snapshot through eufyMake MQTT."""

    def __init__(
        self,
        plan: MqttProbePlan,
        *,
        ca_file: str | Path | None = None,
    ) -> None:
        """Initialize the MQTT status client."""
        if not plan.device.secret_key:
            raise EufyMakeMqttClientError("Cached E1 secret key is unavailable")
        self.plan = plan
        self.ca_file = Path(ca_file) if ca_file else None

    def fetch_once(
        self,
        *,
        timeout: float = 25,
        publish_variant: str = "cbc",
        listen_after_ink: float = 0,
        on_decoded_message: Callable[[DecodedMqttMessage], None] | None = None,
    ) -> MqttStatusResult:
        """Connect, request status, and wait for an ink status message."""
        try:
            import paho.mqtt.client as mqtt
        except ImportError as err:
            raise EufyMakeMqttClientError("paho-mqtt is not installed") from err

        done = Event()
        decoded_messages: list[DecodedMqttMessage] = []
        state: dict[str, Any] = {
            "messages": 0,
            "decoded": 0,
            "undecoded": 0,
            "ink_status": None,
            "ink_seen_at": None,
            "error": None,
        }

        client = _build_client(mqtt, self.plan.credentials.client_id)
        client.username_pw_set(
            self.plan.credentials.username,
            password=self.plan.credentials.password,
        )
        if self.ca_file and self.ca_file.exists():
            client.tls_set(
                ca_certs=str(self.ca_file),
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )
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
                state["error"] = f"MQTT connect failed with code {code}"
                done.set()
                return
            for topic in self.plan.topics.subscriptions:
                client.subscribe(topic, qos=0)
            self._publish_query(client, publish_variant)

        def on_message(client: Any, userdata: Any, message: Any) -> None:
            state["messages"] += 1
            decoded = self._try_decode(message.payload)
            if decoded is None:
                state["undecoded"] += 1
                return

            variant, payload = decoded
            state["decoded"] += 1
            decoded_message = DecodedMqttMessage(
                topic=message.topic,
                variant=variant,
                payload=payload,
                command_type=_command_type(payload),
            )
            decoded_messages.append(decoded_message)
            if on_decoded_message is not None:
                on_decoded_message(decoded_message)

            ink_status = find_ink_status(payload)
            if ink_status is not None:
                state["ink_status"] = ink_status
                if state["ink_seen_at"] is None:
                    state["ink_seen_at"] = time.monotonic()
                if listen_after_ink <= 0:
                    done.set()

        def on_disconnect(
            client: Any,
            userdata: Any,
            disconnect_flags: Any,
            reason_code: Any,
            *extra: Any,
        ) -> None:
            code = _reason_code_value(reason_code)
            if code != 0 and not done.is_set():
                state["error"] = f"MQTT disconnected with code {code}"
                done.set()

        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect

        try:
            client.connect(self.plan.host, self.plan.port, keepalive=30)
            client.loop_start()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if done.wait(0.2):
                    break
                ink_seen_at = state["ink_seen_at"]
                if (
                    ink_seen_at is not None
                    and listen_after_ink > 0
                    and time.monotonic() - float(ink_seen_at) >= listen_after_ink
                ):
                    break
        except Exception as err:
            raise EufyMakeMqttClientError(f"MQTT probe failed: {err}") from err
        finally:
            client.loop_stop()
            client.disconnect()

        if state["error"] and not decoded_messages:
            raise EufyMakeMqttClientError(str(state["error"]))

        return MqttStatusResult(
            messages=int(state["messages"]),
            decoded=int(state["decoded"]),
            undecoded=int(state["undecoded"]),
            ink_status=state["ink_status"],
            decoded_messages=tuple(decoded_messages),
        )

    def _publish_query(self, client: Any, variant: str) -> None:
        if variant not in ("cbc", "gcm", "both"):
            raise EufyMakeMqttClientError(f"Unsupported publish variant: {variant}")
        secret_key = self.plan.device.secret_key
        if secret_key is None:
            raise EufyMakeMqttClientError("Cached E1 secret key is unavailable")

        if variant in ("cbc", "both"):
            client.publish(
                self.plan.topics.query,
                build_app_frame(self.plan.status_query, secret_key),
                qos=0,
            )
        if variant in ("gcm", "both"):
            client.publish(
                self.plan.topics.query,
                build_gcm_payload(self.plan.status_query, secret_key),
                qos=0,
            )

    def _try_decode(self, payload: bytes) -> tuple[str, Any] | None:
        secret_key = self.plan.device.secret_key
        if secret_key is None:
            return None
        decoders = (
            ("cbc", decrypt_json_frame),
            ("gcm", decrypt_json_gcm_payload),
        )
        for variant, decoder in decoders:
            try:
                return variant, decoder(payload, secret_key)
            except EufyMakeMqttProtocolError:
                pass
        return None


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


def _command_type(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("commandType")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
