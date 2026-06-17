"""Calendar platform for Tend."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.util import dt as dt_util

DEFAULT_APPOINTMENT_LENGTH = timedelta(minutes=15)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tend calendar entities."""
    async_add_entities([TendCalendarEntity(entry.runtime_data, entry)])


class TendCalendarEntity(CoordinatorEntity[DataUpdateCoordinator], CalendarEntity):
    """A unified calendar of upcoming Tend appointments."""

    _attr_has_entity_name = True
    _attr_name = "Appointments"

    def __init__(self, coordinator: DataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the calendar entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_appointments"

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        now = dt_util.now()
        events = [
            event
            for event in _appointments_to_events(self.coordinator.data or [])
            if event.end > now
        ]
        if not events:
            return None
        return min(events, key=lambda event: event.start)

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        return [
            event
            for event in _appointments_to_events(self.coordinator.data or [])
            if event.end > start_date and event.start < end_date
        ]


def _appointments_to_events(appointments: list[dict[str, Any]]) -> list[CalendarEvent]:
    """Convert Tend appointments into Home Assistant calendar events."""
    events = [_appointment_to_event(item) for item in appointments]
    return sorted(events, key=lambda event: event.start)


def _appointment_to_event(item: dict[str, Any]) -> CalendarEvent:
    """Convert a Tend appointment dict into a calendar event."""
    start = dt_util.parse_datetime(item["startTime"])
    if start is None:
        raise ValueError(f"Invalid Tend start time: {item['startTime']}")
    if start.tzinfo is None:
        start = dt_util.as_utc(start)
    else:
        start = dt_util.as_local(start)

    end = None
    if item.get("endTime"):
        end = dt_util.parse_datetime(item["endTime"])
    elif item.get("expectedEndTime"):
        end = dt_util.parse_datetime(item["expectedEndTime"])
    if end is None and item.get("duration"):
        end = start + timedelta(minutes=int(item["duration"]))
    if end is None:
        end = start + DEFAULT_APPOINTMENT_LENGTH
    elif end.tzinfo is None:
        end = dt_util.as_utc(end)
    else:
        end = dt_util.as_local(end)

    kind = item.get("kind")
    appointment_type = _title_case(item.get("type"))
    service = (item.get("service") or {}).get("name")
    queue = item.get("appointmentQueue") or {}
    queue_name = queue.get("name") or _title_case(queue.get("shortCode"))
    summary_parts = ["Tend"]
    if kind == "queue":
        summary_parts.append(queue_name or "Queue")
    elif service:
        summary_parts.append(service)
    elif appointment_type:
        summary_parts.append(appointment_type)
    else:
        summary_parts.append("Appointment")

    person = _person_name(item.get("dependant") or item.get("patient"))
    if person:
        summary_parts.append(f"for {person}")

    location = _location_name(item)
    description_parts = [
        part
        for part in [
            f"Status: {_title_case(item.get('status'))}" if item.get("status") else None,
            f"Type: {appointment_type}" if appointment_type else None,
            f"Clinician: {_clinicians(item.get('clinicians'))}"
            if item.get("clinicians")
            else None,
            f"Health concern: {_health_concerns(item.get('healthConcerns'))}"
            if item.get("healthConcerns")
            else None,
        ]
        if part
    ]

    return CalendarEvent(
        start=start,
        end=end,
        summary=" ".join(summary_parts),
        location=location,
        description="\n".join(description_parts) or None,
        uid=item.get("uid"),
    )


def _title_case(value: str | None) -> str | None:
    """Return a readable title-cased API enum."""
    if not value:
        return None
    return value.replace("_", " ").replace("-", " ").title()


def _person_name(person: dict[str, Any] | None) -> str | None:
    """Return a readable patient/dependant name."""
    if not person:
        return None
    given = person.get("preferredGivenName") or person.get("givenName")
    family = person.get("familyName")
    return " ".join(part for part in [given, family] if part) or None


def _location_name(item: dict[str, Any]) -> str | None:
    """Return a Tend location name."""
    location = item.get("location") or {}
    return location.get("displayName") or location.get("name")


def _clinicians(clinicians: list[dict[str, Any]]) -> str:
    """Return clinician names for a description."""
    names = []
    for clinician in clinicians:
        prefix = (clinician.get("prefix") or {}).get("short")
        name = " ".join(
            part
            for part in [prefix, clinician.get("givenName"), clinician.get("familyName")]
            if part
        )
        names.append(name or _title_case(clinician.get("type")) or "Clinician")
    return ", ".join(names)


def _health_concerns(health_concerns: list[dict[str, Any]]) -> str:
    """Return health concern labels for a description."""
    labels = []
    for concern in health_concerns:
        health_concern = concern.get("healthConcern") or {}
        labels.append(health_concern.get("appDisplayName") or health_concern.get("name"))
    return ", ".join(label for label in labels if label)
