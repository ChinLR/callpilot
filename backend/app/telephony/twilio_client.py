"""Twilio outbound call creation."""

from __future__ import annotations

import logging

from twilio.rest import Client as TwilioRestClient

from app.config import Settings
from app.store import store

logger = logging.getLogger(__name__)


async def create_call(
    to_phone: str,
    campaign_id: str,
    provider_id: str,
    settings: Settings,
) -> str:
    """Place an outbound call via Twilio and register it in the store.

    Returns the Twilio call SID.
    """
    client = TwilioRestClient(settings.twilio_account_sid, settings.twilio_auth_token)

    twiml_url = (
        f"{settings.public_base_url}/twilio/voice"
        f"?campaign_id={campaign_id}&provider_id={provider_id}"
    )
    status_callback_url = (
        f"{settings.public_base_url}/twilio/voice/status"
        f"?campaign_id={campaign_id}&provider_id={provider_id}"
    )

    call = client.calls.create(
        to=to_phone,
        from_=settings.twilio_caller_id,
        url=twiml_url,
        status_callback=status_callback_url,
        status_callback_event=["initiated", "ringing", "answered", "completed"],
        status_callback_method="POST",
        timeout=60,
    )

    logger.info(
        "Created Twilio call %s to %s for campaign %s / provider %s",
        call.sid,
        to_phone,
        campaign_id,
        provider_id,
        extra={
            "campaign_id": campaign_id,
            "provider_id": provider_id,
            "call_sid": call.sid,
        },
    )

    # Register in store so the WS handler can find it
    await store.register_call(call.sid, campaign_id, provider_id)

    return call.sid
