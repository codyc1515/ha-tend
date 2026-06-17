"""Constants for the Tend integration."""

from datetime import timedelta

DOMAIN = "tend"

CONF_REFRESH_TOKEN = "refresh_token"
CONF_ID_TOKEN = "id_token"
CONF_ACCESS_TOKEN = "access_token"
CONF_EXPIRES_AT = "expires_at"

API_BASE_URL = "https://api.tend.nz"
COGNITO_URL = "https://cognito-idp.us-west-2.amazonaws.com/"
COGNITO_CLIENT_ID = "5v0ojtrl56n3auak7iibmfbmsb"

API_VERSION = "1494"
APP_VERSION = "2026.11.0"
APP_BUILD = "1494"

SCAN_INTERVAL = timedelta(hours=6)
PLATFORMS = ["calendar"]
