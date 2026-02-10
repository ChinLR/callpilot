"""Scoring engine — ranks slot offers by weighted criteria."""

from __future__ import annotations

from datetime import datetime

from app.schemas import Provider, SlotOffer


# Default weights
DEFAULT_EARLIEST_WEIGHT = 0.5
DEFAULT_RATING_WEIGHT = 0.25
DEFAULT_DISTANCE_WEIGHT = 0.2
DEFAULT_PREFERENCE_WEIGHT = 0.05


def score_offer(
    offer: SlotOffer,
    provider: Provider,
    travel_min: int,
    prefs: dict[str, float],
    window_start: datetime,
    window_end: datetime,
) -> tuple[float, dict[str, float]]:
    """Compute a single score in [0, 1] for an offer.

    Returns (score, breakdown_dict).
    """
    w_earliest = prefs.get("earliest_weight", DEFAULT_EARLIEST_WEIGHT)
    w_rating = prefs.get("rating_weight", DEFAULT_RATING_WEIGHT)
    w_distance = prefs.get("distance_weight", DEFAULT_DISTANCE_WEIGHT)
    w_pref = prefs.get("preference_weight", DEFAULT_PREFERENCE_WEIGHT)

    # --- Normalize each dimension to [0, 1] ---

    # Earliest: earlier start → higher score
    window_seconds = max((window_end - window_start).total_seconds(), 1)
    elapsed = (offer.start - window_start).total_seconds()
    earliest_score = max(0.0, 1.0 - elapsed / window_seconds)

    # Rating: [0..5] → [0..1]
    rating_score = provider.rating / 5.0

    # Distance: lower travel → higher score (cap at 60 min)
    distance_score = 1.0 - min(travel_min, 60) / 60.0

    # Preference placeholder (can be used for custom signals)
    pref_score = offer.confidence  # use confidence as proxy

    total = (
        w_earliest * earliest_score
        + w_rating * rating_score
        + w_distance * distance_score
        + w_pref * pref_score
    )

    breakdown = {
        "earliest": round(earliest_score, 4),
        "rating": round(rating_score, 4),
        "distance": round(distance_score, 4),
        "preference": round(pref_score, 4),
        "weights": {
            "earliest": w_earliest,
            "rating": w_rating,
            "distance": w_distance,
            "preference": w_pref,
        },
    }

    return round(total, 4), breakdown


def rank_offers(
    offers: list[SlotOffer],
    providers_by_id: dict[str, Provider],
    travel_by_provider: dict[str, int],
    prefs: dict[str, float],
    window_start: datetime,
    window_end: datetime,
) -> tuple[list[SlotOffer], dict[str, dict]]:
    """Score and sort offers descending.  Mutates offer.score in place.

    Scores are **relative**: the best offer gets 1.0 (100%) and the rest
    are scaled proportionally so users can compare options meaningfully.

    Returns (sorted_offers, debug_breakdown_by_provider_id).
    """
    scored: list[tuple[float, SlotOffer, dict]] = []

    for offer in offers:
        provider = providers_by_id.get(offer.provider_id)
        if provider is None:
            continue
        travel = travel_by_provider.get(offer.provider_id, 20)
        total, breakdown = score_offer(
            offer, provider, travel, prefs, window_start, window_end
        )
        offer.score = total
        scored.append((total, offer, breakdown))

    # Sort descending by raw score
    scored.sort(key=lambda t: t[0], reverse=True)

    # Normalize scores relative to the best offer (best = 1.0 / 100%)
    max_score = scored[0][0] if scored else 1.0
    if max_score > 0:
        for raw, offer, breakdown in scored:
            offer.score = round(raw / max_score, 4)
            breakdown["raw_score"] = raw
            breakdown["relative_score"] = offer.score

    sorted_offers = [t[1] for t in scored]

    # Group breakdowns by provider_id as a list so multiple offers
    # from the same provider are all preserved.
    debug: dict[str, list[dict]] = {}
    for t in scored:
        pid = t[1].provider_id
        debug.setdefault(pid, []).append(t[2])

    return sorted_offers, debug
