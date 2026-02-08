"""Twilio Media Stream WebSocket handler — bridges audio to ElevenLabs.

Accepts bidirectional Twilio Media Streams, transcodes audio, and proxies
to/from an ElevenLabs Conversational AI WebSocket session.  Also handles
ElevenLabs tool calls by dispatching to the tools registry.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

from app.config import Settings
from app.schemas import SlotOffer
from app.store import ProviderCallResultData, store
from app.swarm.models import CallOutcome
from app.telephony.audio import mulaw_to_pcm16k, pcm16k_to_mulaw
from app.voice.eleven_client import create_eleven_session
from app.voice.tools_registry import dispatch_tool

logger = logging.getLogger(__name__)


async def handle_media_stream(
    websocket: WebSocket,
    call_id: str,
    campaign_id: str,
    provider_id: str,
    settings: Settings,
) -> None:
    """Handle a single Twilio Media Stream WebSocket connection.

    This is the main entry point called from the FastAPI WS route.
    """
    await websocket.accept()
    logger.info(
        "Twilio stream connected: call_id=%s campaign=%s provider=%s",
        call_id, campaign_id, provider_id,
    )

    stream_sid: str = ""
    transcript_parts: list[str] = []
    offers: list[SlotOffer] = []
    outcome = CallOutcome.FAILED

    eleven_ws = None

    try:
        # --- Resolve campaign context ---
        campaign = await store.get_campaign(campaign_id)
        if campaign is None:
            logger.error("Campaign %s not found for call %s", campaign_id, call_id)
            await websocket.close()
            return

        # Find the provider from campaign
        provider = None
        for p in campaign.providers:
            if p.id == provider_id:
                provider = p
                break

        # --- Create ElevenLabs session ---
        eleven_ws = await create_eleven_session(
            settings=settings,
            provider=provider,
            campaign=campaign,
        )
        if eleven_ws is None:
            logger.error("Failed to create ElevenLabs session for call %s", call_id)
            await websocket.close()
            return

        # Build tool context for dispatching
        tool_context = {
            "campaign_id": campaign_id,
            "provider_id": provider_id,
            "settings": settings,
        }

        # --- Concurrent bridge tasks ---
        stop_event = asyncio.Event()
        bridge_error = False  # Track whether either bridge task hit an error

        async def twilio_to_eleven() -> None:
            """Read Twilio WS messages and forward audio to ElevenLabs."""
            nonlocal stream_sid, bridge_error
            try:
                while not stop_event.is_set():
                    raw = await websocket.receive_text()
                    msg = json.loads(raw)
                    event = msg.get("event")

                    if event == "connected":
                        logger.debug("Twilio stream: connected event")

                    elif event == "start":
                        stream_sid = msg.get("streamSid", "")
                        logger.info(
                            "Twilio stream started: streamSid=%s callSid=%s",
                            stream_sid,
                            msg.get("start", {}).get("callSid", ""),
                        )

                    elif event == "media":
                        payload_b64 = msg.get("media", {}).get("payload", "")
                        if payload_b64 and eleven_ws:
                            pcm_b64 = mulaw_to_pcm16k(payload_b64)
                            await eleven_ws.send(json.dumps({
                                "user_audio_chunk": pcm_b64,
                            }))

                    elif event == "stop":
                        logger.info("Twilio stream stopped: call_id=%s", call_id)
                        stop_event.set()
                        return

                    elif event == "mark":
                        pass  # Acknowledgement of playback completion

            except WebSocketDisconnect:
                logger.info("Twilio WS disconnected: call_id=%s", call_id)
                stop_event.set()
            except Exception:
                logger.exception("Error in twilio_to_eleven for call %s", call_id)
                bridge_error = True
                stop_event.set()

        async def eleven_to_twilio() -> None:
            """Read ElevenLabs WS messages and forward audio / handle tools."""
            nonlocal bridge_error
            try:
                while not stop_event.is_set():
                    raw = await eleven_ws.recv()  # type: ignore[union-attr]
                    msg = json.loads(raw)
                    msg_type = msg.get("type", "")

                    if msg_type == "audio":
                        # ElevenLabs -> Twilio audio
                        audio_b64 = msg.get("audio_event", {}).get(
                            "audio_base_64", ""
                        )
                        if audio_b64 and stream_sid:
                            mulaw_b64 = pcm16k_to_mulaw(audio_b64)
                            await websocket.send_json({
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": mulaw_b64},
                            })

                    elif msg_type == "user_transcript":
                        text = msg.get("user_transcription_event", {}).get(
                            "user_transcript", ""
                        )
                        if text:
                            transcript_parts.append(f"Receptionist: {text}")
                            logger.debug("Transcript (user): %s", text)

                    elif msg_type == "agent_response":
                        text = msg.get("agent_response_event", {}).get(
                            "agent_response", ""
                        )
                        if text:
                            transcript_parts.append(f"Agent: {text}")
                            logger.debug("Transcript (agent): %s", text)

                    elif msg_type == "client_tool_call":
                        tool_data = msg.get("client_tool_call", {})
                        tool_name = tool_data.get("tool_name", "")
                        tool_call_id = tool_data.get("tool_call_id", "")
                        params = tool_data.get("parameters", {})

                        logger.info(
                            "Tool call: %s (id=%s) params=%s",
                            tool_name, tool_call_id, params,
                        )

                        result_str, is_error = await dispatch_tool(
                            tool_name, params, tool_context
                        )

                        # Parse log_event results for offers
                        if tool_name == "log_event" and not is_error:
                            _extract_offers(params, offers, provider_id)

                        # Send tool result back to ElevenLabs
                        await eleven_ws.send(json.dumps({  # type: ignore[union-attr]
                            "type": "client_tool_result",
                            "tool_call_id": tool_call_id,
                            "result": result_str,
                            "is_error": is_error,
                        }))

                    elif msg_type == "ping":
                        ping_event = msg.get("ping_event", {})
                        event_id = ping_event.get("event_id")
                        ping_ms = ping_event.get("ping_ms", 0)
                        if ping_ms:
                            await asyncio.sleep(ping_ms / 1000.0)
                        await eleven_ws.send(json.dumps({  # type: ignore[union-attr]
                            "type": "pong",
                            "event_id": event_id,
                        }))

                    elif msg_type == "interruption":
                        # Clear Twilio audio buffer on interruption
                        if stream_sid:
                            await websocket.send_json({
                                "event": "clear",
                                "streamSid": stream_sid,
                            })

                    elif msg_type == "conversation_initiation_metadata":
                        logger.info(
                            "ElevenLabs session confirmed: %s",
                            msg.get("conversation_initiation_metadata_event", {}),
                        )

            except Exception:
                logger.exception("Error in eleven_to_twilio for call %s", call_id)
                bridge_error = True
                stop_event.set()

        # Run both bridge directions concurrently
        await asyncio.gather(
            twilio_to_eleven(),
            eleven_to_twilio(),
            return_exceptions=True,
        )

        # Determine outcome — if a bridge task errored, report FAILED
        # unless we still managed to collect offers before the error.
        if bridge_error and not offers:
            outcome = CallOutcome.FAILED
        elif offers:
            outcome = CallOutcome.SUCCESS
        else:
            outcome = CallOutcome.COMPLETED_NO_MATCH

    except Exception:
        logger.exception("Media stream handler failed for call %s", call_id)
        outcome = CallOutcome.FAILED
    finally:
        # Close ElevenLabs WS
        if eleven_ws:
            try:
                await eleven_ws.close()
            except Exception:
                pass

        # Finalize call result and signal completion
        transcript = "\n".join(transcript_parts[-10:])  # last 10 lines
        result = ProviderCallResultData(
            provider_id=provider_id,
            call_sid=call_id,
            outcome=outcome.value,
            offers=offers,
            transcript_snippet=transcript[:500],
            notes=f"Call completed at {datetime.now(timezone.utc).isoformat()}",
        )

        # Signal the swarm manager that this call is done
        call_mapping = await store.get_call(call_id)
        if call_mapping:
            await store.complete_call(call_id, result)
        else:
            # If no call mapping (e.g. simulated), just log
            logger.info(
                "Call %s complete (no mapping): outcome=%s offers=%d",
                call_id, outcome.value, len(offers),
            )

        logger.info(
            "Media stream finalized: call_id=%s outcome=%s offers=%d",
            call_id, outcome.value, len(offers),
        )


def _extract_offers(
    params: dict,
    offers: list[SlotOffer],
    provider_id: str,
) -> None:
    """Try to extract slot offers from a log_event tool call payload."""
    try:
        data = params.get("data", {})
        if isinstance(data, str):
            data = json.loads(data)

        raw_offers = data.get("offers", [])
        for o in raw_offers:
            offers.append(
                SlotOffer(
                    provider_id=provider_id,
                    start=o["start"],
                    end=o["end"],
                    notes=o.get("notes", ""),
                    confidence=o.get("confidence", 0.8),
                )
            )
    except Exception:
        logger.debug("Could not extract offers from log_event params")
