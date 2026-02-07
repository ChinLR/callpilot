"""In-memory campaign and call state management."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.schemas import (
    AppointmentRequest,
    CampaignProgress,
    CampaignResponse,
    CampaignStatusEnum,
    Provider,
    SlotOffer,
)


@dataclass
class ProviderCallResultData:
    """Lightweight call result stored in campaign state."""

    provider_id: str
    call_sid: str = ""
    outcome: str = ""
    offers: list[SlotOffer] = field(default_factory=list)
    transcript_snippet: str = ""
    notes: str = ""


@dataclass
class CampaignState:
    campaign_id: str
    request: AppointmentRequest
    status: CampaignStatusEnum = CampaignStatusEnum.running
    progress: CampaignProgress = field(default_factory=CampaignProgress)
    providers: list[Provider] = field(default_factory=list)
    call_results: list[ProviderCallResultData] = field(default_factory=list)
    ranked: list[SlotOffer] = field(default_factory=list)
    best: SlotOffer | None = None
    debug: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CallMapping:
    """Maps a Twilio call SID to its campaign / provider context."""

    call_sid: str
    campaign_id: str
    provider_id: str
    stream_sid: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completion_event: asyncio.Event = field(default_factory=asyncio.Event)
    result: ProviderCallResultData | None = None


class Store:
    """Thread-safe (async-safe) in-memory store for MVP."""

    def __init__(self) -> None:
        self.campaigns: dict[str, CampaignState] = {}
        self.calls: dict[str, CallMapping] = {}
        self._lock = asyncio.Lock()

    # ----- Campaign helpers ------------------------------------------------

    async def create_campaign(self, request: AppointmentRequest) -> CampaignState:
        campaign_id = uuid.uuid4().hex[:12]
        state = CampaignState(campaign_id=campaign_id, request=request)
        async with self._lock:
            self.campaigns[campaign_id] = state
        return state

    async def get_campaign(self, campaign_id: str) -> CampaignState | None:
        return self.campaigns.get(campaign_id)

    async def update_campaign(self, campaign_id: str, **kwargs: Any) -> None:
        async with self._lock:
            state = self.campaigns.get(campaign_id)
            if state is None:
                return
            for key, value in kwargs.items():
                setattr(state, key, value)
            state.updated_at = datetime.now(timezone.utc)

    # ----- Call helpers ----------------------------------------------------

    async def register_call(
        self,
        call_sid: str,
        campaign_id: str,
        provider_id: str,
    ) -> CallMapping:
        mapping = CallMapping(
            call_sid=call_sid,
            campaign_id=campaign_id,
            provider_id=provider_id,
        )
        async with self._lock:
            self.calls[call_sid] = mapping
        return mapping

    async def get_call(self, call_sid: str) -> CallMapping | None:
        return self.calls.get(call_sid)

    async def complete_call(
        self,
        call_sid: str,
        result: ProviderCallResultData,
    ) -> None:
        async with self._lock:
            mapping = self.calls.get(call_sid)
            if mapping is None:
                return
            mapping.result = result
            mapping.completion_event.set()


# Module-level singleton
store = Store()
