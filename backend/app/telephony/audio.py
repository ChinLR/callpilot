"""Audio transcoding helpers for the Twilio <-> ElevenLabs bridge.

Twilio Media Streams: mu-law 8 kHz mono, base64-encoded
ElevenLabs Convai WS: PCM 16-bit 16 kHz mono, base64-encoded

We need bidirectional conversion:
  mulaw 8k  -->  pcm16 16k   (Twilio inbound  -> ElevenLabs input)
  pcm16 16k -->  mulaw 8k    (ElevenLabs output -> Twilio outbound)
"""

from __future__ import annotations

import base64

try:
    import audioop  # available in CPython 3.11-3.12
except ImportError:
    import audioop_lts as audioop  # type: ignore[no-redef]  # 3.13+ fallback


SAMPLE_WIDTH = 2  # 16-bit PCM


def mulaw_to_pcm16k(payload_b64: str) -> str:
    """Decode Twilio mu-law 8 kHz base64 -> PCM 16-bit 16 kHz base64."""
    mulaw_bytes = base64.b64decode(payload_b64)

    # mu-law -> linear PCM 16-bit @ 8 kHz
    pcm_8k = audioop.ulaw2lin(mulaw_bytes, SAMPLE_WIDTH)

    # Resample 8 kHz -> 16 kHz
    pcm_16k, _state = audioop.ratecv(
        pcm_8k, SAMPLE_WIDTH, 1, 8000, 16000, None
    )

    return base64.b64encode(pcm_16k).decode("ascii")


def pcm16k_to_mulaw(payload_b64: str) -> str:
    """Encode ElevenLabs PCM 16-bit 16 kHz base64 -> mu-law 8 kHz base64."""
    pcm_16k = base64.b64decode(payload_b64)

    # Resample 16 kHz -> 8 kHz
    pcm_8k, _state = audioop.ratecv(
        pcm_16k, SAMPLE_WIDTH, 1, 16000, 8000, None
    )

    # Linear PCM -> mu-law
    mulaw_bytes = audioop.lin2ulaw(pcm_8k, SAMPLE_WIDTH)

    return base64.b64encode(mulaw_bytes).decode("ascii")
