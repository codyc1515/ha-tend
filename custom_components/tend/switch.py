"""Switch platform for Tend appointment searches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TendDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tend search toggle."""
    async_add_entities([TendAppointmentSearchSwitch(entry.runtime_data, entry)])


class TendAppointmentSearchSwitch(
    CoordinatorEntity[TendDataUpdateCoordinator], SwitchEntity
):
    """Control whether Tend polls every five minutes."""

    _attr_has_entity_name = True
    _attr_name = "Look for new appointments"
    _attr_icon = "mdi:calendar-search"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: TendDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the search switch, off on each integration setup."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_look_for_new_appointments"
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, entry.unique_id or entry.data[CONF_EMAIL])},
            manufacturer="Tend",
            name=entry.title,
        )

    @property
    def available(self) -> bool:
        """Allow searches to be stopped even if the last API update failed."""
        return True

    @property
    def is_on(self) -> bool:
        """Return whether frequent appointment searches are enabled."""
        return self.coordinator.look_for_new_appointments

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable frequent updates and request fresh appointment data."""
        await self.coordinator.async_set_appointment_search(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Return to the normal refresh interval."""
        await self.coordinator.async_set_appointment_search(False)
