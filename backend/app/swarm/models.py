"""Swarm call outcome models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.schemas import SlotOffer


class CallOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    NO_ANSWER = "NO_ANSWER"
    BUSY = "BUSY"
    FAILED = "FAILED"
    NO_SLOTS = "NO_SLOTS"
    COMPLETED_NO_MATCH = "COMPLETED_NO_MATCH"


class ProviderCallResult(BaseModel):
    provider_id: str
    call_sid: str = ""
    outcome: CallOutcome = CallOutcome.FAILED
    offers: list[SlotOffer] = Field(default_factory=list)
    transcript_snippet: str = ""
    notes: str = ""
