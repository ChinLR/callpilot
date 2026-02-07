"""TwiML generation for outbound calls."""

from __future__ import annotations

from twilio.twiml.voice_response import Connect, VoiceResponse


def build_twiml(stream_url: str) -> str:
    """Return TwiML XML that says a disclosure then connects a media stream.

    Args:
        stream_url: Full ``wss://`` URL for the Twilio media stream endpoint,
                    including any query parameters (campaign_id, provider_id).
    """
    response = VoiceResponse()

    # Brief disclosure
    response.say(
        "This is an automated assistant calling to schedule an appointment.",
        voice="Polly.Joanna",
    )

    # Connect bidirectional media stream
    connect = Connect()
    connect.stream(url=stream_url)
    response.append(connect)

    return str(response)
