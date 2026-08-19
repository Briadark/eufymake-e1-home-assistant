"""Config flow for eufyMake E1."""

from __future__ import annotations

import json
from functools import partial
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    CONF_DEVICE_SN,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REGION,
    CONF_SETUP_EXPORT,
    DOMAIN,
    REGION_EU,
    REGION_OPTIONS,
)

_STEP_LOGIN_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION, default=REGION_EU): vol.In(REGION_OPTIONS),
        vol.Required(CONF_EMAIL): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
        ),
        vol.Required(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)

_STEP_SETUP_EXPORT_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SETUP_EXPORT): vol.All(
            str,
            vol.Length(min=1),
        ),
    }
)


class EufyMakeE1ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for eufyMake E1."""

    VERSION = 1
    _login_result: Any | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle the initial step."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["login", "setup_export"],
        )

    async def async_step_login(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle eufyMake account login."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                result = await self.hass.async_add_executor_job(
                    partial(
                        _login,
                        region=user_input[CONF_REGION],
                        email=user_input[CONF_EMAIL],
                        password=user_input[CONF_PASSWORD],
                    )
                )
            except ValueError as err:
                errors["base"] = str(err)
            else:
                self._login_result = result
                if len(result.devices) == 1:
                    return await self._async_create_entry_from_device(
                        result.devices[0]
                    )
                return await self.async_step_device()

        return self.async_show_form(
            step_id="login",
            data_schema=_STEP_LOGIN_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_setup_export(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle setup from a pasted setup export."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                data = _parse_setup_export(user_input[CONF_SETUP_EXPORT])
            except ValueError:
                errors["base"] = "invalid_setup_export"
            else:
                return await self._async_create_entry(data)

        return self.async_show_form(
            step_id="setup_export",
            data_schema=_STEP_SETUP_EXPORT_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Select an E1 device when the account has more than one."""
        if self._login_result is None:
            return await self.async_step_login()

        if user_input is not None:
            serial_number = user_input[CONF_DEVICE_SN]
            for device in self._login_result.devices:
                if str(device.get("station_sn") or "") == serial_number:
                    return await self._async_create_entry_from_device(device)
            return self.async_abort(reason="device_not_found")

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_SN): vol.In(
                        {
                            str(device.get("station_sn") or ""): _device_label(device)
                            for device in self._login_result.devices
                        }
                    )
                }
            ),
        )

    async def _async_create_entry_from_device(
        self,
        device: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a config entry for one logged-in E1 device."""
        from .auth import build_setup_from_login_device

        if self._login_result is None:
            return self.async_abort(reason="login_required")
        try:
            data = build_setup_from_login_device(self._login_result.session, device)
        except Exception:
            return self.async_abort(reason="invalid_device")
        return await self._async_create_entry(data)

    async def _async_create_entry(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create the Home Assistant config entry."""
        await self.async_set_unique_id(data[CONF_DEVICE_SN])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"eufyMake E1 {data[CONF_DEVICE_SN][-4:]}",
            data=data,
        )


def _login(*, region: str, email: str, password: str) -> Any:
    """Run eufyMake cloud login without importing auth at module import time."""
    from .auth import EufyMakeAuthError, EufyMakeCloudAuthClient

    try:
        return EufyMakeCloudAuthClient(region=region).login(
            email=email,
            password=password,
        )
    except EufyMakeAuthError as err:
        message = str(err)
        if "code=100006" in message or "password" in message.lower():
            raise ValueError("invalid_auth") from err
        raise ValueError("cannot_connect") from err


def _device_label(device: dict[str, Any]) -> str:
    """Return a short, recognizable device label."""
    product_name = str(device.get("product_name") or "eufyMake E1")
    serial_number = str(device.get("station_sn") or "")
    suffix = serial_number[-4:] if len(serial_number) >= 4 else serial_number
    firmware = device.get("main_sw_version")
    if firmware:
        return f"{product_name} {suffix} ({firmware})"
    return f"{product_name} {suffix}"


def _parse_setup_export(value: str) -> dict[str, Any]:
    """Parse the setup export without importing the discovery library."""
    try:
        data = json.loads(value)
    except json.JSONDecodeError as err:
        raise ValueError("Setup export is not valid JSON") from err

    if not isinstance(data, dict):
        raise ValueError("Setup export must be an object")
    if data.get("version", 1) != 1:
        raise ValueError("Unsupported setup export version")

    for key in ("device_sn", "user_id", "email", "secret_key", "mqtt_host"):
        if not data.get(key):
            raise ValueError(f"Setup export is missing {key}")
    if str(data.get("station_model", "V8260")) != "V8260":
        raise ValueError("Setup export is not for a eufyMake E1")

    parsed = {
        "region": str(data.get("region") or _region_from_host(data["mqtt_host"])),
        "device_sn": str(data["device_sn"]),
        "user_id": str(data["user_id"]),
        "email": str(data["email"]),
        "secret_key": str(data["secret_key"]),
        "mqtt_host": str(data["mqtt_host"]),
    }
    if data.get("firmware_version"):
        parsed["firmware_version"] = str(data["firmware_version"])
    return parsed


def _region_from_host(host: str) -> str:
    """Infer the region name from the broker host."""
    return "eu" if "-eu." in host else "us"
