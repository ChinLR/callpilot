"""Tools registry — callable functions for ElevenLabs agent tool calls.

Each tool is an async function that accepts (params, context) and returns
a JSON-serializable dict.  The dispatch_tool function routes tool calls
from the ElevenLabs WebSocket to the correct handler.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.config import Settings
from app.services.calendar import (
    CalendarUnavailableError,
    get_calendar_service,
    get_calendar_service_for_user,
)
from app.services.distance import get_distance_service
from app.services.providers import search_providers

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fix_past_dates(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """If the AI agent accidentally used a past year, bump to current year."""
    from datetime import date as date_type

    today = date_type.today()
    if start.date() < today:
        year_delta = today.year - start.year
        if year_delta > 0:
            start = start.replace(year=start.year + year_delta)
            end = end.replace(year=end.year + year_delta)
            logger.warning("Auto-corrected past date by +%d year(s)", year_delta)
    return start, end


def _localize_naive(dt: datetime, settings: Settings) -> datetime:
    """If *dt* is naive (no tzinfo), attach the configured local timezone.

    This ensures that "10:00" from the AI agent is interpreted as 10:00
    in the user's timezone rather than 10:00 UTC.
    """
    if dt.tzinfo is not None:
        return dt
    try:
        tz = ZoneInfo(settings.default_timezone)
    except (KeyError, Exception):
        tz = ZoneInfo("UTC")
    return dt.replace(tzinfo=tz)


async def _get_calendar_for_context(context: dict):
    """Resolve the best calendar service from the tool context.

    Uses the user's linked Google Calendar if the campaign has a user_id,
    otherwise falls back to the default (service-account or mock).

    As a convenience for single-user demos, if no user_id is set on the
    campaign but there is exactly one OAuth token in the store, use it.
    """
    settings: Settings = context.get("settings", Settings())

    campaign_id = context.get("campaign_id", "")
    user_id = ""
    if campaign_id:
        from app.store import store
        campaign = await store.get_campaign(campaign_id)
        if campaign:
            user_id = campaign.request.user_id

    if user_id:
        logger.info(
            "Campaign %s has user_id=%s; resolving calendar service",
            campaign_id, user_id,
        )
        return await get_calendar_service_for_user(user_id, settings)

    # Fallback: if no user_id but there are stored OAuth tokens, pick the
    # first one.  This keeps single-user / demo setups working without
    # requiring the frontend to pass user_id on every campaign.
    from app.store import store as _store
    if _store.oauth_tokens:
        fallback_user_id = next(iter(_store.oauth_tokens))
        logger.info(
            "Campaign %s has no user_id; using fallback OAuth token for user_id=%s",
            campaign_id, fallback_user_id,
        )
        return await get_calendar_service_for_user(fallback_user_id, settings)

    svc = get_calendar_service(settings)
    logger.info(
        "No OAuth tokens available; using %s calendar",
        type(svc).__name__,
    )
    return svc


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def calendar_check(params: dict, context: dict) -> dict:
    """Check if a time slot is free on the user's calendar."""
    calendar = await _get_calendar_for_context(context)
    settings: Settings = context.get("settings", Settings())

    start_str = params.get("start", "")
    end_str = params.get("end", "")

    try:
        start = _localize_naive(datetime.fromisoformat(start_str), settings)
        end = _localize_naive(datetime.fromisoformat(end_str), settings)

        # Auto-correct past years
        start, end = _fix_past_dates(start, end)
    except (ValueError, TypeError):
        return {"free": False, "error": "Invalid datetime format"}

    try:
        free = await calendar.is_free(start, end)
    except CalendarUnavailableError:
        logger.warning("Calendar unavailable during calendar_check; reporting as not free")
        return {"free": False, "error": "Calendar unavailable, cannot verify"}

    return {
        "free": free,
        "checked_start": start.strftime("%-I:%M %p"),
        "checked_end": end.strftime("%-I:%M %p"),
        "timezone": settings.default_timezone,
    }


async def validate_slot(params: dict, context: dict) -> dict:
    """Validate a slot: must be calendar-free and within the campaign's date range."""
    calendar = await _get_calendar_for_context(context)
    settings: Settings = context.get("settings", Settings())

    start_str = params.get("start", "")
    end_str = params.get("end", "")

    try:
        start = _localize_naive(datetime.fromisoformat(start_str), settings)
        end = _localize_naive(datetime.fromisoformat(end_str), settings)

        # Auto-correct past years
        start, end = _fix_past_dates(start, end)
    except (ValueError, TypeError):
        return {"ok": False, "reason": "Invalid datetime format"}

    # Verify slot falls within campaign date range
    campaign_id = context.get("campaign_id", "")
    if campaign_id:
        from app.store import store
        campaign = await store.get_campaign(campaign_id)
        if campaign:
            range_start = _localize_naive(campaign.request.date_range_start, settings)
            range_end = _localize_naive(campaign.request.date_range_end, settings)
            if start < range_start or end > range_end:
                return {"ok": False, "reason": "Slot is outside the requested date range"}

    try:
        free = await calendar.is_free(start, end)
    except CalendarUnavailableError:
        logger.warning("Calendar unavailable during validate_slot; rejecting slot")
        return {"ok": False, "reason": "Calendar unavailable, cannot verify availability"}

    if not free:
        return {"ok": False, "reason": "Conflicts with client calendar"}

    return {"ok": True, "reason": None}


async def distance_check(params: dict, context: dict) -> dict:
    """Return estimated travel time to a provider."""
    settings: Settings = context.get("settings", Settings())
    distance_svc = get_distance_service(settings)

    provider_id = params.get("provider_id", "")
    # We need a Provider object; look it up from the campaign
    from app.store import store
    campaign_id = context.get("campaign_id", "")
    campaign = await store.get_campaign(campaign_id) if campaign_id else None

    if campaign:
        for p in campaign.providers:
            if p.id == provider_id:
                minutes = await distance_svc.estimate_travel_minutes(
                    campaign.request.location, p
                )
                return {"minutes": minutes}

    return {"minutes": -1, "error": "Provider not found"}


async def log_event(params: dict, context: dict) -> dict:
    """Log an event from the agent (used for call summaries and debugging)."""
    message = params.get("message", "")
    data = params.get("data", {})
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            data = {"raw": data}

    campaign_id = context.get("campaign_id", "")
    provider_id = context.get("provider_id", "")

    logger.info(
        "Agent log_event: %s | data=%s",
        message,
        json.dumps(data, default=str)[:500],
        extra={"campaign_id": campaign_id, "provider_id": provider_id},
    )

    return {"ok": True}


async def provider_lookup(params: dict, context: dict) -> dict:
    """Search for alternative providers (mid-conversation agent tool)."""
    settings: Settings = context.get("settings", Settings())

    service = params.get("service", "")
    location = params.get("location", "")
    exclude_ids = params.get("exclude_ids", [])
    if isinstance(exclude_ids, str):
        try:
            exclude_ids = json.loads(exclude_ids)
        except (json.JSONDecodeError, TypeError):
            exclude_ids = []

    if not service or not location:
        # Try to infer from campaign
        campaign_id = context.get("campaign_id", "")
        if campaign_id:
            from app.store import store
            campaign = await store.get_campaign(campaign_id)
            if campaign:
                service = service or campaign.request.service
                location = location or campaign.request.location

    providers = await search_providers(service, location, settings)
    filtered = [p for p in providers if p.id not in exclude_ids][:5]

    return {
        "providers": [
            {
                "id": p.id,
                "name": p.name,
                "rating": p.rating,
                "phone": p.phone,
                "address": p.address,
            }
            for p in filtered
        ]
    }


async def available_slots(params: dict, context: dict) -> dict:
    """Return the client's free time windows for a given date (9 AM–5 PM).

    Params:
        date: ISO date string, e.g. "2026-02-10"
        business_start: (optional) hour int, default 9
        business_end:   (optional) hour int, default 17
    """
    calendar = await _get_calendar_for_context(context)
    settings: Settings = context.get("settings", Settings())

    date_str = params.get("date", "")
    try:
        from datetime import date as date_type
        day = date_type.fromisoformat(date_str)

        # Auto-correct past dates: if the agent accidentally used a past
        # year (e.g. 2025 instead of 2026), bump to the current year.
        today = date_type.today()
        if day < today:
            day = day.replace(year=today.year)
            if day < today:
                day = day.replace(year=today.year + 1)
            logger.warning(
                "available_slots: corrected past date %s → %s",
                date_str, day.isoformat(),
            )
    except (ValueError, TypeError):
        return {"slots": [], "error": "Invalid date format. Use YYYY-MM-DD."}

    biz_start = int(params.get("business_start", 9))
    biz_end = int(params.get("business_end", 17))

    # Use the configured timezone so business hours are in the user's
    # local time rather than UTC.
    tz_name = settings.default_timezone

    try:
        windows = await calendar.get_available_slots(
            day,
            business_start=biz_start,
            business_end=biz_end,
            min_slot_minutes=30,
            tz_name=tz_name,
        )
    except Exception:
        logger.warning("Calendar unavailable during available_slots lookup")
        return {"slots": [], "error": "Calendar unavailable, cannot fetch availability"}

    slots = []
    for s, e in windows:
        slots.append({
            "start": s.isoformat(),
            "end": e.isoformat(),
            # Human-readable labels so the AI agent doesn't misinterpret
            # the timezone offset (e.g. reading +01:00 as "plus 1 hour").
            "start_local": s.strftime("%-I:%M %p"),
            "end_local": e.strftime("%-I:%M %p"),
            "date": s.strftime("%A, %B %-d, %Y"),
        })
    return {"slots": slots, "timezone": tz_name}


async def propose_alternatives(params: dict, context: dict) -> dict:
    """Suggest alternative providers/times when current provider has no slots."""
    settings: Settings = context.get("settings", Settings())

    constraints = params.get("constraints", {})
    if isinstance(constraints, str):
        try:
            constraints = json.loads(constraints)
        except (json.JSONDecodeError, TypeError):
            constraints = {}
    service = constraints.get("service", "")
    location = constraints.get("location", "")
    date_start_str = constraints.get("date_range_start", "")
    exclude_providers: list[str] = constraints.get("exclude_providers", [])

    # Infer from campaign if missing
    campaign_id = context.get("campaign_id", "")
    if campaign_id and (not service or not location):
        from app.store import store
        campaign = await store.get_campaign(campaign_id)
        if campaign:
            service = service or campaign.request.service
            location = location or campaign.request.location
            if not date_start_str:
                date_start_str = campaign.request.date_range_start.isoformat()

    providers = await search_providers(service, location, settings)
    filtered = [p for p in providers if p.id not in exclude_providers][:3]

    suggestions = []
    for p in filtered:
        suggestions.append({
            "provider_name": p.name,
            "provider_id": p.id,
            "rating": p.rating,
            "estimated_availability": "Call to check",
        })

    return {"suggestions": suggestions}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

TOOLS: dict[str, Any] = {
    "calendar_check": calendar_check,
    "validate_slot": validate_slot,
    "available_slots": available_slots,
    "distance_check": distance_check,
    "log_event": log_event,
    "provider_lookup": provider_lookup,
    "propose_alternatives": propose_alternatives,
}


async def dispatch_tool(
    tool_name: str,
    params: dict,
    context: dict,
) -> tuple[str, bool]:
    """Dispatch a tool call and return (result_json_string, is_error).

    Returns a JSON string suitable for the ElevenLabs client_tool_result
    message, and a boolean indicating if an error occurred.
    """
    handler = TOOLS.get(tool_name)
    if handler is None:
        logger.warning("Unknown tool called: %s", tool_name)
        return json.dumps({"error": f"Unknown tool: {tool_name}"}), True

    try:
        result = await handler(params, context)
        return json.dumps(result, default=str), False
    except Exception:
        logger.exception("Tool %s failed", tool_name)
        return json.dumps({"error": f"Tool {tool_name} encountered an error"}), True
