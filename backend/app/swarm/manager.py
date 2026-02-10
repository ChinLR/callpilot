"""Swarm campaign manager — orchestrates parallel provider calls."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from app.config import Settings, get_settings
from app.schemas import (
    BookingConfirmation,
    CallMode,
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
from app.services.providers import get_cached_providers, search_providers
from app.services.scoring import rank_offers
from app.store import CampaignState, ProviderCallResultData, store
from app.swarm.models import CallOutcome, ProviderCallResult

logger = logging.getLogger(__name__)

# Type alias for the callable that executes a single provider call
CallFn = Callable[[Provider, CampaignState, Settings], Awaitable[ProviderCallResult]]


class _ProgressTracker:
    """Tracks the number of calls currently in progress and updates the store."""

    def __init__(self, total_providers: int) -> None:
        self._in_progress = 0
        self._total = total_providers
        self._lock = asyncio.Lock()

    @property
    def in_progress(self) -> int:
        return self._in_progress

    async def call_started(self, campaign_id: str) -> None:
        async with self._lock:
            self._in_progress += 1
            count = self._in_progress
        # Fetch current progress to preserve completed/successful/failed counts
        campaign = await store.get_campaign(campaign_id)
        if campaign:
            await store.update_campaign(
                campaign_id,
                progress=CampaignProgress(
                    total_providers=self._total,
                    calls_in_progress=count,
                    completed_calls=campaign.progress.completed_calls,
                    successful_calls=campaign.progress.successful_calls,
                    failed_calls=campaign.progress.failed_calls,
                ),
            )

    async def call_finished(self, campaign_id: str) -> None:
        async with self._lock:
            self._in_progress = max(0, self._in_progress - 1)


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
    # Use the user's linked Google Calendar when available.
    # Fallback: if no user_id, try the first stored OAuth token (demo mode).
    user_id = req.user_id
    if not user_id and store.oauth_tokens:
        user_id = next(iter(store.oauth_tokens))

    if user_id:
        calendar_svc = await get_calendar_service_for_user(user_id, settings)
    else:
        calendar_svc = get_calendar_service(settings)

    # Stable seed from provider id
    seed = int(hashlib.sha256(provider.id.encode()).hexdigest(), 16)

    # ~20% chance of NO_ANSWER / NO_SLOTS
    fate = seed % 10
    if fate == 0:
        await asyncio.sleep(8.0 + (seed % 5))  # ring for a while, then no answer
        return ProviderCallResult(
            provider_id=provider.id,
            outcome=CallOutcome.NO_ANSWER,
            notes="Simulated: no answer",
        )
    if fate == 1:
        await asyncio.sleep(6.0 + (seed % 4))  # conversation, then declined
        return ProviderCallResult(
            provider_id=provider.id,
            outcome=CallOutcome.NO_SLOTS,
            notes="Simulated: receptionist said no availability",
        )

    # Generate 2-3 candidate slots using the configured timezone
    # so that "9 AM" means 9 AM local time, not UTC.
    try:
        local_tz = ZoneInfo(settings.default_timezone)
    except (KeyError, Exception):
        local_tz = ZoneInfo("UTC")

    base_date = req.date_range_start.replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    if base_date.tzinfo is None:
        base_date = base_date.replace(tzinfo=local_tz)
    else:
        base_date = base_date.astimezone(local_tz).replace(
            hour=9, minute=0, second=0, microsecond=0
        )

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

    # Simulate a realistic call duration (6-14 seconds feels natural in a demo)
    await asyncio.sleep(6.0 + (seed % 5) * 1.6)

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
# Simulated booking callback (Phase 2)
# ---------------------------------------------------------------------------


async def simulate_booking_call(
    offer: SlotOffer,
    campaign: CampaignState,
    settings: Settings,
) -> ProviderCallResult:
    """Deterministic simulated booking callback for demo / testing.

    Uses a hash of the offer to decide success (~90%) vs rejection (~10%).
    Sleeps 1-3 seconds to simulate a realistic call duration.
    """
    seed = int(
        hashlib.sha256(
            f"{offer.provider_id}:{offer.start.isoformat()}:book".encode()
        ).hexdigest(),
        16,
    )

    # Simulate a realistic callback duration (4-8 seconds)
    await asyncio.sleep(4.0 + (seed % 3) * 1.5)

    # ~90% success rate
    if seed % 10 == 0:
        return ProviderCallResult(
            provider_id=offer.provider_id,
            outcome=CallOutcome.BOOKING_REJECTED,
            notes=f"Simulated: {offer.provider_id} said the slot is no longer available",
        )

    return ProviderCallResult(
        provider_id=offer.provider_id,
        outcome=CallOutcome.BOOKING_CONFIRMED,
        notes=f"Simulated: confirmed {offer.start.isoformat()} with {offer.provider_id}",
    )


async def _run_booking_phase(
    campaign_id: str,
    ranked: list[SlotOffer],
    providers_by_id: dict[str, Provider],
    settings: Settings,
    max_attempts: int = 3,
) -> None:
    """Phase 2: call back top-ranked providers to confirm a booking.

    Tries up to *max_attempts* providers (best-first).  On first success
    the campaign status is set to ``booked``.  If all attempts fail the
    status falls back to ``completed`` so the user can still manually review.
    """
    campaign = await store.get_campaign(campaign_id)
    if campaign is None:
        return

    await store.update_campaign(campaign_id, status=CampaignStatusEnum.booking)
    logger.info("Campaign %s entering booking phase (%d candidates)", campaign_id, len(ranked))

    for idx, offer in enumerate(ranked[:max_attempts]):
        logger.info(
            "Campaign %s booking attempt %d/%d: provider=%s slot=%s",
            campaign_id, idx + 1, max_attempts,
            offer.provider_id, offer.start.isoformat(),
        )

        try:
            result = await asyncio.wait_for(
                simulate_booking_call(offer, campaign, settings),
                timeout=30,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Booking call to %s timed out", offer.provider_id,
                extra={"campaign_id": campaign_id},
            )
            continue
        except Exception:
            logger.exception(
                "Booking call to %s failed", offer.provider_id,
                extra={"campaign_id": campaign_id},
            )
            continue

        if result.outcome == CallOutcome.BOOKING_CONFIRMED:
            confirmation = BookingConfirmation(
                provider_id=offer.provider_id,
                start=offer.start,
                end=offer.end,
                confirmation_ref=f"CONF-{uuid.uuid4().hex[:8].upper()}",
                confirmed_at=datetime.now(timezone.utc),
                notes=result.notes,
                client_name=campaign.request.client_name,
                client_phone=campaign.request.client_phone,
            )
            await store.update_campaign(
                campaign_id,
                status=CampaignStatusEnum.booked,
                booking_confirmation=confirmation,
            )
            logger.info(
                "Campaign %s BOOKED: provider=%s ref=%s slot=%s",
                campaign_id, offer.provider_id,
                confirmation.confirmation_ref, offer.start.isoformat(),
            )
            return

        # Booking rejected — try next provider
        logger.info(
            "Campaign %s booking rejected by %s, trying next",
            campaign_id, offer.provider_id,
        )

    # All attempts exhausted — fall back to completed (offers still available)
    logger.warning(
        "Campaign %s booking phase exhausted %d attempts, falling back to completed",
        campaign_id, max_attempts,
    )
    await store.update_campaign(campaign_id, status=CampaignStatusEnum.completed)


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
    progress_tracker: _ProgressTracker,
) -> ProviderCallResult:
    """Run a single provider call behind the semaphore."""
    async with semaphore:
        await progress_tracker.call_started(campaign.campaign_id)
        try:
            # Use a longer timeout for real Twilio calls than for simulated ones
            is_real = call_fn is real_call
            result = await asyncio.wait_for(
                call_fn(provider, campaign, settings),
                timeout=300 if is_real else 30,
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
        finally:
            await progress_tracker.call_finished(campaign.campaign_id)
    return result


def _resolve_call_mode(req_mode: CallMode, settings: Settings) -> CallMode:
    """Resolve ``auto`` into ``real`` or ``simulated`` based on the server setting."""
    if req_mode == CallMode.auto:
        return CallMode.simulated if settings.simulated_calls else CallMode.real
    return req_mode


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

    req = campaign.request

    # --- Resolve per-campaign call mode ---
    effective_mode = _resolve_call_mode(req.call_mode, settings)
    logger.info(
        "Campaign %s call_mode: requested=%s, effective=%s",
        campaign_id, req.call_mode.value, effective_mode.value,
    )

    # Select call function: explicit call_fn > per-campaign mode
    if call_fn is None:
        if effective_mode == CallMode.real:
            call_fn = real_call
        else:
            # For both "simulated" and "hybrid", the default call_fn is simulate.
            # Hybrid mode overrides the *first* provider below.
            call_fn = simulate_call

    # 1) Find providers
    #
    # When provider_ids are supplied (user already picked providers in the
    # preview step), try to retrieve them from the in-memory cache first.
    # This avoids a redundant search that might return different place IDs
    # (e.g. Nearby Search vs Text Search yield different results).
    providers: list[Provider] = []

    if req.provider_ids:
        cached = get_cached_providers(req.provider_ids)
        if cached is not None:
            providers = cached
            logger.info(
                "Campaign %s: retrieved %d providers from cache",
                campaign_id, len(providers),
            )

    if not providers:
        try:
            providers = await search_providers(req.service, req.location, settings)
            providers = providers[: req.max_providers]
        except Exception:
            logger.exception("Provider search failed for campaign %s", campaign_id)
            await store.update_campaign(campaign_id, status=CampaignStatusEnum.failed)
            return

        # Filter to user-selected providers (from preview step)
        if req.provider_ids:
            selected = set(req.provider_ids)
            providers = [p for p in providers if p.id in selected]

    # Filter by max travel time
    if req.max_travel_minutes > 0:
        distance_svc_filter = get_distance_service(settings)
        filtered: list[Provider] = []
        for p in providers:
            travel = await distance_svc_filter.estimate_travel_minutes(
                req.location, p
            )
            if travel <= req.max_travel_minutes:
                filtered.append(p)
        providers = filtered

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
    progress_tracker = _ProgressTracker(total_providers=len(providers))

    # In hybrid mode the first provider gets a real Twilio call;
    # every other provider gets a simulated call.
    tasks: list[asyncio.Task[ProviderCallResult]] = []
    for idx, prov in enumerate(providers):
        if effective_mode == CallMode.hybrid and idx == 0:
            fn = real_call
        else:
            fn = call_fn
        tasks.append(
            asyncio.create_task(
                _call_provider(prov, campaign, settings, fn, semaphore, progress_tracker)
            )
        )

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
                calls_in_progress=progress_tracker.in_progress,
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
        "call_mode": effective_mode.value,
        "scoring": scoring_debug,
        "provider_outcomes": {
            cr.provider_id: cr.outcome for cr in call_results
        },
    }

    # Determine initial status after discovery
    if not ranked and failed == len(providers):
        status = CampaignStatusEnum.failed
    elif ranked and req.auto_book:
        # Will proceed to booking phase — keep status as running for now
        status = CampaignStatusEnum.running
    else:
        status = CampaignStatusEnum.completed

    await store.update_campaign(
        campaign_id,
        status=status,
        ranked=ranked,
        best=best,
        debug=debug,
    )

    logger.info(
        "Campaign %s discovery finished: %d offers ranked, best=%s, auto_book=%s",
        campaign_id,
        len(ranked),
        best.provider_id if best else "none",
        req.auto_book,
        extra={"campaign_id": campaign_id},
    )

    # --- Phase 2: Autonomous booking ---
    if ranked and req.auto_book:
        await _run_booking_phase(
            campaign_id,
            ranked,
            providers_by_id,
            settings,
        )
