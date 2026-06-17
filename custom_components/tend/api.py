"""Client for the Tend app API."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from aiohttp import ClientError, ClientSession

from .const import (
    API_BASE_URL,
    API_VERSION,
    APP_BUILD,
    COGNITO_CLIENT_ID,
    COGNITO_URL,
    CONF_ACCESS_TOKEN,
    CONF_EXPIRES_AT,
    CONF_ID_TOKEN,
    CONF_REFRESH_TOKEN,
)

GRAPHQL_URL = f"{API_BASE_URL}/patients/graphql"
_LOGGER = logging.getLogger(__name__)

APPOINTMENTS_QUERY = """
query AppointmentsScreenQuery($bookingFilter: AppointmentSearchInput!, $pastBookingFilter: AppointmentSearchInput!, $queueFilter: AppointmentQueueItemSearchInput!, $langInput: String!) {
  account {
    id
    futureAppointments: bundledAppointments(input: $bookingFilter) {
      id
      main {
        id
        startTime
        endTime
        expectedEndTime
        type
        status
        location {
          displayName
          name
        }
        patient {
          givenName
          familyName
          preferredGivenName
        }
        dependant {
          givenName
          familyName
          preferredGivenName
        }
        clinicians {
          type
          givenName
          familyName
          prefix {
            short
          }
        }
        healthConcerns {
          healthConcern {
            name
            appDisplayName(lang: $langInput)
          }
        }
        service {
          name
        }
      }
      bundled {
        id
        startTime
        endTime
        expectedEndTime
        type
        status
        location {
          displayName
          name
        }
        patient {
          givenName
          familyName
          preferredGivenName
        }
        dependant {
          givenName
          familyName
          preferredGivenName
        }
        clinicians {
          type
          givenName
          familyName
          prefix {
            short
          }
        }
        healthConcerns {
          healthConcern {
            name
            appDisplayName(lang: $langInput)
          }
        }
        service {
          name
        }
      }
    }
    appointmentQueueItems(input: $queueFilter) {
      id
      status
      appointmentQueue {
        shortCode
        name
      }
      appointment {
        id
        status
        startTime
        endTime
        expectedEndTime
        type
      }
      patient {
        givenName
        familyName
        preferredGivenName
      }
      dependant {
        givenName
        familyName
        preferredGivenName
      }
      healthConcerns {
        healthConcern {
          name
          appDisplayName(lang: $langInput)
        }
      }
      waitTime {
        waitWindowStart
        waitWindowEnd
        estimatedAppointmentSlot {
          id
          startTime
          duration
        }
      }
    }
    pastAppointments: bundledAppointments(input: $pastBookingFilter) {
      id
    }
  }
}
"""


class TendApiError(Exception):
    """Raised when the Tend API returns an error."""


class TendAuthError(TendApiError):
    """Raised when Tend authentication fails."""


@dataclass(slots=True)
class TendLoginChallenge:
    """Cognito login challenge details returned after Tend sends a code."""

    session: str
    challenge_name: str
    username: str | None = None


class TendApiClient:
    """Small async API client for Tend."""

    def __init__(
        self,
        session: ClientSession,
        *,
        email: str,
        refresh_token: str | None = None,
        id_token: str | None = None,
        access_token: str | None = None,
        expires_at: float = 0,
        token_update_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self.email = email
        self.refresh_token = refresh_token
        self.id_token = id_token
        self.access_token = access_token
        self.expires_at = expires_at
        self._token_update_callback = token_update_callback

    async def async_start_login(self) -> TendLoginChallenge:
        """Start the Tend code login flow and return the Cognito challenge."""
        response = await self._cognito(
            "AWSCognitoIdentityProviderService.InitiateAuth",
            {
                "AuthFlow": "CUSTOM_AUTH",
                "ClientId": COGNITO_CLIENT_ID,
                "AuthParameters": {"USERNAME": self.email},
            },
        )
        if response.get("AuthenticationResult"):
            self._store_authentication_result(response)
            raise TendAuthError("Tend returned tokens before a code was entered")

        challenge_name = response.get("ChallengeName")
        session = response.get("Session")
        if not challenge_name or not session:
            _LOGGER.warning(
                "Tend login response did not include a usable challenge: %s",
                _safe_cognito_debug(response),
            )
            raise TendAuthError(
                "Tend did not return a login session "
                f"({response.get('ChallengeName') or response.get('__type') or 'unknown'})"
            )
        challenge_parameters = response.get("ChallengeParameters") or {}
        username = (
            challenge_parameters.get("USERNAME")
            or challenge_parameters.get("USER_ID_FOR_SRP")
            or self.email
        )
        return TendLoginChallenge(
            session=session,
            challenge_name=challenge_name,
            username=username,
        )

    async def async_finish_login(
        self, challenge: TendLoginChallenge, code: str
    ) -> None:
        """Finish the Tend code login flow."""
        challenge_responses = {
            "USERNAME": _challenge_username(challenge, self.email),
            _challenge_code_key(challenge.challenge_name): code.strip(),
        }
        response = await self._cognito(
            "AWSCognitoIdentityProviderService.RespondToAuthChallenge",
            {
                "ClientId": COGNITO_CLIENT_ID,
                "Session": challenge.session,
                "ChallengeName": challenge.challenge_name,
                "ChallengeResponses": challenge_responses,
            },
        )
        self._store_authentication_result(response)

    async def async_refresh_tokens(self) -> None:
        """Refresh Cognito tokens using the stored refresh token."""
        if not self.refresh_token:
            raise TendAuthError("No Tend refresh token is available")

        response = await self._cognito(
            "AWSCognitoIdentityProviderService.InitiateAuth",
            {
                "AuthFlow": "REFRESH_TOKEN_AUTH",
                "ClientId": COGNITO_CLIENT_ID,
                "AuthParameters": {"REFRESH_TOKEN": self.refresh_token},
            },
        )
        self._store_authentication_result(response, keep_existing_refresh_token=True)

    async def async_get_upcoming_appointments(self) -> list[dict[str, Any]]:
        """Return all upcoming Tend appointments and queue items."""
        await self._ensure_valid_token()
        response = await self._graphql(
            {
                "operationName": "AppointmentsScreenQuery",
                "variables": {
                    "bookingFilter": {
                        "timeframe": "UPCOMING",
                        "includeQueueAppointments": False,
                    },
                    "queueFilter": {
                        "timeframe": "UPCOMING",
                        "includeAllocatedAppointments": True,
                    },
                    "pastBookingFilter": {
                        "includeQueueAppointments": True,
                        "timeframe": "PAST_COMPLETED",
                    },
                    "langInput": "en_NZ",
                },
                "query": APPOINTMENTS_QUERY,
            }
        )
        account = response.get("data", {}).get("account") or {}
        return _normalise_appointments(account)

    async def async_validate_auth(self) -> None:
        """Validate the current credentials by fetching appointments."""
        await self.async_get_upcoming_appointments()

    async def _ensure_valid_token(self) -> None:
        """Refresh tokens when the current id token is close to expiry."""
        now = datetime.now(UTC).timestamp()
        if self.id_token and self.expires_at - now > 300:
            return
        await self.async_refresh_tokens()

    async def _cognito(self, target: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Call AWS Cognito."""
        try:
            response = await self._session.post(
                COGNITO_URL,
                headers={
                    "Content-Type": "application/x-amz-json-1.1",
                    "x-amz-target": target,
                    "Accept": "*/*",
                    "User-Agent": f"Tend/{APP_BUILD}",
                },
                json=payload,
                timeout=30,
            )
            data = await response.json(content_type=None)
            if response.status < 400:
                return data
            if isinstance(data, dict) and data.get("ChallengeName") and data.get("Session"):
                _LOGGER.warning(
                    "Tend Cognito returned HTTP %s with a usable challenge: %s",
                    response.status,
                    _safe_cognito_debug(data),
                )
                return data
            _LOGGER.warning(
                "Tend Cognito request failed with HTTP %s: %s",
                response.status,
                _safe_cognito_debug(data),
            )
            raise TendAuthError(
                "Tend authentication failed "
                f"({response.status}: {_cognito_error_message(data)})"
            )
        except (ClientError, TimeoutError) as err:
            raise TendApiError("Unable to reach Tend authentication service") from err

    async def _graphql(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Call the Tend GraphQL API."""
        if not self.id_token:
            raise TendAuthError("No Tend id token is available")

        try:
            response = await self._session.post(
                GRAPHQL_URL,
                headers={
                    "Accept": f"application/vnd.tend.api+json;version={API_VERSION}",
                    "Authorization": f"Bearer {self.id_token}",
                    "Content-Type": "application/json",
                    "User-Agent": f"Tend/{APP_BUILD}",
                    "x-tend-platform": "IOS",
                },
                json=payload,
                timeout=30,
            )
            if response.status in (401, 403):
                response.release()
                raise TendAuthError("Tend rejected the current token")
            if response.status >= 400:
                raise TendApiError(f"Tend API request failed: {response.status}")
            data = await response.json()
        except TendAuthError:
            raise
        except (ClientError, TimeoutError) as err:
            raise TendApiError("Unable to reach Tend API") from err

        if errors := data.get("errors"):
            raise TendApiError(f"Tend GraphQL returned errors: {errors}")
        return data

    def _store_authentication_result(
        self,
        response: dict[str, Any],
        *,
        keep_existing_refresh_token: bool = False,
    ) -> None:
        """Store Cognito authentication tokens."""
        result = response.get("AuthenticationResult")
        if not result:
            raise TendAuthError("Tend did not return authentication tokens")

        expires_in = int(result.get("ExpiresIn", 3600))
        expires_at = (datetime.now(UTC) + timedelta(seconds=expires_in)).timestamp()

        self.access_token = result.get("AccessToken")
        self.id_token = result.get("IdToken")
        self.refresh_token = result.get("RefreshToken") or (
            self.refresh_token if keep_existing_refresh_token else None
        )
        self.expires_at = expires_at

        if not self.id_token or not self.refresh_token:
            raise TendAuthError("Tend authentication result was incomplete")

        tokens = {
            CONF_ACCESS_TOKEN: self.access_token,
            CONF_ID_TOKEN: self.id_token,
            CONF_REFRESH_TOKEN: self.refresh_token,
            CONF_EXPIRES_AT: self.expires_at,
        }
        if self._token_update_callback:
            self._token_update_callback(tokens)


def _normalise_appointments(account: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten Tend appointment bundles and queue items into appointment dicts."""
    items: list[dict[str, Any]] = []

    for bundle in account.get("futureAppointments") or []:
        for appointment in [bundle.get("main"), *(bundle.get("bundled") or [])]:
            if not appointment or not appointment.get("startTime"):
                continue
            item = dict(appointment)
            item["uid"] = appointment.get("id") or bundle.get("id")
            item["kind"] = "appointment"
            items.append(item)

    for queue_item in account.get("appointmentQueueItems") or []:
        appointment = queue_item.get("appointment") or {}
        wait_time = queue_item.get("waitTime") or {}
        slot = wait_time.get("estimatedAppointmentSlot") or {}
        start = (
            appointment.get("startTime")
            or slot.get("startTime")
            or wait_time.get("waitWindowStart")
        )
        if not start:
            continue

        item = dict(appointment)
        item.update(
            {
                "uid": queue_item.get("id") or appointment.get("id") or slot.get("id"),
                "kind": "queue",
                "status": queue_item.get("status") or appointment.get("status"),
                "startTime": start,
                "endTime": appointment.get("endTime") or wait_time.get("waitWindowEnd"),
                "duration": slot.get("duration"),
                "appointmentQueue": queue_item.get("appointmentQueue"),
                "patient": queue_item.get("patient"),
                "dependant": queue_item.get("dependant"),
                "healthConcerns": queue_item.get("healthConcerns"),
            }
        )
        items.append(item)

    return sorted(items, key=lambda item: item["startTime"])


def _challenge_code_key(challenge_name: str) -> str:
    """Return the response field Cognito expects for a challenge code."""
    return {
        "CUSTOM_CHALLENGE": "ANSWER",
        "SMS_MFA": "SMS_MFA_CODE",
        "SOFTWARE_TOKEN_MFA": "SOFTWARE_TOKEN_MFA_CODE",
    }.get(challenge_name, "ANSWER")


def _challenge_username(challenge: TendLoginChallenge, email: str) -> str:
    """Return the username Cognito expects for a challenge response."""
    if challenge.challenge_name == "CUSTOM_CHALLENGE":
        return email
    return challenge.username or email


def _cognito_error_message(data: Any) -> str:
    """Return a concise Cognito error message."""
    if not isinstance(data, dict):
        return "unknown"
    return (
        data.get("message")
        or data.get("Message")
        or data.get("__type")
        or data.get("code")
        or "unknown"
    )


def _safe_cognito_debug(data: Any) -> dict[str, Any]:
    """Return Cognito response fields that are safe to write to Home Assistant logs."""
    if not isinstance(data, dict):
        return {"response_type": type(data).__name__}
    challenge_parameters = data.get("ChallengeParameters") or {}
    return {
        "challenge_name": data.get("ChallengeName"),
        "has_session": bool(data.get("Session")),
        "error_type": data.get("__type"),
        "error_code": data.get("code"),
        "message": data.get("message") or data.get("Message"),
        "challenge_parameters": sorted(challenge_parameters),
    }
