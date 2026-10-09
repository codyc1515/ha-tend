# Tend custom integration for Home Assistant

This custom integration logs in to Tend and exposes one unified `calendar.tend_appointments` calendar.

The **Look for new appointments** switch is off when the integration starts. Turning
it on refreshes appointment data immediately and then every five minutes. Turning
it off restores the usual six-hour refresh interval and stops fetching availability.

While the switch is on, two sensors show the availability from the Tend home screen:

- **Online Now**: estimated appointment time as a timestamp, allowing
  Home Assistant to display the wait as a relative time.
- **Next available**: the next bookable scheduled slot as a timestamp,
  displayed in Home Assistant's configured timezone.

Both sensors are hidden while the switch is off and shown again when it is on.
Sensors you manually hide stay hidden. Existing entity IDs remain unchanged.
Home Assistant's hidden setting excludes sensors from automatically generated
dashboards; explicitly configured cards need a visibility condition on the search
switch to hide them too. No available slot or wait
estimate produces an unknown value; maintenance makes the affected sensor unavailable.

## Install

1. Copy `custom_components/tend` into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings > Devices & services > Add integration** and search for **Tend**.
4. Enter your Tend email address, then enter the login code Tend sends you.
