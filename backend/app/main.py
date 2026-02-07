"""CallPilot FastAPI application — Agentic Voice AI for Appointment Scheduling."""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.config import Settings, get_settings
from app.logging_utils import setup_logging
from app.schemas import (
    AppointmentRequest,
    CampaignProgress,
    CampaignResponse,
    CampaignStatusEnum,
    ConfirmRequest,
    ConfirmResponse,
    CreateCampaignResponse,
)
from app.services.calendar import get_calendar_service
from app.store import store
from app.swarm.manager import run_campaign
from app.telephony.media_stream import handle_media_stream
from app.telephony.twiml import build_twiml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    setup_logging()
    logger.info("CallPilot backend starting up")
    yield
    logger.info("CallPilot backend shutting down")


# ---------------------------------------------------------------------------
# App creation
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CallPilot",
    description="Agentic Voice AI for Autonomous Appointment Scheduling",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
settings = get_settings()
if settings.allow_all_cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


# ---------------------------------------------------------------------------
# Campaign endpoints
# ---------------------------------------------------------------------------


@app.post("/campaigns", status_code=202, response_model=CreateCampaignResponse)
async def create_campaign(request: AppointmentRequest) -> CreateCampaignResponse:
    """Start a new appointment scheduling campaign."""
    campaign = await store.create_campaign(request)

    # Launch campaign in background
    settings = get_settings()
    asyncio.create_task(run_campaign(campaign.campaign_id, settings=settings))

    logger.info("Campaign %s started", campaign.campaign_id)
    return CreateCampaignResponse(
        campaign_id=campaign.campaign_id,
        status=CampaignStatusEnum.running,
    )


@app.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(campaign_id: str) -> CampaignResponse:
    """Poll campaign status and results."""
    campaign = await store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return CampaignResponse(
        campaign_id=campaign.campaign_id,
        status=campaign.status,
        progress=campaign.progress,
        best=campaign.best,
        ranked=campaign.ranked,
        debug=campaign.debug,
    )


@app.post("/campaigns/{campaign_id}/confirm", response_model=ConfirmResponse)
async def confirm_slot(campaign_id: str, body: ConfirmRequest) -> ConfirmResponse:
    """Confirm a chosen slot from the ranked offers."""
    campaign = await store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Validate the slot is in ranked offers
    slot_found = False
    for offer in campaign.ranked:
        if (
            offer.provider_id == body.provider_id
            and offer.start == body.start
            and offer.end == body.end
        ):
            slot_found = True
            break

    if not slot_found:
        raise HTTPException(
            status_code=400,
            detail="Requested slot not found in campaign ranked offers",
        )

    # Re-check calendar
    settings = get_settings()
    calendar = get_calendar_service(settings)
    still_free = await calendar.is_free(body.start, body.end)
    if not still_free:
        raise HTTPException(
            status_code=409,
            detail="Slot conflicts with calendar; it may have been booked since the campaign ran",
        )

    confirmation_ref = f"CONF-{uuid.uuid4().hex[:8].upper()}"

    logger.info(
        "Slot confirmed: campaign=%s provider=%s ref=%s",
        campaign_id, body.provider_id, confirmation_ref,
    )

    return ConfirmResponse(
        campaign_id=campaign_id,
        confirmed=True,
        confirmation_ref=confirmation_ref,
    )


# ---------------------------------------------------------------------------
# Twilio webhooks
# ---------------------------------------------------------------------------


@app.post("/twilio/voice")
async def twilio_voice_webhook(
    request: Request,
    campaign_id: str = Query(""),
    provider_id: str = Query(""),
) -> Response:
    """TwiML webhook called by Twilio when an outbound call connects.

    Returns TwiML that plays a disclosure message then connects the
    bidirectional Media Stream.
    """
    settings = get_settings()

    # The call_sid comes from Twilio's POST body
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")

    # Build the WebSocket stream URL
    base = settings.public_base_url.replace("http://", "wss://").replace(
        "https://", "wss://"
    )
    stream_url = (
        f"{base}/twilio/stream/{call_sid}"
        f"?campaign_id={campaign_id}&provider_id={provider_id}"
    )

    twiml = build_twiml(stream_url)

    logger.info(
        "TwiML webhook: call_sid=%s campaign=%s provider=%s",
        call_sid, campaign_id, provider_id,
    )

    return Response(content=twiml, media_type="application/xml")


@app.post("/twilio/voice/status")
async def twilio_voice_status(
    request: Request,
    campaign_id: str = Query(""),
    provider_id: str = Query(""),
) -> dict[str, str]:
    """Status callback for Twilio call lifecycle events."""
    form = await request.form()
    call_sid = str(form.get("CallSid", ""))
    call_status = str(form.get("CallStatus", ""))

    logger.info(
        "Call status: sid=%s status=%s campaign=%s provider=%s",
        call_sid, call_status, campaign_id, provider_id,
    )

    # Handle terminal states that mean the call never connected or failed
    if call_status in ("busy", "no-answer", "canceled", "failed"):
        from app.store import ProviderCallResultData
        from app.swarm.models import CallOutcome

        outcome_map = {
            "busy": CallOutcome.BUSY,
            "no-answer": CallOutcome.NO_ANSWER,
            "canceled": CallOutcome.FAILED,
            "failed": CallOutcome.FAILED,
        }
        outcome = outcome_map.get(call_status, CallOutcome.FAILED)

        result = ProviderCallResultData(
            provider_id=provider_id,
            call_sid=call_sid,
            outcome=outcome.value,
            notes=f"Twilio status: {call_status}",
        )
        await store.complete_call(call_sid, result)

    return {"status": "received"}


# ---------------------------------------------------------------------------
# Twilio Media Stream WebSocket
# ---------------------------------------------------------------------------


@app.websocket("/twilio/stream/{call_id}")
async def twilio_stream_ws(
    websocket: WebSocket,
    call_id: str,
    campaign_id: str = Query(""),
    provider_id: str = Query(""),
) -> None:
    """WebSocket endpoint for Twilio bidirectional Media Streams."""
    settings = get_settings()
    await handle_media_stream(
        websocket=websocket,
        call_id=call_id,
        campaign_id=campaign_id,
        provider_id=provider_id,
        settings=settings,
    )
