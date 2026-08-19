"""Coordinator for eufyMake E1."""

from __future__ import annotations

from datetime import datetime, timezone
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEVICE_SN,
    CONF_EMAIL,
    CONF_FIRMWARE_VERSION,
    CONF_MQTT_HOST,
    CONF_SECRET_KEY,
    CONF_USER_ID,
    DOMAIN,
)
from .runtime import (
    EufyMakeMqttStatusClient,
    EufyMakeRuntimeError,
    MqttProbePlan,
    build_probe_plan,
)

_LOGGER = logging.getLogger(__name__)


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
        return await self.hass.async_add_executor_job(self._load_live_data)

    def _load_live_data(self) -> dict[str, Any]:
        """Load live data from manually configured MQTT fields."""
        plan = self._manual_probe_plan()
        try:
            result = EufyMakeMqttStatusClient(plan).fetch_once(timeout=25)
        except EufyMakeRuntimeError as err:
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

        return build_probe_plan(
            host=data[CONF_MQTT_HOST],
            station_sn=data[CONF_DEVICE_SN],
            user_id=data[CONF_USER_ID],
            email=data[CONF_EMAIL],
            secret_key=data[CONF_SECRET_KEY],
            firmware_version=data.get(CONF_FIRMWARE_VERSION),
        )


def _data_from_live_result(
    ink_status: Any,
    *,
    firmware_version: str | None,
    mqtt_online: bool | None,
    p2p_online: bool | None,
) -> dict[str, Any]:
    """Build coordinator data from live MQTT status."""
    ink = {}
    ink_details = {}
    waste_ink = None
    waste_ink_details = {}
    if ink_status is not None:
        ink = {
            channel.channel: channel.remaining_percent
            for channel in ink_status.channels
        }
        ink_details = {
            channel.channel: _ink_channel_attributes(channel)
            for channel in ink_status.channels
        }
        if ink_status.waste_tank is not None:
            waste_ink = ink_status.waste_tank.remaining_percent
            waste_ink_details = _ink_channel_attributes(ink_status.waste_tank)

    return {
        "availability": "online" if ink_status is not None else "unknown",
        "print_status": None,
        "firmware_version": firmware_version,
        "mqtt_online": mqtt_online,
        "p2p_online": p2p_online,
        "ink": ink,
        "ink_details": ink_details,
        "waste_ink": waste_ink,
        "waste_ink_details": waste_ink_details,
        "parts": [],
    }


def _ink_channel_attributes(channel: Any) -> dict[str, Any]:
    """Return public HA attributes for an ink or waste tank record."""
    return {
        "status": getattr(channel, "status", None),
        "manufacture_date": _date_from_timestamp(
            getattr(channel, "manufacture_timestamp", None)
        ),
        "expiration_date": _date_from_timestamp(
            getattr(channel, "expiration_timestamp", None)
        ),
        "days_until_expiration": getattr(
            channel,
            "distance_expiration_days",
            None,
        ),
        "expired": getattr(channel, "expired", None),
    }


def _date_from_timestamp(timestamp: int | None) -> str | None:
    """Convert a Unix timestamp to an ISO calendar date."""
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()
