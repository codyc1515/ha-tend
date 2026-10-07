"""Sensors for bookable Tend appointments."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import TendDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up both Tend availability sensors."""
    async_add_entities(
        [
            TendOnlineNowSensor(entry.runtime_data, entry),
            TendNextAppointmentSensor(entry.runtime_data, entry),
        ]
    )


class TendAvailabilitySensor(CoordinatorEntity[TendDataUpdateCoordinator], SensorEntity):
    """Base entity for availability fetched while appointment search is on."""

    _attr_has_entity_name = True
    maintenance_key: str

    def __init__(
        self, coordinator: TendDataUpdateCoordinator, entry: ConfigEntry, key: str
    ) -> None:
        """Initialize a sensor on the account's existing Tend device."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, entry.unique_id or entry.data[CONF_EMAIL])},
            manufacturer="Tend",
            name=entry.title,
        )

    @property
    def availability_data(self) -> dict[str, Any]:
        """Return availability only while searches are enabled."""
        if not self.coordinator.look_for_new_appointments or not self.coordinator.data:
            return {}
        return self.coordinator.data.availability or {}

    @property
    def available(self) -> bool:
        """Disable readings while searches are off or booking is under maintenance."""
        data = self.availability_data
        maintenance = (data.get("maintenanceStatuses") or {}).get(
            self.maintenance_key
        ) or {}
        return (
            super().available
            and self.coordinator.look_for_new_appointments
            and bool(data)
            and not maintenance.get("isUnderMaintenance", False)
        )


class TendOnlineNowSensor(TendAvailabilitySensor):
    """The API's estimated Online Now appointment time."""

    _attr_name = "Online Now wait time"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:timer-outline"
    maintenance_key = "onlineNow"

    def __init__(
        self, coordinator: TendDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the Online Now sensor."""
        super().__init__(coordinator, entry, "online_now_wait_time")

    @property
    def native_value(self) -> datetime | None:
        """Return the estimated slot time for Home Assistant to display locally."""
        queue = self.availability_data.get("onlineNowQueue") or {}
        wait = queue.get("waitTime") or {}
        slot = wait.get("estimatedAppointmentSlot") or {}
        start = slot.get("startTime")
        if not isinstance(start, str):
            return None
        parsed = dt_util.parse_datetime(start)
        if parsed is None or parsed.tzinfo is None:
            return None
        return parsed


class TendNextAppointmentSensor(TendAvailabilitySensor):
    """The next bookable scheduled appointment shown on the Tend home screen."""

    _attr_name = "Next available appointment"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-clock"
    maintenance_key = "standardBooking"

    def __init__(
        self, coordinator: TendDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the scheduled appointment sensor."""
        super().__init__(coordinator, entry, "next_available_appointment")

    @property
    def native_value(self) -> datetime | None:
        """Return a timezone-aware timestamp for Home Assistant to display locally."""
        slot = self.availability_data.get("nextAppointmentSlot") or {}
        start = slot.get("startTime")
        if not isinstance(start, str):
            return None
        parsed = dt_util.parse_datetime(start)
        if parsed is None or parsed.tzinfo is None:
            return None
        return parsed
