"""The Tend integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TendApiClient, TendApiError, TendAuthError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EXPIRES_AT,
    CONF_ID_TOKEN,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    PLATFORMS,
    SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tend from a config entry."""
    session = async_get_clientsession(hass)
    client = TendApiClient(
        session,
        email=entry.data[CONF_EMAIL],
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        id_token=entry.data.get(CONF_ID_TOKEN),
        access_token=entry.data.get(CONF_ACCESS_TOKEN),
        expires_at=entry.data.get(CONF_EXPIRES_AT, 0),
        token_update_callback=lambda tokens: hass.config_entries.async_update_entry(
            entry, data={**entry.data, **tokens}
        ),
    )

    async def async_update_data() -> list:
        try:
            return await client.async_get_upcoming_appointments()
        except TendAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except TendApiError as err:
            raise UpdateFailed(str(err)) from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=SCAN_INTERVAL,
        always_update=False,
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        raise
    except Exception as err:
        raise ConfigEntryNotReady("Unable to connect to Tend") from err

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
