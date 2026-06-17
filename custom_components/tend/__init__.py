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


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old Tend config entries."""
    email = entry.data[CONF_EMAIL].strip().lower()
    data_updates = {}
    if entry.data[CONF_EMAIL] != email:
        data_updates[CONF_EMAIL] = email

    duplicate_entries = [
        current_entry
        for current_entry in hass.config_entries.async_entries(DOMAIN)
        if current_entry.entry_id != entry.entry_id
        and current_entry.data.get(CONF_EMAIL, "").strip().lower() == email
    ]
    unique_id = entry.unique_id
    if not duplicate_entries and (unique_id is None or unique_id.lower() == email):
        unique_id = email
    elif duplicate_entries:
        _LOGGER.warning(
            "Multiple Tend config entries exist for %s; remove duplicate entries to "
            "keep one Tend instance per account",
            email,
        )

    if entry.unique_id != unique_id or data_updates:
        updates = {"data": {**entry.data, **data_updates}}
        if entry.unique_id != unique_id:
            updates["unique_id"] = unique_id
        hass.config_entries.async_update_entry(entry, **updates)

    return True


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
