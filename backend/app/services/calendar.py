"""Calendar service — mock busy blocks + optional Google Calendar."""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Protocol
from zoneinfo import ZoneInfo

import httpx

from app.config import Settings

if TYPE_CHECKING:
    from app.store import GoogleOAuthToken

logger = logging.getLogger(__name__)


def _resolve_tz(tz_name: str | None = None) -> ZoneInfo | timezone:
    """Return a ZoneInfo for the given IANA name, falling back to UTC."""
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except (KeyError, Exception):
            logger.warning("Unknown timezone %r; falling back to UTC", tz_name)
    return ZoneInfo("UTC")

# Google Calendar API base
_GCAL_FREEBUSY_URL = "https://www.googleapis.com/calendar/v3/freeBusy"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CalendarUnavailableError(Exception):
    """Raised when calendar availability cannot be verified.

    Callers should treat this as "unknown" rather than assuming
    the slot is free, to prevent double-bookings.
    """


# ---------------------------------------------------------------------------
# Protocol (shared interface)
# ---------------------------------------------------------------------------


class CalendarService(Protocol):
    """Common interface implemented by both mock and real calendar."""

    async def is_free(self, start: datetime, end: datetime) -> bool: ...

    async def get_available_slots(
        self,
        day: date,
        business_start: int = 9,
        business_end: int = 17,
        min_slot_minutes: int = 30,
        tz_name: str | None = None,
    ) -> list[tuple[datetime, datetime]]: ...


# ---------------------------------------------------------------------------
# Mock calendar
# ---------------------------------------------------------------------------


def _date_hash(d: date) -> int:
    """Stable integer hash for a date string."""
    return int(hashlib.sha256(d.isoformat().encode()).hexdigest(), 16)


def _busy_blocks(d: date, tz: ZoneInfo | timezone | None = None) -> list[tuple[datetime, datetime]]:
    """Return deterministic busy blocks for a given date.

    Always includes 12:00-13:00 lunch block.
    Adds one extra block derived from the date hash.

    *tz* controls which timezone the wall-clock hours refer to.
    Defaults to UTC for backward compatibility, but callers should
    pass the user's local timezone so that "lunch at noon" means noon
    local time.
    """
    if tz is None:
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


def _compute_free_windows(
    day_start: datetime,
    day_end: datetime,
    busy_blocks: list[tuple[datetime, datetime]],
    min_slot_minutes: int = 30,
) -> list[tuple[datetime, datetime]]:
    """Compute free windows between *day_start* and *day_end*.

    Busy blocks must already be sorted by start time.
    Returns only windows >= *min_slot_minutes*.
    """
    free: list[tuple[datetime, datetime]] = []
    cursor = day_start

    for b_start, b_end in busy_blocks:
        # Clamp to business-hours window
        b_start = max(b_start, day_start)
        b_end = min(b_end, day_end)
        if b_start >= day_end or b_end <= day_start:
            continue  # outside window
        if cursor < b_start:
            gap = b_start - cursor
            if gap >= timedelta(minutes=min_slot_minutes):
                free.append((cursor, b_start))
        cursor = max(cursor, b_end)

    # Trailing free window after last busy block
    if cursor < day_end:
        gap = day_end - cursor
        if gap >= timedelta(minutes=min_slot_minutes):
            free.append((cursor, day_end))

    return free


class MockCalendarService:
    """Deterministic mock calendar with stable busy blocks."""

    def __init__(self, tz_name: str | None = None) -> None:
        self._tz = _resolve_tz(tz_name)

    async def is_free(self, start: datetime, end: datetime) -> bool:
        # Ensure timezone-aware — default to configured tz, not UTC
        if start.tzinfo is None:
            start = start.replace(tzinfo=self._tz)
        if end.tzinfo is None:
            end = end.replace(tzinfo=self._tz)

        current = start.date()
        end_date = end.date()
        while current <= end_date:
            for b_start, b_end in _busy_blocks(current, self._tz):
                if _intervals_overlap(start, end, b_start, b_end):
                    return False
            current += timedelta(days=1)
        return True

    async def get_available_slots(
        self,
        day: date,
        business_start: int = 9,
        business_end: int = 17,
        min_slot_minutes: int = 30,
        tz_name: str | None = None,
    ) -> list[tuple[datetime, datetime]]:
        """Return free windows on *day* during business hours.

        *tz_name* is an IANA timezone (e.g. ``America/Los_Angeles``).
        Business hours are interpreted in that timezone, and the returned
        datetimes carry the same zone so the caller (and ultimately the
        frontend) sees the correct wall-clock times.
        """
        tz = _resolve_tz(tz_name) if tz_name else self._tz
        day_start = datetime.combine(day, time(business_start, 0), tzinfo=tz)
        day_end = datetime.combine(day, time(business_end, 0), tzinfo=tz)

        # Busy blocks are generated in the user's local timezone,
        # so all datetimes share the same tzinfo.
        busy = sorted(_busy_blocks(day, tz), key=lambda b: b[0])
        windows = _compute_free_windows(day_start, day_end, busy, min_slot_minutes)
        return windows


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
            calendars = result.get("calendars", {})
            cal_data = calendars.get(self._calendar_id, {})
            if not cal_data.get("busy") and calendars:
                cal_data = next(iter(calendars.values()), {})
            busy_raw = cal_data.get("busy", [])
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
        # Naive datetimes are unlikely here (callers should localise),
        # but fall back to UTC to keep the API call valid.
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

    async def get_available_slots(
        self,
        day: date,
        business_start: int = 9,
        business_end: int = 17,
        min_slot_minutes: int = 30,
        tz_name: str | None = None,
    ) -> list[tuple[datetime, datetime]]:
        """Return free windows on *day* during business hours."""
        tz = _resolve_tz(tz_name)
        day_start = datetime.combine(day, time(business_start, 0), tzinfo=tz)
        day_end = datetime.combine(day, time(business_end, 0), tzinfo=tz)

        busy = await self.get_busy_blocks(day_start, day_end)
        busy = [(s.astimezone(tz), e.astimezone(tz)) for s, e in busy]
        busy.sort(key=lambda b: b[0])
        return _compute_free_windows(day_start, day_end, busy, min_slot_minutes)


# ---------------------------------------------------------------------------
# User OAuth Calendar (linked Google account)
# ---------------------------------------------------------------------------


class UserOAuthCalendarService:
    """Google Calendar access using a user's OAuth 2.0 tokens.

    Automatically refreshes the access token when needed.
    """

    def __init__(self, oauth_token: GoogleOAuthToken, settings: Settings) -> None:
        self._token = oauth_token
        self._settings = settings
        self._calendar_id = "primary"  # always the user's own calendar

    async def _ensure_fresh_token(self) -> str:
        """Return a valid access token, refreshing if expired."""
        # If we have a refresh token we can always refresh; for MVP we
        # optimistically try the existing access_token first and refresh
        # on 401.
        return self._token.access_token

    async def _refresh_access_token(self) -> str:
        """Use the refresh token to get a new access token."""
        if not self._token.refresh_token:
            raise RuntimeError("No refresh token available")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "client_id": self._settings.google_oauth_client_id,
                    "client_secret": self._settings.google_oauth_client_secret,
                    "refresh_token": self._token.refresh_token,
                    "grant_type": "refresh_token",
                },
            )

        if resp.status_code != 200:
            logger.error("Token refresh failed: %s %s", resp.status_code, resp.text)
            raise RuntimeError("Failed to refresh Google OAuth token")

        data = resp.json()
        self._token.access_token = data["access_token"]
        if "refresh_token" in data:
            self._token.refresh_token = data["refresh_token"]

        # Persist the refreshed token back to the store
        from app.store import store
        await store.save_oauth_token(self._token)

        logger.info("Refreshed OAuth token for user_id=%s", self._token.user_id)
        return self._token.access_token

    async def _freebusy_query(
        self, time_min: datetime, time_max: datetime, access_token: str
    ) -> list[tuple[datetime, datetime]]:
        """Call the Google Calendar FreeBusy API."""
        headers = {"Authorization": f"Bearer {access_token}"}
        body = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "items": [{"id": self._calendar_id}],
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(_GCAL_FREEBUSY_URL, json=body, headers=headers)

        if resp.status_code == 401:
            # Token expired — refresh and retry once
            new_token = await self._refresh_access_token()
            headers = {"Authorization": f"Bearer {new_token}"}
            async with httpx.AsyncClient() as client:
                resp = await client.post(_GCAL_FREEBUSY_URL, json=body, headers=headers)

        if resp.status_code != 200:
            raise CalendarUnavailableError(
                f"Google FreeBusy API returned {resp.status_code}: {resp.text}"
            )

        result = resp.json()
        # Google sometimes returns the actual email as the calendar key
        # instead of "primary", so fall back to the first calendar entry.
        calendars = result.get("calendars", {})
        cal_data = calendars.get(self._calendar_id, {})
        if not cal_data.get("busy") and calendars:
            cal_data = next(iter(calendars.values()), {})
        busy_raw = cal_data.get("busy", [])

        logger.info(
            "FreeBusy response: calendar_keys=%s busy_count=%d",
            list(calendars.keys()), len(busy_raw),
        )

        return [
            (datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"]))
            for b in busy_raw
        ]

    async def is_free(self, start: datetime, end: datetime) -> bool:
        """Check availability on the user's Google Calendar.

        Raises CalendarUnavailableError if the calendar cannot be reached,
        rather than silently assuming the slot is free.
        """
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        buffer = timedelta(minutes=15)
        try:
            blocks = await self._freebusy_query(
                start - buffer, end + buffer, self._token.access_token
            )
        except CalendarUnavailableError:
            raise  # already a structured error — let callers handle it
        except Exception as exc:
            raise CalendarUnavailableError(
                "Failed to verify calendar availability"
            ) from exc

        for b_start, b_end in blocks:
            if _intervals_overlap(start, end, b_start, b_end):
                return False
        return True

    async def get_available_slots(
        self,
        day: date,
        business_start: int = 9,
        business_end: int = 17,
        min_slot_minutes: int = 30,
        tz_name: str | None = None,
    ) -> list[tuple[datetime, datetime]]:
        """Return free windows on *day* during business hours.

        Raises CalendarUnavailableError if the calendar cannot be reached.
        """
        tz = _resolve_tz(tz_name)
        day_start = datetime.combine(day, time(business_start, 0), tzinfo=tz)
        day_end = datetime.combine(day, time(business_end, 0), tzinfo=tz)

        try:
            busy = await self._freebusy_query(
                day_start, day_end, self._token.access_token
            )
        except CalendarUnavailableError:
            raise
        except Exception as exc:
            raise CalendarUnavailableError(
                "Failed to fetch calendar availability"
            ) from exc

        busy = [(s.astimezone(tz), e.astimezone(tz)) for s, e in busy]
        busy.sort(key=lambda b: b[0])
        return _compute_free_windows(day_start, day_end, busy, min_slot_minutes)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


async def get_calendar_service_for_user(
    user_id: str,
    settings: Settings | None = None,
) -> CalendarService:
    """Return a calendar service that uses the user's linked Google account.

    Falls back to the default (service-account or mock) if no OAuth token
    is stored for this user.
    """
    if settings is None:
        from app.config import get_settings
        settings = get_settings()

    from app.store import store
    token = await store.get_oauth_token(user_id)

    if token is not None:
        logger.info("Using user-linked Google Calendar for user_id=%s", user_id)
        return UserOAuthCalendarService(token, settings)  # type: ignore[return-value]

    # Fall back to default
    return get_calendar_service(settings)


def get_calendar_service(settings: Settings | None = None) -> CalendarService:
    """Return the appropriate calendar service based on config.

    Prefers service-account integration if configured, otherwise mock.
    For user-specific OAuth calendars, use get_calendar_service_for_user().
    """
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
    tz_name = settings.default_timezone if settings else None
    return MockCalendarService(tz_name=tz_name)  # type: ignore[return-value]
