"""Coordinate Tend updates and appointment search polling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import APPOINTMENT_SEARCH_INTERVAL, SCAN_INTERVAL


@dataclass
class TendData:
    """Booked appointments and optional bookable appointment availability."""

    appointments: list[dict[str, Any]]
    availability: dict[str, Any] | None = None


class TendDataUpdateCoordinator(DataUpdateCoordinator[TendData]):
    """Update appointments more frequently while searching is enabled."""

    look_for_new_appointments = False

    async def async_set_appointment_search(self, enabled: bool) -> None:
        """Change search mode and immediately apply the polling interval."""
        if self.look_for_new_appointments == enabled:
            return
        self.look_for_new_appointments = enabled
        if self.data is not None:
            self.data.availability = None
        self.update_interval = (
            APPOINTMENT_SEARCH_INTERVAL if enabled else SCAN_INTERVAL
        )
        self._schedule_refresh()
        self.async_update_listeners()
        if enabled:
            await self.async_request_refresh()
