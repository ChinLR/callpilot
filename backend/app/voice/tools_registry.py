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

from app.config import Settings
from app.services.calendar import get_calendar_service
from app.services.distance import get_distance_service
from app.services.providers import search_providers

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def calendar_check(params: dict, context: dict) -> dict:
    """Check if a time slot is free on the user's calendar."""
    settings: Settings = context.get("settings", Settings())
    calendar = get_calendar_service(settings)

    start_str = params.get("start", "")
    end_str = params.get("end", "")

    try:
        start = datetime.fromisoformat(start_str)
        end = datetime.fromisoformat(end_str)
    except (ValueError, TypeError):
        return {"free": False, "error": "Invalid datetime format"}

    free = await calendar.is_free(start, end)
    return {"free": free}


async def validate_slot(params: dict, context: dict) -> dict:
    """Validate a slot: must be calendar-free and within the campaign's date range."""
    settings: Settings = context.get("settings", Settings())
    calendar = get_calendar_service(settings)

    start_str = params.get("start", "")
    end_str = params.get("end", "")

    try:
        start = datetime.fromisoformat(start_str)
        end = datetime.fromisoformat(end_str)
    except (ValueError, TypeError):
        return {"ok": False, "reason": "Invalid datetime format"}

    free = await calendar.is_free(start, end)
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
    exclude_ids: list[str] = params.get("exclude_ids", [])

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


async def propose_alternatives(params: dict, context: dict) -> dict:
    """Suggest alternative providers/times when current provider has no slots."""
    settings: Settings = context.get("settings", Settings())

    constraints = params.get("constraints", {})
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
