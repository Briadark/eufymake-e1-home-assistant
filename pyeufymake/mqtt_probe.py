"""Preparation helpers for eufyMake E1 MQTT probing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .cache import EufyMakeCacheStore
from .models import Device
from .mqtt_protocol import (
    MQTT_PORT,
    MqttCredentials,
    MqttTopics,
    build_credentials,
    build_status_query,
    build_topics,
    resolve_mqtt_host,
)
from .profile import EufyMakeProfileCacheStore


@dataclass(frozen=True, kw_only=True)
class MqttProbePlan:
    """Inputs needed for a future live MQTT probe."""

    host: str
    port: int
    credentials: MqttCredentials
    topics: MqttTopics
    device: Device
    status_query: dict[str, int]
    has_secret_key: bool


def build_probe_plan(
    profile_dir: str | Path,
    cache_dir: str | Path,
    *,
    serial_number: str | None = None,
) -> MqttProbePlan:
    """Load cached E1 data and build a non-network MQTT probe plan."""
    login = EufyMakeProfileCacheStore(profile_dir).load_login()
    snapshot = EufyMakeCacheStore(cache_dir).load_snapshot(serial_number)
    return MqttProbePlan(
        host=resolve_mqtt_host(login),
        port=MQTT_PORT,
        credentials=build_credentials(login),
        topics=build_topics(snapshot.device.serial_number, login.user_id),
        device=snapshot.device,
        status_query=build_status_query(),
        has_secret_key=bool(snapshot.device.secret_key),
    )
