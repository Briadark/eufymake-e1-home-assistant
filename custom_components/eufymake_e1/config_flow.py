"""Config flow for eufyMake E1."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_DEVICE_SN,
    CONF_SETUP_EXPORT,
    DOMAIN,
)
from .pyeufymake.setup_export import (
    EufyMakeSetupExportError,
    parse_setup_export,
)


class EufyMakeE1ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for eufyMake E1."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                data = parse_setup_export(user_input[CONF_SETUP_EXPORT])
            except EufyMakeSetupExportError:
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
