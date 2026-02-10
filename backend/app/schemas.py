"""Pydantic models shared across the application."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class Provider(BaseModel):
    id: str
    name: str
    phone: str
    address: str
    rating: float = Field(ge=0, le=5)
    lat: float
    lng: float
    services: list[str]


class ProviderPreview(BaseModel):
    """Provider info enriched with travel time, returned before calling."""
    id: str
    name: str
    phone: str
    address: str
    rating: float
    lat: float
    lng: float
    services: list[str]
    travel_minutes: int = 0


# ---------------------------------------------------------------------------
# Appointment request (from frontend)
# ---------------------------------------------------------------------------

class ProviderSearchRequest(BaseModel):
    """Request to search providers before starting a campaign."""
    service: str
    location: str
    lat: float | None = None  # optional user coordinates (from geolocation)
    lng: float | None = None
    max_providers: int = 15
    max_travel_minutes: int = 0  # 0 = no limit


class ProviderSearchResponse(BaseModel):
    """List of providers with distance info so the user can pick."""
    providers: list[ProviderPreview]


class CallMode(str, Enum):
    """How calls are placed for a campaign.

    - ``auto``      – use the server-wide ``SIMULATED_CALLS`` setting.
    - ``real``      – every call goes through Twilio.
    - ``simulated`` – every call is simulated locally (no Twilio needed).
    - ``hybrid``    – the **first** call is a real Twilio call; the
                      remaining calls are simulated so you can demo
                      parallel-call functionality on a single Twilio number.
    """
    auto = "auto"
    real = "real"
    simulated = "simulated"
    hybrid = "hybrid"


class AppointmentRequest(BaseModel):
    service: str
    location: str
    date_range_start: datetime
    date_range_end: datetime
    duration_min: int = 30
    preferences: dict[str, float] = Field(default_factory=dict)
    max_providers: int = 15
    max_parallel: int = 5
    max_travel_minutes: int = 0  # 0 = no limit; filter providers by travel time
    provider_ids: list[str] = Field(default_factory=list)  # if set, only call these providers
    user_id: str = ""  # links to Google Calendar when OAuth is connected
    timezone: str = ""  # IANA timezone (e.g. "America/Los_Angeles"); falls back to server default
    call_mode: CallMode = CallMode.auto  # override the server-wide SIMULATED_CALLS setting per campaign
    auto_book: bool = True  # automatically book the best slot after discovery
    client_name: str = ""  # name of the person the appointment is for
    client_phone: str = ""  # phone number of the client (for provider callback)


# ---------------------------------------------------------------------------
# Slot offer
# ---------------------------------------------------------------------------

class SlotOffer(BaseModel):
    provider_id: str
    start: datetime
    end: datetime
    notes: str = ""
    confidence: float = 1.0
    score: float | None = None


# ---------------------------------------------------------------------------
# Campaign lifecycle
# ---------------------------------------------------------------------------

class CampaignStatusEnum(str, Enum):
    running = "running"
    booking = "booking"        # Phase 2: agent is confirming the best slot
    booked = "booked"          # Phase 2 succeeded — appointment confirmed
    completed = "completed"    # Discovery done (auto_book=False or booking failed)
    failed = "failed"


class CampaignProgress(BaseModel):
    total_providers: int = 0
    calls_in_progress: int = 0
    completed_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0


class CreateCampaignResponse(BaseModel):
    campaign_id: str
    status: CampaignStatusEnum
    call_mode: str = ""  # effective call mode for this campaign


class BookingConfirmation(BaseModel):
    """Result of the autonomous booking phase."""
    provider_id: str
    start: datetime
    end: datetime
    confirmation_ref: str
    confirmed_at: datetime
    notes: str = ""
    client_name: str = ""  # name the appointment was booked under
    client_phone: str = ""  # client phone shared with the provider


class CampaignResponse(BaseModel):
    campaign_id: str
    status: CampaignStatusEnum
    progress: CampaignProgress
    best: SlotOffer | None = None
    ranked: list[SlotOffer] = Field(default_factory=list)
    booking: BookingConfirmation | None = None
    debug: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Confirm
# ---------------------------------------------------------------------------

class UserContact(BaseModel):
    name: str
    phone: str


class ConfirmRequest(BaseModel):
    provider_id: str
    start: datetime
    end: datetime
    user_contact: UserContact


class ConfirmResponse(BaseModel):
    campaign_id: str
    confirmed: bool
    confirmation_ref: str
