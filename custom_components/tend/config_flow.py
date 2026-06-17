"""Config flow for Tend."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_NAME
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TendApiClient, TendApiError, TendAuthError, TendLoginChallenge
from .const import DOMAIN

CONF_CODE = "code"
_LOGGER = logging.getLogger(__name__)


class TendConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tend."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._email: str | None = None
        self._challenge: TendLoginChallenge | None = None
        self._tokens: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect email and start Tend's code login."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._email = user_input[CONF_EMAIL].strip().lower()
            await self.async_set_unique_id(self._email)
            self._abort_if_unique_id_configured()
            self._abort_if_email_configured(self._email)

            client = TendApiClient(async_get_clientsession(self.hass), email=self._email)
            try:
                self._challenge = await client.async_start_login()
            except TendAuthError as err:
                _LOGGER.warning("Tend login challenge failed: %s", err)
                errors["base"] = "auth"
            except TendApiError:
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_code()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_EMAIL): str}),
            errors=errors,
        )

    async def async_step_code(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect the emailed Tend login code."""
        errors: dict[str, str] = {}

        if user_input is not None and self._email and self._challenge:
            client = TendApiClient(
                async_get_clientsession(self.hass),
                email=self._email,
                token_update_callback=self._tokens.update,
            )
            try:
                await client.async_finish_login(self._challenge, user_input[CONF_CODE])
                await client.async_validate_auth()
            except TendAuthError:
                errors["base"] = "invalid_code"
            except TendApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or "Tend",
                    data={CONF_EMAIL: self._email, **self._tokens},
                )

        return self.async_show_form(
            step_id="code",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CODE): str,
                    vol.Optional(CONF_NAME, default="Tend"): str,
                }
            ),
            errors=errors,
            description_placeholders={"email": self._email or ""},
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Handle reauthentication."""
        self._email = entry_data[CONF_EMAIL].strip().lower()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Start a new login challenge during reauthentication."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")

        client = TendApiClient(async_get_clientsession(self.hass), email=self._email or "")
        try:
            self._challenge = await client.async_start_login()
        except TendAuthError as err:
            _LOGGER.warning("Tend reauth challenge failed: %s", err)
            return self.async_show_form(
                step_id="reauth_confirm", errors={"base": "auth"}
            )
        except TendApiError:
            return self.async_show_form(
                step_id="reauth_confirm", errors={"base": "cannot_connect"}
            )
        return await self.async_step_reauth_code()

    async def async_step_reauth_code(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Finish reauthentication."""
        errors: dict[str, str] = {}

        if user_input is not None and self._email and self._challenge:
            client = TendApiClient(
                async_get_clientsession(self.hass),
                email=self._email,
                token_update_callback=self._tokens.update,
            )
            try:
                await client.async_finish_login(self._challenge, user_input[CONF_CODE])
                await client.async_validate_auth()
            except TendAuthError:
                errors["base"] = "invalid_code"
            except TendApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={CONF_EMAIL: self._email, **self._tokens},
                )

        return self.async_show_form(
            step_id="reauth_code",
            data_schema=vol.Schema({vol.Required(CONF_CODE): str}),
            errors=errors,
            description_placeholders={"email": self._email or ""},
        )

    def _abort_if_email_configured(self, email: str) -> None:
        """Abort if a Tend entry already exists for this email address."""
        for entry in self._async_current_entries():
            if entry.data.get(CONF_EMAIL, "").strip().lower() == email:
                raise AbortFlow("already_configured")
