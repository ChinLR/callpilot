"""In-memory campaign and call state management with file-backed persistence.

Both OAuth tokens and campaign state are persisted to JSON files so they
survive server restarts (e.g. WatchFiles hot-reloads during development).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas import (
    AppointmentRequest,
    BookingConfirmation,
    CampaignProgress,
    CampaignResponse,
    CampaignStatusEnum,
    Provider,
    SlotOffer,
)

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
# Persist OAuth tokens to a JSON file so they survive server restarts.
_OAUTH_FILE = _DATA_DIR / "oauth_tokens.json"
# Persist campaigns so they survive WatchFiles / hot-reload restarts.
_CAMPAIGNS_FILE = _DATA_DIR / "campaigns.json"


# ---------------------------------------------------------------------------
# Google OAuth token storage
# ---------------------------------------------------------------------------


@dataclass
class GoogleOAuthToken:
    """Stores a user's Google OAuth credentials."""

    user_id: str
    access_token: str
    refresh_token: str
    token_uri: str = "https://oauth2.googleapis.com/token"
    scopes: list[str] = field(default_factory=lambda: [
        "https://www.googleapis.com/auth/calendar.readonly",
    ])
    expiry: datetime | None = None
    linked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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
    booking_confirmation: BookingConfirmation | None = None
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
    """Thread-safe (async-safe) in-memory store for MVP.

    Both OAuth tokens and campaigns are persisted to JSON files so they
    survive WatchFiles hot-reloads and normal restarts.
    """

    def __init__(self) -> None:
        self.campaigns: dict[str, CampaignState] = {}
        self.calls: dict[str, CallMapping] = {}
        self.oauth_tokens: dict[str, GoogleOAuthToken] = {}  # user_id → token
        self._lock = asyncio.Lock()
        self._load_oauth_tokens()
        self._load_campaigns()

    # ----- Campaign helpers ------------------------------------------------

    async def create_campaign(self, request: AppointmentRequest) -> CampaignState:
        campaign_id = uuid.uuid4().hex[:12]
        state = CampaignState(campaign_id=campaign_id, request=request)
        async with self._lock:
            self.campaigns[campaign_id] = state
            self._persist_campaigns()
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
            self._persist_campaigns()

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

    # ----- OAuth token helpers (file-backed) --------------------------------

    def _load_oauth_tokens(self) -> None:
        """Load OAuth tokens from disk at startup."""
        if not _OAUTH_FILE.exists():
            return
        try:
            raw = json.loads(_OAUTH_FILE.read_text())
            for uid, entry in raw.items():
                self.oauth_tokens[uid] = GoogleOAuthToken(
                    user_id=uid,
                    access_token=entry["access_token"],
                    refresh_token=entry.get("refresh_token", ""),
                    token_uri=entry.get("token_uri", "https://oauth2.googleapis.com/token"),
                    scopes=entry.get("scopes", [
                        "https://www.googleapis.com/auth/calendar.readonly",
                    ]),
                    linked_at=datetime.fromisoformat(entry["linked_at"])
                    if "linked_at" in entry
                    else datetime.now(timezone.utc),
                )
            logger.info(
                "Loaded %d OAuth token(s) from %s", len(self.oauth_tokens), _OAUTH_FILE,
            )
        except Exception:
            logger.exception("Failed to load OAuth tokens from %s", _OAUTH_FILE)

    def _persist_oauth_tokens(self) -> None:
        """Write current OAuth tokens to disk."""
        try:
            data = {}
            for uid, tok in self.oauth_tokens.items():
                data[uid] = {
                    "access_token": tok.access_token,
                    "refresh_token": tok.refresh_token,
                    "token_uri": tok.token_uri,
                    "scopes": tok.scopes,
                    "linked_at": tok.linked_at.isoformat(),
                }
            _OAUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
            _OAUTH_FILE.write_text(json.dumps(data, indent=2))
            logger.debug("Persisted %d OAuth token(s) to %s", len(data), _OAUTH_FILE)
        except Exception:
            logger.exception("Failed to persist OAuth tokens to %s", _OAUTH_FILE)

    async def save_oauth_token(self, token: GoogleOAuthToken) -> None:
        async with self._lock:
            self.oauth_tokens[token.user_id] = token
            self._persist_oauth_tokens()

    async def get_oauth_token(self, user_id: str) -> GoogleOAuthToken | None:
        return self.oauth_tokens.get(user_id)

    async def delete_oauth_token(self, user_id: str) -> bool:
        async with self._lock:
            removed = self.oauth_tokens.pop(user_id, None) is not None
            if removed:
                self._persist_oauth_tokens()
            return removed

    # ----- Campaign persistence (file-backed) --------------------------------

    def _serialize_campaign(self, state: CampaignState) -> dict[str, Any]:
        """Convert a CampaignState to a JSON-safe dict."""
        return {
            "campaign_id": state.campaign_id,
            "request": state.request.model_dump(mode="json"),
            "status": state.status.value,
            "progress": state.progress.model_dump(mode="json"),
            "providers": [p.model_dump(mode="json") for p in state.providers],
            "call_results": [
                {
                    "provider_id": cr.provider_id,
                    "call_sid": cr.call_sid,
                    "outcome": cr.outcome,
                    "offers": [o.model_dump(mode="json") for o in cr.offers],
                    "transcript_snippet": cr.transcript_snippet,
                    "notes": cr.notes,
                }
                for cr in state.call_results
            ],
            "ranked": [o.model_dump(mode="json") for o in state.ranked],
            "best": state.best.model_dump(mode="json") if state.best else None,
            "booking_confirmation": (
                state.booking_confirmation.model_dump(mode="json")
                if state.booking_confirmation
                else None
            ),
            "debug": state.debug,
            "created_at": state.created_at.isoformat(),
            "updated_at": state.updated_at.isoformat(),
        }

    def _deserialize_campaign(self, data: dict[str, Any]) -> CampaignState:
        """Reconstruct a CampaignState from a persisted dict."""
        status = CampaignStatusEnum(data["status"])

        # Campaigns that were running/booking when the server stopped have
        # lost their background tasks, so mark them as failed.
        if status in (CampaignStatusEnum.running, CampaignStatusEnum.booking):
            status = CampaignStatusEnum.failed

        return CampaignState(
            campaign_id=data["campaign_id"],
            request=AppointmentRequest(**data["request"]),
            status=status,
            progress=CampaignProgress(**data.get("progress", {})),
            providers=[Provider(**p) for p in data.get("providers", [])],
            call_results=[
                ProviderCallResultData(
                    provider_id=cr["provider_id"],
                    call_sid=cr.get("call_sid", ""),
                    outcome=cr.get("outcome", ""),
                    offers=[SlotOffer(**o) for o in cr.get("offers", [])],
                    transcript_snippet=cr.get("transcript_snippet", ""),
                    notes=cr.get("notes", ""),
                )
                for cr in data.get("call_results", [])
            ],
            ranked=[SlotOffer(**o) for o in data.get("ranked", [])],
            best=SlotOffer(**data["best"]) if data.get("best") else None,
            booking_confirmation=(
                BookingConfirmation(**data["booking_confirmation"])
                if data.get("booking_confirmation")
                else None
            ),
            debug=data.get("debug", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )

    def _load_campaigns(self) -> None:
        """Load persisted campaigns from disk at startup."""
        if not _CAMPAIGNS_FILE.exists():
            return
        try:
            raw = json.loads(_CAMPAIGNS_FILE.read_text())
            for cid, entry in raw.items():
                self.campaigns[cid] = self._deserialize_campaign(entry)
            logger.info(
                "Loaded %d campaign(s) from %s", len(self.campaigns), _CAMPAIGNS_FILE,
            )
        except Exception:
            logger.exception("Failed to load campaigns from %s", _CAMPAIGNS_FILE)

    def _persist_campaigns(self) -> None:
        """Write current campaigns to disk."""
        try:
            data = {
                cid: self._serialize_campaign(state)
                for cid, state in self.campaigns.items()
            }
            _CAMPAIGNS_FILE.parent.mkdir(parents=True, exist_ok=True)
            _CAMPAIGNS_FILE.write_text(json.dumps(data, indent=2, default=str))
            logger.debug("Persisted %d campaign(s) to %s", len(data), _CAMPAIGNS_FILE)
        except Exception:
            logger.exception("Failed to persist campaigns to %s", _CAMPAIGNS_FILE)


# Module-level singleton
store = Store()
