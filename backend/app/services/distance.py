"""Distance estimation — mock hash-based + optional Google Distance Matrix."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Protocol

import httpx

from app.config import Settings
from app.schemas import Provider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class DistanceService(Protocol):
    async def estimate_travel_minutes(
        self, origin: str, provider: Provider
    ) -> int: ...


# ---------------------------------------------------------------------------
# Mock distance (deterministic, hash-based)
# ---------------------------------------------------------------------------


class MockDistanceService:
    """Return a stable travel time in 5–40 min derived from provider.id."""

    async def estimate_travel_minutes(
        self, origin: str, provider: Provider
    ) -> int:
        h = int(hashlib.sha256(provider.id.encode()).hexdigest(), 16)
        return 5 + (h % 36)


# ---------------------------------------------------------------------------
# Google Distance Matrix (feature-flagged)
# ---------------------------------------------------------------------------

_distance_cache: dict[str, tuple[float, int]] = {}
_DISTANCE_TTL = 3600  # 1 hour


class GoogleDistanceService:
    """Real travel time via Google Distance Matrix API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def estimate_travel_minutes(
        self, origin: str, provider: Provider
    ) -> int:
        cache_key = f"{origin}|{provider.id}"
        cached = _distance_cache.get(cache_key)
        if cached and (time.time() - cached[0]) < _DISTANCE_TTL:
            return cached[1]

        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            "origins": origin,
            "destinations": f"{provider.lat},{provider.lng}",
            "mode": "driving",
            "key": self._api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            element = data["rows"][0]["elements"][0]
            if element.get("status") != "OK":
                raise ValueError(f"Element status: {element.get('status')}")

            minutes = element["duration"]["value"] // 60
            _distance_cache[cache_key] = (time.time(), minutes)
            return minutes
        except Exception:
            logger.exception(
                "Google Distance Matrix failed for %s; falling back to mock",
                provider.id,
            )
            mock = MockDistanceService()
            return await mock.estimate_travel_minutes(origin, provider)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_distance_service(settings: Settings | None = None) -> DistanceService:
    """Return real or mock distance service based on config."""
    if settings and settings.use_google_distance and settings.google_maps_api_key:
        logger.info("Using Google Distance Matrix")
        return GoogleDistanceService(settings.google_maps_api_key)  # type: ignore[return-value]
    return MockDistanceService()  # type: ignore[return-value]
