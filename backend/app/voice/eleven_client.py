"""ElevenLabs Conversational AI WebSocket client."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import httpx
import websockets

from app.config import Settings
from app.store import CampaignState
from app.schemas import Provider
from app.voice.prompts import build_system_prompt

logger = logging.getLogger(__name__)

# ElevenLabs Convai WS endpoint
ELEVEN_CONVAI_WS = "wss://api.elevenlabs.io/v1/convai/conversation"
ELEVEN_SIGNED_URL_API = "https://api.elevenlabs.io/v1/convai/conversation/get-signed-url"


async def _get_signed_url(agent_id: str, api_key: str) -> str | None:
    """Obtain a signed WebSocket URL from ElevenLabs (keeps API key server-side)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                ELEVEN_SIGNED_URL_API,
                params={"agent_id": agent_id},
                headers={"xi-api-key": api_key},
            )
            resp.raise_for_status()
            return resp.json().get("signed_url")
    except Exception:
        logger.exception("Failed to get ElevenLabs signed URL")
        return None


async def create_eleven_session(
    settings: Settings,
    provider: Provider | None = None,
    campaign: CampaignState | None = None,
) -> websockets.WebSocketClientProtocol | None:  # type: ignore[name-defined]
    """Open a WebSocket session to ElevenLabs Conversational AI.

    Sends conversation_initiation_client_data with dynamic variables
    tailored to the current provider and campaign context.  The agent's
    prompt on the ElevenLabs dashboard should use {{placeholders}} to
    incorporate these variables.

    Returns the connected websocket or None on failure.
    """
    agent_id = settings.elevenlabs_agent_id
    api_key = settings.elevenlabs_api_key

    if not agent_id or not api_key:
        logger.error("ElevenLabs credentials not configured")
        return None

    # Build dynamic prompt
    system_prompt = ""
    first_message = "Hello, I'm calling to check available appointment times."
    if provider and campaign:
        client_name = campaign.request.client_name or "a client"
        system_prompt = build_system_prompt(provider, campaign.request)
        first_message = (
            f"Hello, I'm calling on behalf of {client_name} who would like to "
            f"schedule a {campaign.request.service} appointment with "
            f"{provider.name}. Could you help me check what times you have available?"
        )

    # Get signed URL for security
    ws_url = await _get_signed_url(agent_id, api_key)
    if not ws_url:
        # Fallback to direct connection (less secure but functional)
        ws_url = f"{ELEVEN_CONVAI_WS}?agent_id={agent_id}"
        logger.warning("Using unsigned ElevenLabs WS URL (signed URL failed)")

    try:
        ws = await websockets.connect(  # type: ignore[attr-defined]
            ws_url,
            additional_headers={"Origin": "https://callpilot.app"},
        )

        # Send initiation message with dynamic variables.
        # These fill {{placeholders}} in the dashboard-configured prompt.
        now = datetime.now(timezone.utc)
        dynamic_vars = {
            "current_date": now.strftime("%A, %B %d, %Y"),
            "current_year": str(now.year),
        }
        if provider and campaign:
            req = campaign.request
            dynamic_vars.update({
                "provider_name": provider.name,
                "provider_address": provider.address,
                "service": req.service,
                "date_range_start": req.date_range_start.strftime("%A, %B %d, %Y"),
                "date_range_end": req.date_range_end.strftime("%A, %B %d, %Y"),
                "duration_min": str(req.duration_min),
                "client_name": req.client_name or "my client",
            })

        init_msg: dict = {
            "type": "conversation_initiation_client_data",
            "dynamic_variables": dynamic_vars,
        }

        # Pass prompt and first_message as dynamic variables rather than
        # conversation_config_override — the ElevenLabs agent config does
        # not allow client overrides, so we inject all context via
        # {{placeholders}} in the dashboard-configured prompt instead.
        if system_prompt:
            dynamic_vars["system_prompt"] = system_prompt
        if first_message:
            dynamic_vars["first_message"] = first_message

        await ws.send(json.dumps(init_msg))

        # Wait for confirmation
        raw = await ws.recv()
        msg = json.loads(raw)
        if msg.get("type") == "conversation_initiation_metadata":
            conv_id = msg.get("conversation_initiation_metadata_event", {}).get(
                "conversation_id", ""
            )
            logger.info("ElevenLabs session started: conversation_id=%s", conv_id)
        else:
            logger.warning(
                "Unexpected first message from ElevenLabs: %s", msg.get("type")
            )

        return ws

    except Exception:
        logger.exception("Failed to connect to ElevenLabs Convai WS")
        return None
