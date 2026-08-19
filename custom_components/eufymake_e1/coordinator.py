"""Coordinator for eufyMake E1."""

from __future__ import annotations

from datetime import timedelta
import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_CACHE_DIR,
    CONF_CA_FILE,
    CONF_DEVICE_SN,
    CONF_EMAIL,
    CONF_FIRMWARE_VERSION,
    CONF_MQTT_HOST,
    CONF_SECRET_KEY,
    CONF_USER_ID,
    DOMAIN,
)
from .pyeufymake.models import Device
from .pyeufymake.mqtt_client import EufyMakeMqttClientError, EufyMakeMqttStatusClient
from .pyeufymake.mqtt_probe import MqttProbePlan, build_probe_plan
from .pyeufymake.mqtt_protocol import (
    MQTT_PORT,
    MqttCredentials,
    build_client_id,
    build_status_query,
    build_topics,
)

_LOGGER = logging.getLogger(__name__)
DEFAULT_MQTT_CA = Path(__file__).parent / "certs" / "ankermake_mqtt_ca.pem"


class EufyMakeE1Coordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and hold eufyMake E1 data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=1),
        )
        self.entry = entry

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the printer."""
        cache_dir = self.entry.data.get(CONF_CACHE_DIR)
        if cache_dir:
            return await self.hass.async_add_executor_job(
                self._load_cache_or_live_data,
                cache_dir,
            )

        return await self.hass.async_add_executor_job(self._load_live_data)

    def _load_cache_or_live_data(self, cache_dir: str) -> dict[str, Any]:
        """Load cached metadata and fetch live MQTT status when possible."""
        try:
            from .pyeufymake.cache import EufyMakeCacheError

            plan = build_probe_plan(
                _profile_dir_from_cache_dir(cache_dir),
                cache_dir,
                serial_number=self.entry.data.get(CONF_DEVICE_SN),
            )
        except EufyMakeCacheError:
            return self._load_cache_data(cache_dir)
        except Exception as err:
            raise UpdateFailed(str(err)) from err

        try:
            result = EufyMakeMqttStatusClient(
                plan,
                ca_file=_mqtt_ca_file(self.entry.data.get(CONF_CA_FILE)),
            ).fetch_once(timeout=25)
        except EufyMakeMqttClientError as err:
            _LOGGER.debug("Live MQTT update failed; falling back to cache: %s", err)
            return self._load_cache_data(cache_dir)

        return _data_from_live_result(
            result.ink_status,
            firmware_version=plan.device.firmware_version,
            mqtt_online=True,
            p2p_online=None,
        )

    def _load_cache_data(self, cache_dir: str) -> dict[str, Any]:
        """Load data from eufyMake Studio cache."""
        try:
            from .pyeufymake import EufyMakeCacheStore
            from .pyeufymake.cache import EufyMakeCacheError

            snapshot = EufyMakeCacheStore(cache_dir).load_snapshot(
                self.entry.data.get(CONF_DEVICE_SN)
            )
        except EufyMakeCacheError as err:
            raise UpdateFailed(str(err)) from err

        device = snapshot.device
        return {
            "availability": _availability(device.is_online),
            "print_status": None,
            "firmware_version": device.firmware_version,
            "mqtt_online": device.mqtt_online,
            "p2p_online": device.p2p_online,
            "ink": {},
            "waste_ink": _part_percent(snapshot.parts, "Waste"),
            "parts": [
                {
                    "key": part.key,
                    "name": part.name,
                    "remaining_percent": part.remaining_percent,
                    "remaining_work_life": part.remaining_work_life,
                    "maintenance_required": part.maintenance_required,
                    "support_reset": part.support_reset,
                }
                for part in snapshot.parts
            ],
        }

    def _load_live_data(self) -> dict[str, Any]:
        """Load live data from manually configured MQTT fields."""
        plan = self._manual_probe_plan()
        try:
            result = EufyMakeMqttStatusClient(
                plan,
                ca_file=_mqtt_ca_file(self.entry.data.get(CONF_CA_FILE)),
            ).fetch_once(timeout=25)
        except EufyMakeMqttClientError as err:
            raise UpdateFailed(str(err)) from err

        return _data_from_live_result(
            result.ink_status,
            firmware_version=plan.device.firmware_version,
            mqtt_online=True,
            p2p_online=None,
        )

    def _manual_probe_plan(self) -> MqttProbePlan:
        """Build a probe plan from config entry data."""
        data = self.entry.data
        missing = [
            key
            for key in (CONF_DEVICE_SN, CONF_USER_ID, CONF_EMAIL, CONF_SECRET_KEY)
            if not data.get(key)
        ]
        if missing:
            raise UpdateFailed(
                f"Missing MQTT configuration fields: {', '.join(missing)}"
            )

        device = Device(
            serial_number=data[CONF_DEVICE_SN],
            secret_key=data[CONF_SECRET_KEY],
            station_model="V8260",
            sku_number=None,
            product_name="eufyMake E1",
            product_region=None,
            firmware_version=data.get(CONF_FIRMWARE_VERSION),
            hardware_version=None,
            ip_address=None,
            mqtt_online=None,
            p2p_online=None,
            can_query=True,
            can_command=False,
            has_camera=False,
            params={},
        )
        user_id = data[CONF_USER_ID]
        return MqttProbePlan(
            host=data[CONF_MQTT_HOST],
            port=MQTT_PORT,
            credentials=MqttCredentials(
                username=f"eufy_{user_id}",
                password=data[CONF_EMAIL],
                client_id=build_client_id(user_id),
            ),
            topics=build_topics(device.serial_number, user_id),
            device=device,
            status_query=build_status_query(),
            has_secret_key=True,
        )


def _availability(value: bool | None) -> str:
    """Return a human-readable availability value."""
    if value is None:
        return "unknown"
    return "online" if value else "offline"


def _part_percent(parts: list[Any], name_fragment: str) -> int | None:
    """Return a part percentage by partial part name."""
    lowered = name_fragment.lower()
    for part in parts:
        name = (part.name or part.key or "").lower()
        if lowered in name:
            return part.remaining_percent
    return None


def _data_from_live_result(
    ink_status: Any,
    *,
    firmware_version: str | None,
    mqtt_online: bool | None,
    p2p_online: bool | None,
) -> dict[str, Any]:
    """Build coordinator data from live MQTT status."""
    ink = {}
    waste_ink = None
    if ink_status is not None:
        ink = {
            channel.channel: channel.remaining_percent
            for channel in ink_status.channels
        }
        if ink_status.waste_tank is not None:
            waste_ink = ink_status.waste_tank.remaining_percent

    return {
        "availability": "online" if ink_status is not None else "unknown",
        "print_status": None,
        "firmware_version": firmware_version,
        "mqtt_online": mqtt_online,
        "p2p_online": p2p_online,
        "ink": ink,
        "waste_ink": waste_ink,
        "parts": [],
    }


def _profile_dir_from_cache_dir(cache_dir: str) -> str:
    """Infer the eufyMake profile directory from the device cache path."""
    from pathlib import Path

    path = Path(cache_dir)
    parts = tuple(part.lower() for part in path.parts)
    suffix = ("cache", "offline", "device_info")
    if len(parts) >= len(suffix) and parts[-3:] == suffix:
        return str(path.parents[2])
    return str(path)


def _mqtt_ca_file(configured_path: str | None) -> Path:
    """Return the configured CA path or the bundled MQTT trust anchor."""
    if configured_path:
        return Path(configured_path)
    return DEFAULT_MQTT_CA
