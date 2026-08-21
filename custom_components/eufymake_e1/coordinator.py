"""Coordinator for eufyMake E1."""

from __future__ import annotations

from datetime import datetime, timezone
from datetime import timedelta
import json
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_APP_DOMAIN,
    CONF_AUTH_TOKEN,
    CONF_COUNTRY,
    CONF_DEVICE_SN,
    CONF_EMAIL,
    CONF_FIRMWARE_VERSION,
    CONF_MQTT_HOST,
    CONF_SECRET_KEY,
    CONF_TOKEN_EXPIRES_AT,
    CONF_USER_ID,
    DOMAIN,
)
from .runtime import (
    ACCESSORY_QUERY_COMMANDS,
    EufyMakeMqttCommandClient,
    EufyMakeMqttStatusClient,
    EufyMakeRuntimeError,
    MqttProbePlan,
    build_probe_plan,
    find_accessory_status,
)

_LOGGER = logging.getLogger(__name__)
PURIFIER_REFRESH_INTERVAL = 300
PURIFIER_MODE_COMMAND = 1600
PURIFIER_DELAY_VALUES = {0, 60, 180, 300, 600}
PURIFIER_MODE_VALUES = {
    "Standby": 0,
    "Silent": 1,
    "High": 2,
    "Full power": 3,
    "Auto": 4,
}


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
        self._purifier_data: dict[str, Any] | None = None
        self._purifier_credentials: dict[str, str] | None = None
        self._purifier_loaded_at = 0.0

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the printer."""
        return await self.hass.async_add_executor_job(self._load_live_data)

    def _load_live_data(self) -> dict[str, Any]:
        """Load live data from manually configured MQTT fields."""
        plan = self._manual_probe_plan()
        try:
            result = EufyMakeMqttStatusClient(plan).fetch_once(
                timeout=25,
                listen_after_ink=5,
                query_payloads=(
                    plan.status_query,
                    *ACCESSORY_QUERY_COMMANDS,
                ),
            )
        except EufyMakeRuntimeError as err:
            raise UpdateFailed(str(err)) from err

        data = _data_from_live_result(
            result.ink_status,
            decoded_messages=result.decoded_messages,
            firmware_version=plan.device.firmware_version,
            mqtt_online=True,
            p2p_online=None,
        )
        _preserve_previous_accessory(data, self.data)
        data["purifier"] = self._load_purifier_data()
        return data

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

    def _load_purifier_data(self) -> dict[str, Any] | None:
        """Load linked P1 purifier data with a short cloud-poll cache."""
        if not _has_purifier_cloud_credentials(self.entry.data):
            return _previous_purifier_data(self.data)

        now = time.monotonic()
        if (
            self._purifier_loaded_at
            and now - self._purifier_loaded_at < PURIFIER_REFRESH_INTERVAL
        ):
            return self._purifier_data

        self._purifier_loaded_at = now
        purifier = _load_cloud_purifier(self.entry.data)
        if purifier is not None:
            public_data, credentials = purifier
            self._purifier_data = public_data
            self._purifier_credentials = credentials
        elif self._purifier_data is None:
            self._purifier_data = _previous_purifier_data(self.data)
        return self._purifier_data

    async def async_set_purifier_mode(self, mode: str) -> None:
        """Set the linked P1 mode."""
        if mode not in PURIFIER_MODE_VALUES:
            raise EufyMakeRuntimeError(f"Unsupported purifier mode: {mode}")
        delay = _purifier_delay(self._purifier_data)
        if mode != "Auto":
            delay = 0
        await self.hass.async_add_executor_job(
            self._send_purifier_command,
            PURIFIER_MODE_VALUES[mode],
            delay,
        )
        self._purifier_loaded_at = 0
        await self.async_request_refresh()

    async def async_set_purifier_delay(self, delay: int) -> None:
        """Set the linked P1 Auto delay-off seconds."""
        if delay not in PURIFIER_DELAY_VALUES:
            raise EufyMakeRuntimeError(f"Unsupported purifier delay: {delay}")
        await self.hass.async_add_executor_job(
            self._send_purifier_command,
            PURIFIER_MODE_VALUES["Auto"],
            delay,
        )
        self._purifier_loaded_at = 0
        await self.async_request_refresh()

    def _send_purifier_command(self, mode: int, delay: int) -> None:
        """Send a linked P1 MQTT command."""
        credentials = self._purifier_credentials
        if not credentials:
            loaded = _load_cloud_purifier(self.entry.data)
            if loaded is not None:
                public_data, credentials = loaded
                self._purifier_data = public_data
                self._purifier_credentials = credentials
        if not credentials:
            raise EufyMakeRuntimeError("Linked Purifier P1 is not available")

        data = self.entry.data
        EufyMakeMqttCommandClient(
            host=data[CONF_MQTT_HOST],
            station_sn=credentials["station_sn"],
            user_id=data[CONF_USER_ID],
            email=data[CONF_EMAIL],
            secret_key=credentials["secret_key"],
        ).send(
            {
                "commandType": PURIFIER_MODE_COMMAND,
                "mode": mode,
                "delay": delay,
            },
            expected_command_type=PURIFIER_MODE_COMMAND,
        )


def _data_from_live_result(
    ink_status: Any,
    *,
    decoded_messages: tuple[Any, ...] = (),
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

    accessory_status = find_accessory_status(decoded_messages)

    return {
        "availability": "online" if ink_status is not None else "unknown",
        "print_status": None,
        "firmware_version": firmware_version,
        "current_accessory": accessory_status.name,
        "current_accessory_details": {
            "attachment_type": accessory_status.attachment_type,
            "plate_type": accessory_status.plate_type,
            "version": accessory_status.version,
        },
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


def _preserve_previous_accessory(
    data: dict[str, Any],
    previous_data: dict[str, Any] | None,
) -> None:
    """Keep the last known accessory when a poll lacks accessory packets."""
    if data.get("current_accessory") is not None or not previous_data:
        return
    previous_accessory = previous_data.get("current_accessory")
    if previous_accessory is None:
        return
    data["current_accessory"] = previous_accessory
    previous_details = previous_data.get("current_accessory_details", {})
    data["current_accessory_details"] = (
        previous_details if isinstance(previous_details, dict) else {}
    )


def _load_cloud_purifier(
    entry_data: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]] | None:
    """Read the linked P1 accessory from the cloud device list."""
    required = (
        CONF_APP_DOMAIN,
        CONF_AUTH_TOKEN,
        CONF_COUNTRY,
        CONF_DEVICE_SN,
        CONF_USER_ID,
    )
    if any(not entry_data.get(key) for key in required):
        return None
    if _token_is_expired(entry_data.get(CONF_TOKEN_EXPIRES_AT)):
        raise ConfigEntryAuthFailed("eufyMake cloud token expired")

    try:
        from .auth import EufyMakeAuthError, _desktop_headers
        from .auth import _perform_key_exchange, _post_encrypted

        session_key = _perform_key_exchange(
            app_domain=entry_data[CONF_APP_DOMAIN],
            timeout=15,
        )

        response = _post_encrypted(
            app_domain=entry_data[CONF_APP_DOMAIN],
            path="/v1/app/query_fdm_list",
            body={},
            entry_id=session_key.entry_id,
            share_key_hex=session_key.share_key_hex,
            auth_token=entry_data[CONF_AUTH_TOKEN],
            user_id=entry_data[CONF_USER_ID],
            timeout=15,
            country=entry_data[CONF_COUNTRY],
            extra_headers=_desktop_headers(entry_data[CONF_COUNTRY]),
        )
    except EufyMakeAuthError as err:
        if _looks_like_cloud_auth_failure(str(err)):
            raise ConfigEntryAuthFailed("eufyMake cloud authentication failed") from err
        _LOGGER.debug("Unable to load linked purifier data: %s", err)
        return None
    except (ValueError, KeyError) as err:
        _LOGGER.debug("Unable to load linked purifier data: %s", err)
        return None

    if response.get("code") not in (0, 200):
        if _is_cloud_auth_failure_code(response.get("code")):
            raise ConfigEntryAuthFailed("eufyMake cloud authentication failed")
        _LOGGER.debug(
            "Unable to load linked purifier data: code=%s msg=%s",
            response.get("code"),
            response.get("msg"),
        )
        return None
    data = response.get("data")
    if not isinstance(data, list):
        return None

    e1 = next(
        (
            item
            for item in data
            if isinstance(item, dict)
            and str(item.get("station_sn") or "") == entry_data[CONF_DEVICE_SN]
        ),
        None,
    )
    if not isinstance(e1, dict):
        return None

    for accessory in e1.get("accessories") or ():
        if not isinstance(accessory, dict) or not _is_purifier_accessory(accessory):
            continue
        credentials = _purifier_credentials(accessory)
        if credentials is None:
            return None
        return _purifier_data(accessory), credentials
    return None


def _has_purifier_cloud_credentials(entry_data: dict[str, Any]) -> bool:
    """Return whether this config entry can poll the cloud device list."""
    required = (
        CONF_APP_DOMAIN,
        CONF_AUTH_TOKEN,
        CONF_COUNTRY,
        CONF_DEVICE_SN,
        CONF_USER_ID,
    )
    return not any(not entry_data.get(key) for key in required)


def _previous_purifier_data(
    previous_data: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return previous linked purifier data when available."""
    if not previous_data:
        return None
    previous = previous_data.get("purifier")
    return previous if isinstance(previous, dict) else None


def _token_is_expired(value: Any) -> bool:
    """Return whether a stored token expiry timestamp is already in the past."""
    expires_at = _optional_int(value)
    if expires_at is None:
        return False
    return expires_at <= int(time.time())


def _looks_like_cloud_auth_failure(message: str) -> bool:
    """Return whether a cloud exception should trigger reauthentication."""
    return "HTTP 401" in message or "HTTP 403" in message


def _is_cloud_auth_failure_code(code: Any) -> bool:
    """Return whether a cloud business code is an authentication failure."""
    return _optional_int(code) in {
        22008,
        26050,
        26051,
        26054,
        26055,
        26108,
    }


def _is_purifier_accessory(accessory: dict[str, Any]) -> bool:
    """Return whether a nested accessory record is the Purifier P1."""
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


def _purifier_data(accessory: dict[str, Any]) -> dict[str, Any]:
    """Build a public purifier state object from a cloud accessory record."""
    state = _purifier_state(accessory)
    return {
        "serial_number": _purifier_station_sn(accessory),
        "product_name": str(accessory.get("product_name") or "eufyMake Purifier P1"),
        "model": str(
            accessory.get("device_model")
            or accessory.get("device_name")
            or accessory.get("machine_name")
            or "T5216"
        ),
        "firmware_version": str(accessory.get("main_sw_version") or ""),
        "online": _optional_bool(accessory.get("mqtt_status")),
        "status": _optional_int(accessory.get("status")),
        "state": state,
    }


def _purifier_credentials(accessory: dict[str, Any]) -> dict[str, str] | None:
    """Return internal P1 MQTT credentials from a cloud accessory record."""
    station_sn = _purifier_station_sn(accessory)
    secret_key = str(accessory.get("secret_key") or "")
    if not station_sn or not secret_key:
        return None
    return {"station_sn": station_sn, "secret_key": secret_key}


def _purifier_delay(purifier: dict[str, Any] | None) -> int:
    """Return current P1 delay value or zero."""
    if not isinstance(purifier, dict):
        return 0
    state = purifier.get("state")
    if not isinstance(state, dict):
        return 0
    delay = _optional_int(state.get("delay"))
    return delay if delay in PURIFIER_DELAY_VALUES else 0


def _purifier_state(accessory: dict[str, Any]) -> dict[str, Any]:
    """Return decoded P1 param_type 10037 values."""
    for param in accessory.get("params") or ():
        if not isinstance(param, dict):
            continue
        if _optional_int(param.get("param_type")) != 10037:
            continue
        value = param.get("param_value")
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str) and value.strip().startswith("{"):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return parsed
    return {}


def _purifier_station_sn(accessory: dict[str, Any]) -> str:
    """Return the P1-owned station id when the cloud record includes both ids."""
    candidates = [
        str(accessory.get("station_sn") or ""),
        str(accessory.get("relate_sn") or ""),
    ]
    for candidate in candidates:
        if candidate.startswith("AS"):
            return candidate
    return next((candidate for candidate in candidates if candidate), "")


def _optional_bool(value: Any) -> bool | None:
    int_value = _optional_int(value)
    if int_value is None:
        return None
    return bool(int_value)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _date_from_timestamp(timestamp: int | None) -> str | None:
    """Convert a Unix timestamp to an ISO calendar date."""
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()
