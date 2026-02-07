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


# ---------------------------------------------------------------------------
# Appointment request (from frontend)
# ---------------------------------------------------------------------------

class AppointmentRequest(BaseModel):
    service: str
    location: str
    date_range_start: datetime
    date_range_end: datetime
    duration_min: int = 30
    preferences: dict[str, float] = Field(default_factory=dict)
    max_providers: int = 15
    max_parallel: int = 5


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
    completed = "completed"
    failed = "failed"


class CampaignProgress(BaseModel):
    total_providers: int = 0
    completed_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0


class CreateCampaignResponse(BaseModel):
    campaign_id: str
    status: CampaignStatusEnum


class CampaignResponse(BaseModel):
    campaign_id: str
    status: CampaignStatusEnum
    progress: CampaignProgress
    best: SlotOffer | None = None
    ranked: list[SlotOffer] = Field(default_factory=list)
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
