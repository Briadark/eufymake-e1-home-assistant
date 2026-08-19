"""Config flow for eufyMake E1."""

from __future__ import annotations

import json
from typing import Any

import voluptuous as vol

from homeassistant import config_entries

from .const import (
    CONF_DEVICE_SN,
    CONF_SETUP_EXPORT,
    DOMAIN,
)


class EufyMakeE1ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for eufyMake E1."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                data = _parse_setup_export(user_input[CONF_SETUP_EXPORT])
            except ValueError:
                errors["base"] = "invalid_setup_export"
            else:
                await self.async_set_unique_id(data[CONF_DEVICE_SN])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"eufyMake E1 {data[CONF_DEVICE_SN][-4:]}",
                    data=data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SETUP_EXPORT): vol.All(
                        str,
                        vol.Length(min=1),
                    ),
                }
            ),
            errors=errors,
        )


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
