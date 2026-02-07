"""Tests for the scoring engine."""

from datetime import datetime, timezone

from app.schemas import Provider, SlotOffer
from app.services.scoring import rank_offers, score_offer


def _make_provider(pid: str = "p1", rating: float = 4.0) -> Provider:
    return Provider(
        id=pid,
        name=f"Provider {pid}",
        phone="+15550000000",
        address="123 Main St",
        rating=rating,
        lat=37.77,
        lng=-122.42,
        services=["dentist"],
    )


def _make_offer(
    pid: str = "p1",
    hour: int = 10,
    day: int = 15,
) -> SlotOffer:
    return SlotOffer(
        provider_id=pid,
        start=datetime(2025, 3, day, hour, 0, tzinfo=timezone.utc),
        end=datetime(2025, 3, day, hour, 30, tzinfo=timezone.utc),
    )


WINDOW_START = datetime(2025, 3, 15, 8, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2025, 3, 20, 18, 0, tzinfo=timezone.utc)
DEFAULT_PREFS: dict[str, float] = {}


class TestScoreOffer:
    """Unit tests for score_offer."""

    def test_earlier_scores_higher(self) -> None:
        """An earlier appointment should score higher than a later one, all else equal."""
        provider = _make_provider()
        early = _make_offer(hour=9, day=15)
        late = _make_offer(hour=16, day=18)

        score_early, _ = score_offer(
            early, provider, 20, DEFAULT_PREFS, WINDOW_START, WINDOW_END
        )
        score_late, _ = score_offer(
            late, provider, 20, DEFAULT_PREFS, WINDOW_START, WINDOW_END
        )

        assert score_early > score_late, (
            f"Earlier slot ({score_early}) should beat later slot ({score_late})"
        )

    def test_higher_rating_scores_higher(self) -> None:
        """A provider with a higher rating should score better, same time/travel."""
        good_provider = _make_provider(pid="good", rating=4.8)
        bad_provider = _make_provider(pid="bad", rating=2.5)
        offer_good = _make_offer(pid="good", hour=10)
        offer_bad = _make_offer(pid="bad", hour=10)

        score_good, _ = score_offer(
            offer_good, good_provider, 20, DEFAULT_PREFS, WINDOW_START, WINDOW_END
        )
        score_bad, _ = score_offer(
            offer_bad, bad_provider, 20, DEFAULT_PREFS, WINDOW_START, WINDOW_END
        )

        assert score_good > score_bad, (
            f"Higher-rated ({score_good}) should beat lower-rated ({score_bad})"
        )

    def test_shorter_travel_scores_higher(self) -> None:
        """Shorter travel time should yield a higher score, same time/rating."""
        provider = _make_provider()
        offer = _make_offer()

        score_close, _ = score_offer(
            offer, provider, 5, DEFAULT_PREFS, WINDOW_START, WINDOW_END
        )
        score_far, _ = score_offer(
            offer, provider, 55, DEFAULT_PREFS, WINDOW_START, WINDOW_END
        )

        assert score_close > score_far, (
            f"Close provider ({score_close}) should beat far provider ({score_far})"
        )


class TestRankOffers:
    """Integration test for rank_offers."""

    def test_ranking_order(self) -> None:
        """Best offer should be ranked first."""
        p1 = _make_provider("p1", rating=4.5)
        p2 = _make_provider("p2", rating=3.0)

        early = _make_offer("p1", hour=9, day=15)
        late = _make_offer("p2", hour=16, day=19)

        providers_by_id = {"p1": p1, "p2": p2}
        travel_by_provider = {"p1": 10, "p2": 40}

        ranked, debug = rank_offers(
            [late, early],
            providers_by_id,
            travel_by_provider,
            DEFAULT_PREFS,
            WINDOW_START,
            WINDOW_END,
        )

        assert len(ranked) == 2
        assert ranked[0].provider_id == "p1", "p1 (early, high rating, close) should be #1"
        assert ranked[1].provider_id == "p2"
        assert ranked[0].score is not None
        assert ranked[0].score > ranked[1].score  # type: ignore[operator]
        assert "p1" in debug
