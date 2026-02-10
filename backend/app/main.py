"""CallPilot FastAPI application — Agentic Voice AI for Appointment Scheduling."""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.auth import router as auth_router
from app.config import Settings, get_settings
from app.logging_utils import setup_logging
from app.schemas import (
    AppointmentRequest,
    CallMode,
    CampaignProgress,
    CampaignResponse,
    CampaignStatusEnum,
    ConfirmRequest,
    ConfirmResponse,
    CreateCampaignResponse,
    ProviderPreview,
    ProviderSearchRequest,
    ProviderSearchResponse,
)
from app.services.calendar import (
    CalendarUnavailableError,
    get_calendar_service,
    get_calendar_service_for_user,
)
from app.services.distance import get_distance_service
from app.services.providers import search_providers
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

# Register auth routes
app.include_router(auth_router)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


# ---------------------------------------------------------------------------
# Call mode settings (switch between real / simulated / hybrid)
# ---------------------------------------------------------------------------


@app.get("/settings/call-mode")
async def get_call_mode() -> dict[str, Any]:
    """Return the current server-wide call mode default and available options."""
    s = get_settings()
    effective = "simulated" if s.simulated_calls else "real"
    return {
        "server_default": effective,
        "available_modes": [m.value for m in CallMode],
        "description": {
            "auto": "Use the server-wide SIMULATED_CALLS env var",
            "real": "Every call goes through Twilio (requires a Twilio number per parallel call)",
            "simulated": "All calls are simulated locally — no Twilio needed",
            "hybrid": "First call is real (Twilio), remaining calls are simulated in parallel",
        },
    }


@app.put("/settings/call-mode")
async def set_call_mode(mode: str = Query(...)) -> dict[str, str]:
    """Toggle the server-wide simulated_calls flag at runtime.

    Accepts ``real`` or ``simulated``.  This changes the in-process default
    for all future campaigns that use ``call_mode=auto``.
    """
    if mode not in ("real", "simulated"):
        raise HTTPException(
            status_code=400,
            detail="mode must be 'real' or 'simulated'",
        )
    # Mutate the cached settings singleton
    s = get_settings()
    s.simulated_calls = mode == "simulated"
    logger.info("Server-wide call mode changed to %s (simulated_calls=%s)", mode, s.simulated_calls)
    return {"server_default": mode}


# ---------------------------------------------------------------------------
# Provider search (preview before calling)
# ---------------------------------------------------------------------------


@app.post("/providers/search", response_model=ProviderSearchResponse)
async def search_providers_endpoint(
    body: ProviderSearchRequest,
) -> ProviderSearchResponse:
    """Search providers and return them with travel-time info.

    The frontend calls this first so the user can review providers
    (distance, rating, etc.) and pick which ones to call.
    """
    settings = get_settings()
    providers = await search_providers(
        body.service, body.location, settings,
        lat=body.lat, lng=body.lng,
    )
    providers = providers[: body.max_providers]

    # Use coordinates as distance origin when available, else text location
    distance_origin = (
        f"{body.lat},{body.lng}" if body.lat is not None and body.lng is not None
        else body.location
    )

    distance_svc = get_distance_service(settings)
    previews: list[ProviderPreview] = []
    for p in providers:
        travel = await distance_svc.estimate_travel_minutes(distance_origin, p)

        # Skip providers that exceed the distance filter
        if body.max_travel_minutes > 0 and travel > body.max_travel_minutes:
            continue

        previews.append(
            ProviderPreview(
                id=p.id,
                name=p.name,
                phone=p.phone,
                address=p.address,
                rating=p.rating,
                lat=p.lat,
                lng=p.lng,
                services=p.services,
                travel_minutes=travel,
            )
        )

    # Sort by travel time (closest first)
    previews.sort(key=lambda p: p.travel_minutes)

    return ProviderSearchResponse(providers=previews)


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

    # Resolve the effective call mode so the frontend knows what will happen
    from app.swarm.manager import _resolve_call_mode
    effective_mode = _resolve_call_mode(request.call_mode, settings)

    logger.info(
        "Campaign %s started (user_id=%r, call_mode=%s→%s, oauth_tokens=%d)",
        campaign.campaign_id,
        request.user_id,
        request.call_mode.value,
        effective_mode.value,
        len(store.oauth_tokens),
    )
    return CreateCampaignResponse(
        campaign_id=campaign.campaign_id,
        status=CampaignStatusEnum.running,
        call_mode=effective_mode.value,
    )


@app.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(campaign_id: str) -> CampaignResponse:
    """Poll campaign status and results."""
    campaign = await store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Enrich debug with provider metadata so pages can display names/ratings
    debug = dict(campaign.debug)
    if campaign.providers and "providers" not in debug:
        debug["providers"] = {
            p.id: {"name": p.name, "rating": p.rating, "address": p.address, "phone": p.phone}
            for p in campaign.providers
        }

    return CampaignResponse(
        campaign_id=campaign.campaign_id,
        status=campaign.status,
        progress=campaign.progress,
        best=campaign.best,
        ranked=campaign.ranked,
        booking=campaign.booking_confirmation,
        debug=debug,
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

    # Re-check calendar (use user's linked Google Calendar if available)
    settings = get_settings()
    user_id = campaign.request.user_id

    # Fallback: if no user_id, try the first stored OAuth token (demo mode)
    if not user_id and store.oauth_tokens:
        user_id = next(iter(store.oauth_tokens))

    if user_id:
        calendar = await get_calendar_service_for_user(user_id, settings)
    else:
        calendar = get_calendar_service(settings)

    try:
        still_free = await calendar.is_free(body.start, body.end)
    except CalendarUnavailableError:
        logger.exception("Calendar unavailable during confirm for campaign %s", campaign_id)
        raise HTTPException(
            status_code=503,
            detail="Cannot verify calendar availability right now; please try again",
        )
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

    # Twilio Media Streams don't pass query params on the WebSocket URL.
    # Fall back to looking up the call mapping from the store.
    if not campaign_id or not provider_id:
        call_mapping = await store.get_call(call_id)
        if call_mapping:
            campaign_id = campaign_id or call_mapping.campaign_id
            provider_id = provider_id or call_mapping.provider_id

    await handle_media_stream(
        websocket=websocket,
        call_id=call_id,
        campaign_id=campaign_id,
        provider_id=provider_id,
        settings=settings,
    )
