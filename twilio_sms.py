"""Production Twilio SMS sender using a Twilio API Key."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


class TwilioSMS:
    """Send SMS through a Twilio Messaging Service using an API Key."""

    API_BASE_URL = "https://api.twilio.com/2010-04-01"

    def __init__(
        self,
        messaging_service_sid: str | None = None,
        account_sid: str | None = None,
        api_key: str | None = None,
        api_key_secret: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.messaging_service_sid = (
            account_sid or os.environ.get("TWILIO_MESSAGING_SERVICE_SID", "")
        ).strip()
        self.account_sid = (
            account_sid or os.environ.get("TWILIO_ACCOUNT_SID", "")
        ).strip()
        self.api_key = (
            api_key or os.environ.get("TWILIO_API_KEY", "")
        ).strip()
        self.api_key_secret = (
            api_key_secret or os.environ.get("TWILIO_API_KEY_SECRET", "")
        ).strip()

        if not self.messaging_service_sid:
            raise ValueError("TWILIO_MESSAGING_SERVICE_SID is required")
        if not self.account_sid:
            raise ValueError("TWILIO_ACCOUNT_SID is required")
        if not self.api_key:
            raise ValueError("TWILIO_API_KEY is required")
        if not self.api_key_secret:
            raise ValueError("TWILIO_API_KEY_SECRET is required")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        self.timeout = timeout
        self.api_base_url = os.environ.get(
            "TWILIO_API_BASE_URL", self.API_BASE_URL
        ).rstrip("/")

        self._session = requests.Session()

        # Twilio API Key authentication uses HTTP Basic Auth:
        # username = API Key SID
        # password = API Key Secret
        self._session.auth = (
            self.api_key,
            self.api_key_secret,
        )

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

        response = self._session.post(
            url,
            data={
                "To": phone_number,
                "Body": message,
                "MessagingServiceSid": self.messaging_service_sid,
            },
            timeout=self.timeout,
        )

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


if __name__ == "__main__":
    twilio = TwilioSMS(
        messaging_service_sid=None,
        account_sid=None,
        api_key=None,
        api_key_secret=None,
    )

    result = twilio.send_sms(
        "+12622279777",
        "From Trifecta Pool League: Your match is cancelled.",
    )
    print(result)
