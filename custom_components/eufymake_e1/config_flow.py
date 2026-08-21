"""Config flow for eufyMake E1."""

from __future__ import annotations

import base64
import binascii
from functools import partial
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_COUNTRY,
    CONF_DEVICE_SN,
    CONF_EMAIL,
    CONF_PASSWORD,
    DOMAIN,
)
from .countries import COUNTRY_OPTIONS

CONF_CAPTCHA_ANSWER = "captcha_answer"

_STEP_LOGIN_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_COUNTRY, default="NL"): SelectSelector(
            SelectSelectorConfig(
                options=COUNTRY_OPTIONS,
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(CONF_EMAIL): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.EMAIL,
                autocomplete="username",
            )
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.PASSWORD,
                autocomplete="current-password",
            )
        ),
    }
)

_STEP_CAPTCHA_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CAPTCHA_ANSWER): TextSelector(
            TextSelectorConfig(
                autocomplete="one-time-code",
            )
        ),
    }
)

class EufyMakeE1ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for eufyMake E1."""

    VERSION = 1
    _captcha_id: str | None = None
    _captcha_image: str | None = None
    _login_input: dict[str, Any] | None = None
    _login_result: Any | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle the initial step."""
        return await self.async_step_login(user_input)

    async def async_step_login(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle eufyMake account login."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                self._login_input = dict(user_input)
                result = await self.hass.async_add_executor_job(
                    partial(
                        _login,
                        country=user_input[CONF_COUNTRY],
                        email=user_input[CONF_EMAIL],
                        password=user_input[CONF_PASSWORD],
                    )
                )
            except _CaptchaChallenge as err:
                self._captcha_id = err.captcha_id
                self._captcha_image = err.image
                return await self.async_step_captcha()
            except ValueError as err:
                errors["base"] = str(err)
            else:
                return await self._async_finish_login_result(result)

        return self.async_show_form(
            step_id="login",
            data_schema=_STEP_LOGIN_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_captcha(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle eufyMake captcha verification."""
        if self._login_input is None or self._captcha_id is None:
            return await self.async_step_login()

        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                result = await self.hass.async_add_executor_job(
                    partial(
                        _login,
                        country=self._login_input[CONF_COUNTRY],
                        email=self._login_input[CONF_EMAIL],
                        password=self._login_input[CONF_PASSWORD],
                        captcha_id=self._captcha_id,
                        captcha_answer=user_input[CONF_CAPTCHA_ANSWER],
                    )
                )
            except _CaptchaChallenge as err:
                self._captcha_id = err.captcha_id
                self._captcha_image = err.image
                errors["base"] = "captcha_required"
            except ValueError as err:
                errors["base"] = str(err)
            else:
                self._captcha_id = None
                self._captcha_image = None
                self._login_input = None
                return await self._async_finish_login_result(result)

        return self.async_show_form(
            step_id="captcha",
            data_schema=_STEP_CAPTCHA_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"captcha_image": self._captcha_image or ""},
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Refresh login/session data for an existing config entry."""
        return await self.async_step_login(user_input)

    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle expired or rejected eufyMake cloud credentials."""
        return await self.async_step_login()

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

    async def _async_finish_login_result(self, result: Any) -> dict[str, Any]:
        """Finish a successful login according to the active flow source."""
        self._login_result = result
        if len(result.devices) == 1:
            return await self._async_create_entry_from_device(result.devices[0])
        return await self.async_step_device()

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
        if self.source == SOURCE_RECONFIGURE:
            return await self._async_update_existing_entry(
                self._get_reconfigure_entry(),
                data,
            )
        if self.source == SOURCE_REAUTH:
            return await self._async_update_existing_entry(
                self._get_reauth_entry(),
                data,
            )
        return await self._async_create_entry(data)

    async def _async_create_entry(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create the Home Assistant config entry."""
        await self.async_set_unique_id(data[CONF_DEVICE_SN])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"eufyMake E1 {data[CONF_DEVICE_SN][-4:]}",
            data=data,
        )

    async def _async_update_existing_entry(
        self,
        entry: config_entries.ConfigEntry,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update and reload an existing config entry."""
        await self.async_set_unique_id(data[CONF_DEVICE_SN])
        self._abort_if_unique_id_mismatch()
        return self.async_update_reload_and_abort(
            entry,
            data_updates=data,
        )


class _CaptchaChallenge(ValueError):
    """Captcha challenge to be rendered by the config flow."""

    def __init__(self, *, captcha_id: str, image: str) -> None:
        """Initialize captcha challenge details."""
        super().__init__("captcha_required")
        self.captcha_id = captcha_id
        self.image = image


def _login(
    *,
    country: str,
    email: str,
    password: str,
    captcha_id: str | None = None,
    captcha_answer: str | None = None,
) -> Any:
    """Run eufyMake cloud login without importing auth at module import time."""
    from .auth import EufyMakeApiCodeError, EufyMakeAuthError, EufyMakeCaptchaRequired
    from .auth import EufyMakeCloudAuthClient
    from .auth import region_from_country

    try:
        country_code = country.strip().upper()
        return EufyMakeCloudAuthClient(
            region=region_from_country(country_code),
            country=country_code,
        ).login(
            email=email,
            password=password,
            captcha_id=captcha_id,
            captcha_answer=captcha_answer,
        )
    except EufyMakeCaptchaRequired as err:
        image = _captcha_image_uri(err.item)
        if err.captcha_id and image:
            raise _CaptchaChallenge(captcha_id=err.captcha_id, image=image) from err
        raise ValueError("captcha_required") from err
    except EufyMakeApiCodeError as err:
        if err.code in (26050, 26051, 26054, 26055, 26108, 22008):
            raise ValueError("invalid_auth") from err
        if err.code in (26052, 26105):
            raise ValueError("verification_required") from err
        if err.code in (100032, 100033):
            raise ValueError("captcha_required") from err
        if err.code in (10019, 100028, 100056, 250999):
            raise ValueError("rate_limited") from err
        raise ValueError("cannot_connect") from err
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


def _captcha_image_uri(item: str) -> str:
    """Convert eufyMake captcha image data into a URI HA can render."""
    value = item.strip()
    if value.startswith(("https://", "http://", "data:image/")):
        return value
    if value.startswith("<svg"):
        encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
        return f"data:image/svg+xml;base64,{encoded}"
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return ""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        mime_type = "image/png"
    elif raw.startswith(b"\xff\xd8\xff"):
        mime_type = "image/jpeg"
    elif raw.startswith(b"GIF8"):
        mime_type = "image/gif"
    elif raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        mime_type = "image/webp"
    else:
        mime_type = "image/png"
    return f"data:{mime_type};base64,{value}"
