"""Calendar service — mock busy blocks + optional Google Calendar."""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import date, datetime, time, timedelta, timezone
from typing import Protocol

from app.config import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol (shared interface)
# ---------------------------------------------------------------------------


class CalendarService(Protocol):
    """Common interface implemented by both mock and real calendar."""

    async def is_free(self, start: datetime, end: datetime) -> bool: ...


# ---------------------------------------------------------------------------
# Mock calendar
# ---------------------------------------------------------------------------


def _date_hash(d: date) -> int:
    """Stable integer hash for a date string."""
    return int(hashlib.sha256(d.isoformat().encode()).hexdigest(), 16)


def _busy_blocks(d: date) -> list[tuple[datetime, datetime]]:
    """Return deterministic busy blocks for a given date.

    Always includes 12:00-13:00 lunch block.
    Adds one extra block derived from the date hash.
    """
    tz = timezone.utc
    blocks: list[tuple[datetime, datetime]] = []

    # Fixed lunch block
    blocks.append((
        datetime.combine(d, time(12, 0), tzinfo=tz),
        datetime.combine(d, time(13, 0), tzinfo=tz),
    ))

    # Extra block from date hash — maps to one of six 1-hour slots
    h = _date_hash(d) % 6
    extra_starts = [
        time(8, 0),
        time(9, 30),
        time(10, 0),
        time(14, 0),
        time(15, 30),
        time(16, 0),
    ]
    start_t = extra_starts[h]
    blocks.append((
        datetime.combine(d, start_t, tzinfo=tz),
        datetime.combine(d, start_t, tzinfo=tz) + timedelta(hours=1),
    ))

    return blocks


def _intervals_overlap(
    a_start: datetime, a_end: datetime,
    b_start: datetime, b_end: datetime,
) -> bool:
    return a_start < b_end and b_start < a_end


class MockCalendarService:
    """Deterministic mock calendar with stable busy blocks."""

    async def is_free(self, start: datetime, end: datetime) -> bool:
        # Ensure timezone-aware
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        current = start.date()
        end_date = end.date()
        while current <= end_date:
            for b_start, b_end in _busy_blocks(current):
                if _intervals_overlap(start, end, b_start, b_end):
                    return False
            current += timedelta(days=1)
        return True


# ---------------------------------------------------------------------------
# Google Calendar (feature-flagged)
# ---------------------------------------------------------------------------


class GoogleCalendarService:
    """Real Google Calendar integration via FreeBusy API."""

    def __init__(self, credentials_path: str, calendar_id: str) -> None:
        self._calendar_id = calendar_id
        self._service = self._build_service(credentials_path)

    @staticmethod
    def _build_service(credentials_path: str):  # type: ignore[return]
        """Build the Google Calendar API v3 service object."""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=["https://www.googleapis.com/auth/calendar.readonly"],
            )
            return build("calendar", "v3", credentials=creds)
        except Exception:
            logger.exception("Failed to build Google Calendar service")
            return None

    async def get_busy_blocks(
        self, time_min: datetime, time_max: datetime
    ) -> list[tuple[datetime, datetime]]:
        """Query Google Calendar FreeBusy API for busy intervals."""
        if self._service is None:
            return []

        body = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "items": [{"id": self._calendar_id}],
        }
        try:
            result = self._service.freebusy().query(body=body).execute()
            busy_raw = (
                result.get("calendars", {})
                .get(self._calendar_id, {})
                .get("busy", [])
            )
            blocks = []
            for b in busy_raw:
                blocks.append((
                    datetime.fromisoformat(b["start"]),
                    datetime.fromisoformat(b["end"]),
                ))
            return blocks
        except Exception:
            logger.exception("Google Calendar FreeBusy query failed")
            return []

    async def is_free(self, start: datetime, end: datetime) -> bool:
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        # Add 15-minute buffer on both sides
        buffer = timedelta(minutes=15)
        blocks = await self.get_busy_blocks(start - buffer, end + buffer)
        for b_start, b_end in blocks:
            if _intervals_overlap(start, end, b_start, b_end):
                return False
        return True


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_calendar_service(settings: Settings | None = None) -> CalendarService:
    """Return the appropriate calendar service based on config."""
    if (
        settings
        and settings.use_real_calendar
        and settings.google_credentials_json
    ):
        try:
            svc = GoogleCalendarService(
                settings.google_credentials_json, settings.google_calendar_id
            )
            logger.info("Using Google Calendar (calendar_id=%s)", settings.google_calendar_id)
            return svc  # type: ignore[return-value]
        except Exception:
            logger.exception("Failed to init Google Calendar; falling back to mock")
    return MockCalendarService()  # type: ignore[return-value]
