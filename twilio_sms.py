"""Production Twilio SMS sender using OAuth 2.0 Client Credentials."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class _OAuthToken:
    access_token: str
    expires_at: float


class TwilioSMS:
    """Send SMS through a Twilio Messaging Service using OAuth."""

    TOKEN_URL = "https://oauth.twilio.com/v2/token"
    API_BASE_URL = "https://api.twilio.com/2010-04-01"

    def __init__(
        self,
        messaging_service_sid: str,
        account_sid: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout: float = 30.0,
        token_refresh_buffer: int = 60,
    ) -> None:
        self.messaging_service_sid = messaging_service_sid.strip()
        if not self.messaging_service_sid:
            raise ValueError("messaging_service_sid is required")

        self.account_sid = (
            account_sid or os.environ.get("TWILIO_ACCOUNT_SID", "")
        ).strip()
        self.client_id = (
            client_id or os.environ.get("TWILIO_OAUTH_CLIENT_ID", "")
        ).strip()
        self.client_secret = (
            client_secret or os.environ.get("TWILIO_OAUTH_CLIENT_SECRET", "")
        ).strip()

        if not self.account_sid:
            raise ValueError("TWILIO_ACCOUNT_SID is required")
        if not self.client_id:
            raise ValueError("TWILIO_OAUTH_CLIENT_ID is required")
        if not self.client_secret:
            raise ValueError("TWILIO_OAUTH_CLIENT_SECRET is required")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if token_refresh_buffer < 0:
            raise ValueError("token_refresh_buffer cannot be negative")

        self.timeout = timeout
        self.token_refresh_buffer = token_refresh_buffer
        self.token_url = os.environ.get("TWILIO_OAUTH_TOKEN_URL", self.TOKEN_URL)
        self.api_base_url = os.environ.get(
            "TWILIO_API_BASE_URL", self.API_BASE_URL
        ).rstrip("/")

        self._session = requests.Session()
        self._token: _OAuthToken | None = None

    def _get_access_token(self, force_refresh: bool = False) -> str:
        """Return a cached token or obtain a new one."""
        now = time.time()

        if (
            not force_refresh
            and self._token is not None
            and now < self._token.expires_at - self.token_refresh_buffer
        ):
            return self._token.access_token

        response = self._session.post(
            self.token_url,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"Twilio OAuth token request failed "
                f"({response.status_code}): {response.text[:500]}"
            ) from exc

        try:
            token_data = response.json()
            access_token = token_data["access_token"]
            expires_in = int(token_data["expires_in"])
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeError(
                "Twilio OAuth response did not contain a valid "
                "access_token/expires_in"
            ) from exc

        self._token = _OAuthToken(
            access_token=access_token,
            expires_at=time.time() + expires_in,
        )
        return access_token

    def send_sms(self, phone_number: str, message: str) -> dict[str, Any]:
        """Send one SMS and return Twilio's JSON response."""
        phone_number = phone_number.strip()

        if not phone_number:
            raise ValueError("phone_number is required")
        if not message:
            raise ValueError("message is required")

        url = (
            f"{self.api_base_url}/Accounts/"
            f"{self.account_sid}/Messages.json"
        )

        def send(access_token: str) -> requests.Response:
            return self._session.post(
                url,
                data={
                    "To": phone_number,
                    "Body": message,
                    "MessagingServiceSid": self.messaging_service_sid,
                },
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self.timeout,
            )

        response = send(self._get_access_token())

        # Refresh once if the cached token was rejected.
        if response.status_code == 401:
            response = send(self._get_access_token(force_refresh=True))

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"Twilio SMS request failed "
                f"({response.status_code}): {response.text[:1000]}"
            ) from exc

        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(
                "Twilio returned a successful response that was not valid JSON"
            ) from exc

    def close(self) -> None:
        """Close the HTTP session."""
        self._session.close()

    def __enter__(self) -> "TwilioSMS":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

