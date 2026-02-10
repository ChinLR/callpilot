"""Provider directory — loads demo JSON or queries Google Places."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.schemas import Provider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Demo JSON provider store (cached at module level)
# ---------------------------------------------------------------------------

_DEMO_PATH = Path(__file__).resolve().parent.parent / "data" / "providers_demo.json"
_demo_cache: list[Provider] | None = None

# ---------------------------------------------------------------------------
# Provider-by-ID cache — remembers every provider returned by any search so
# the campaign can retrieve them later without re-searching.
# ---------------------------------------------------------------------------

_provider_id_cache: dict[str, Provider] = {}


def _cache_providers(providers: list[Provider]) -> None:
    """Store providers in the ID cache for later retrieval."""
    for p in providers:
        _provider_id_cache[p.id] = p


def get_cached_providers(ids: list[str]) -> list[Provider] | None:
    """Return providers from the ID cache.

    Returns a list if **all** requested IDs are found, otherwise ``None``
    (signalling the caller should fall back to a fresh search).
    """
    result = []
    for pid in ids:
        p = _provider_id_cache.get(pid)
        if p is None:
            return None  # cache miss — caller should re-search
        result.append(p)
    return result


def load_providers() -> list[Provider]:
    """Load providers from the bundled JSON file (cached)."""
    global _demo_cache
    if _demo_cache is None:
        with open(_DEMO_PATH) as fh:
            raw: list[dict[str, Any]] = json.load(fh)
        _demo_cache = [Provider(**p) for p in raw]
        logger.info("Loaded %d demo providers", len(_demo_cache))
    return _demo_cache


def _search_demo(service: str, location: str) -> list[Provider]:
    """Return demo providers whose services match (case-insensitive)."""
    service_lower = service.lower()
    return [
        p
        for p in load_providers()
        if any(service_lower in s.lower() for s in p.services)
    ]


# ---------------------------------------------------------------------------
# Google Places provider lookup (feature-flagged)
# ---------------------------------------------------------------------------

_places_cache: dict[str, tuple[float, list[Provider]]] = {}
_PLACES_TTL = 3600  # 1 hour


async def _search_places(
    service: str,
    location: str,
    radius_km: int,
    api_key: str,
    lat: float | None = None,
    lng: float | None = None,
) -> list[Provider]:
    """Query Google Places API and map results to Provider.

    When *lat*/*lng* are provided, uses Nearby Search for more accurate
    location-based results.  Otherwise falls back to Text Search.
    """
    cache_key = f"{service}|{location}|{radius_km}|{lat}|{lng}"
    cached = _places_cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _PLACES_TTL:
        return cached[1]

    # If we have coordinates, prefer Nearby Search
    if lat is not None and lng is not None:
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params: dict[str, Any] = {
            "location": f"{lat},{lng}",
            "radius": radius_km * 1000,
            "keyword": service,
            "key": api_key,
        }
    else:
        url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        params = {
            "query": f"{service} near {location}",
            "radius": radius_km * 1000,
            "key": api_key,
        }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    providers: list[Provider] = []
    results = data.get("results", [])[:20]

    for place in results:
        place_id = place.get("place_id", "")
        geom = place.get("geometry", {}).get("location", {})

        # Fetch phone number via Place Details
        phone = ""
        try:
            detail_url = "https://maps.googleapis.com/maps/api/place/details/json"
            detail_params = {
                "place_id": place_id,
                "fields": "international_phone_number",
                "key": api_key,
            }
            async with httpx.AsyncClient(timeout=10) as client:
                detail_resp = await client.get(detail_url, params=detail_params)
                detail_resp.raise_for_status()
                raw_phone = (
                    detail_resp.json()
                    .get("result", {})
                    .get("international_phone_number", "")
                )
                # Strip spaces/dashes to get E.164 format for Twilio
                phone = raw_phone.replace(" ", "").replace("-", "")
        except Exception:
            logger.warning("Could not fetch phone for place %s", place_id)

        providers.append(
            Provider(
                id=place_id,
                name=place.get("name", "Unknown"),
                phone=phone,
                address=place.get("formatted_address", ""),
                rating=place.get("rating", 0.0),
                lat=geom.get("lat", 0.0),
                lng=geom.get("lng", 0.0),
                services=[service],  # infer from query
            )
        )

    _places_cache[cache_key] = (time.time(), providers)
    _cache_providers(providers)
    logger.info("Google Places returned %d providers for '%s'", len(providers), service)
    return providers


# ---------------------------------------------------------------------------
# Public interface — dispatches based on settings
# ---------------------------------------------------------------------------


async def search_providers(
    service: str,
    location: str,
    settings: Settings | None = None,
    radius_km: int = 10,
    lat: float | None = None,
    lng: float | None = None,
) -> list[Provider]:
    """Return providers matching *service*.

    Uses Google Places when enabled, otherwise demo JSON.
    When *lat*/*lng* are provided they are forwarded to the Places API
    for more accurate location-based results.
    """
    if settings and settings.use_google_places and settings.google_places_api_key:
        try:
            results = await _search_places(
                service, location, radius_km, settings.google_places_api_key,
                lat=lat, lng=lng,
            )
            _cache_providers(results)
            return results
        except Exception:
            logger.exception("Google Places lookup failed; falling back to demo data")

    results = _search_demo(service, location)
    _cache_providers(results)
    return results
