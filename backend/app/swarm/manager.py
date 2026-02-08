"""Swarm campaign manager — orchestrates parallel provider calls."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from app.config import Settings, get_settings
from app.schemas import (
    CampaignProgress,
    CampaignStatusEnum,
    Provider,
    SlotOffer,
)
from app.services.calendar import (
    CalendarService,
    CalendarUnavailableError,
    get_calendar_service,
    get_calendar_service_for_user,
)
from app.services.distance import DistanceService, get_distance_service
from app.services.providers import search_providers
from app.services.scoring import rank_offers
from app.store import CampaignState, ProviderCallResultData, store
from app.swarm.models import CallOutcome, ProviderCallResult

logger = logging.getLogger(__name__)

# Type alias for the callable that executes a single provider call
CallFn = Callable[[Provider, CampaignState, Settings], Awaitable[ProviderCallResult]]


# ---------------------------------------------------------------------------
# Simulated receptionist (used when SIMULATED_CALLS=true)
# ---------------------------------------------------------------------------


async def simulate_call(
    provider: Provider,
    campaign: CampaignState,
    settings: Settings,
) -> ProviderCallResult:
    """Deterministic simulated receptionist for demo / testing."""
    req = campaign.request
    # Use the user's linked Google Calendar when available
    if req.user_id:
        calendar_svc = await get_calendar_service_for_user(req.user_id, settings)
    else:
        calendar_svc = get_calendar_service(settings)

    # Stable seed from provider id
    seed = int(hashlib.sha256(provider.id.encode()).hexdigest(), 16)

    # ~20% chance of NO_ANSWER / NO_SLOTS
    fate = seed % 10
    if fate == 0:
        await asyncio.sleep(0.3)
        return ProviderCallResult(
            provider_id=provider.id,
            outcome=CallOutcome.NO_ANSWER,
            notes="Simulated: no answer",
        )
    if fate == 1:
        await asyncio.sleep(0.2)
        return ProviderCallResult(
            provider_id=provider.id,
            outcome=CallOutcome.NO_SLOTS,
            notes="Simulated: receptionist said no availability",
        )

    # Generate 2-3 candidate slots
    base_date = req.date_range_start.replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    if base_date.tzinfo is None:
        base_date = base_date.replace(tzinfo=timezone.utc)

    offers: list[SlotOffer] = []
    for i in range(3):
        offset_hours = ((seed >> (i * 4)) % 8)  # 0-7 hours from 9am
        candidate_start = base_date + timedelta(
            days=i, hours=offset_hours
        )
        candidate_end = candidate_start + timedelta(minutes=req.duration_min)

        # Stay within requested range
        if candidate_end > req.date_range_end:
            continue

        # Check calendar — skip slot if calendar is unreachable (fail-closed)
        try:
            is_free = await calendar_svc.is_free(candidate_start, candidate_end)
        except CalendarUnavailableError:
            logger.warning("Calendar unavailable; skipping slot for %s", provider.id)
            continue
        if not is_free:
            # Try shifting 1 hour later
            candidate_start += timedelta(hours=1)
            candidate_end += timedelta(hours=1)
            if candidate_end > req.date_range_end:
                continue
            try:
                is_free = await calendar_svc.is_free(candidate_start, candidate_end)
            except CalendarUnavailableError:
                logger.warning("Calendar unavailable; skipping shifted slot for %s", provider.id)
                continue
            if not is_free:
                continue

        offers.append(
            SlotOffer(
                provider_id=provider.id,
                start=candidate_start,
                end=candidate_end,
                notes=f"Simulated offer from {provider.name}",
                confidence=0.9 - i * 0.1,
            )
        )

        if len(offers) >= 2:
            break

    # Simulate a short call duration
    await asyncio.sleep(0.2 + (seed % 5) * 0.1)

    if offers:
        return ProviderCallResult(
            provider_id=provider.id,
            outcome=CallOutcome.SUCCESS,
            offers=offers,
            transcript_snippet=f"Simulated call with {provider.name}; offered {len(offers)} slot(s).",
            notes="simulated",
        )
    return ProviderCallResult(
        provider_id=provider.id,
        outcome=CallOutcome.COMPLETED_NO_MATCH,
        notes="Simulated: all candidate slots conflicted with calendar",
    )


# ---------------------------------------------------------------------------
# Real Twilio + ElevenLabs call (used when SIMULATED_CALLS=false)
# ---------------------------------------------------------------------------


async def real_call(
    provider: Provider,
    campaign: CampaignState,
    settings: Settings,
) -> ProviderCallResult:
    """Place a real Twilio call and wait for the ElevenLabs agent to finish."""
    from app.telephony.twilio_client import create_call

    call_sid = await create_call(
        to_phone=provider.phone,
        campaign_id=campaign.campaign_id,
        provider_id=provider.id,
        settings=settings,
    )

    # Wait for the media stream handler to signal completion
    mapping = await store.get_call(call_sid)
    if mapping is None:
        return ProviderCallResult(
            provider_id=provider.id,
            outcome=CallOutcome.FAILED,
            notes="Call mapping not found after create_call",
        )

    # Block until media_stream.py calls store.complete_call()
    await mapping.completion_event.wait()

    result_data = mapping.result
    if result_data is None:
        return ProviderCallResult(
            provider_id=provider.id,
            call_sid=call_sid,
            outcome=CallOutcome.FAILED,
            notes="Call completed but no result data",
        )

    return ProviderCallResult(
        provider_id=result_data.provider_id,
        call_sid=call_sid,
        outcome=CallOutcome(result_data.outcome),
        offers=result_data.offers,
        transcript_snippet=result_data.transcript_snippet,
        notes=result_data.notes,
    )


# ---------------------------------------------------------------------------
# Campaign runner
# ---------------------------------------------------------------------------


async def _call_provider(
    provider: Provider,
    campaign: CampaignState,
    settings: Settings,
    call_fn: CallFn,
    semaphore: asyncio.Semaphore,
) -> ProviderCallResult:
    """Run a single provider call behind the semaphore."""
    async with semaphore:
        try:
            result = await asyncio.wait_for(
                call_fn(provider, campaign, settings),
                timeout=120 if not settings.simulated_calls else 30,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Call to %s timed out",
                provider.id,
                extra={"campaign_id": campaign.campaign_id, "provider_id": provider.id},
            )
            result = ProviderCallResult(
                provider_id=provider.id,
                outcome=CallOutcome.FAILED,
                notes="Call timed out",
            )
        except Exception:
            logger.exception(
                "Call to %s failed",
                provider.id,
                extra={"campaign_id": campaign.campaign_id, "provider_id": provider.id},
            )
            result = ProviderCallResult(
                provider_id=provider.id,
                outcome=CallOutcome.FAILED,
                notes="Unexpected error during call",
            )
    return result


async def run_campaign(
    campaign_id: str,
    call_fn: CallFn | None = None,
    settings: Settings | None = None,
) -> None:
    """Execute a full campaign: find providers, call in parallel, score & rank."""
    settings = settings or get_settings()
    campaign = await store.get_campaign(campaign_id)
    if campaign is None:
        logger.error("Campaign %s not found", campaign_id)
        return

    # Select call function: use explicit call_fn, or pick based on config
    if call_fn is None:
        call_fn = simulate_call if settings.simulated_calls else real_call

    req = campaign.request

    # 1) Find providers
    try:
        providers = await search_providers(req.service, req.location, settings)
        providers = providers[: req.max_providers]
    except Exception:
        logger.exception("Provider search failed for campaign %s", campaign_id)
        await store.update_campaign(campaign_id, status=CampaignStatusEnum.failed)
        return

    await store.update_campaign(
        campaign_id,
        providers=providers,
        progress=CampaignProgress(total_providers=len(providers)),
    )

    if not providers:
        await store.update_campaign(
            campaign_id,
            status=CampaignStatusEnum.completed,
            debug={"note": "No providers found for this service/location"},
        )
        return

    # 2) Call providers in parallel
    semaphore = asyncio.Semaphore(req.max_parallel)
    tasks = [
        asyncio.create_task(
            _call_provider(prov, campaign, settings, call_fn, semaphore)
        )
        for prov in providers
    ]

    all_offers: list[SlotOffer] = []
    call_results: list[ProviderCallResultData] = []
    completed = 0
    successful = 0
    failed = 0

    for coro in asyncio.as_completed(tasks):
        result: ProviderCallResult = await coro
        completed += 1
        if result.outcome == CallOutcome.SUCCESS:
            successful += 1
            all_offers.extend(result.offers)
        elif result.outcome in (CallOutcome.FAILED, CallOutcome.NO_ANSWER, CallOutcome.BUSY):
            failed += 1

        call_results.append(
            ProviderCallResultData(
                provider_id=result.provider_id,
                call_sid=result.call_sid,
                outcome=result.outcome.value,
                offers=result.offers,
                transcript_snippet=result.transcript_snippet,
                notes=result.notes,
            )
        )

        # Update progress incrementally
        await store.update_campaign(
            campaign_id,
            call_results=call_results,
            progress=CampaignProgress(
                total_providers=len(providers),
                completed_calls=completed,
                successful_calls=successful,
                failed_calls=failed,
            ),
        )

    # 3) Score & rank
    distance_svc = get_distance_service(settings)
    providers_by_id = {p.id: p for p in providers}
    travel_by_provider: dict[str, int] = {}
    for p in providers:
        travel_by_provider[p.id] = await distance_svc.estimate_travel_minutes(
            req.location, p
        )

    ranked, scoring_debug = rank_offers(
        all_offers,
        providers_by_id,
        travel_by_provider,
        req.preferences,
        req.date_range_start,
        req.date_range_end,
    )

    best = ranked[0] if ranked else None

    # Build debug info (strip secrets)
    debug = {
        "scoring": scoring_debug,
        "provider_outcomes": {
            cr.provider_id: cr.outcome for cr in call_results
        },
    }

    status = CampaignStatusEnum.completed
    if not ranked and failed == len(providers):
        status = CampaignStatusEnum.failed

    await store.update_campaign(
        campaign_id,
        status=status,
        ranked=ranked,
        best=best,
        debug=debug,
    )

    logger.info(
        "Campaign %s finished: %d offers ranked, best=%s",
        campaign_id,
        len(ranked),
        best.provider_id if best else "none",
        extra={"campaign_id": campaign_id},
    )
