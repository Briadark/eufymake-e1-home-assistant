"""The eufyMake E1 integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_AUTH_TOKEN, DOMAIN

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up eufyMake E1 from a config entry."""
    from .coordinator import EufyMakeE1Coordinator

    _async_start_cloud_auth_reauth_if_needed(hass, entry)

    coordinator = EufyMakeE1Coordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


def _async_start_cloud_auth_reauth_if_needed(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Start Home Assistant's normal reauth flow for legacy config entries."""
    if not entry.data.get(CONF_AUTH_TOKEN):
        entry.async_start_reauth(hass)
