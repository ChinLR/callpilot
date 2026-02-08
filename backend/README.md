# CallPilot Backend

Agentic Voice AI for Autonomous Appointment Scheduling. This FastAPI backend
places outbound phone calls via Twilio, bridges audio to an ElevenLabs
Conversational AI agent that negotiates appointment slots, scores the offers,
and returns a ranked shortlist.

## Quick Start

### 1. Prerequisites

- Python 3.11+ (3.12 recommended)
- A Twilio account with a phone number
- An ElevenLabs account with a Conversational AI agent configured
- [ngrok](https://ngrok.com/) (or similar) for exposing your local server to Twilio

### 2. Install

```bash
cd callpilot/backend
pip install -e ".[dev]"
```

> **Note:** `python-multipart` is required for Twilio webhook form parsing and is
> included in the project dependencies. If you see an error about
> `python-multipart` not being installed, run:
>
> ```bash
> pip install python-multipart
> ```

For Google integrations (Calendar, Places, Distance Matrix):

```bash
pip install -e ".[dev,google]"
```

### 3. Environment Variables

Create a `.env` file in `callpilot/backend/`:

```env
# --- Required for real calls ---
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_CALLER_ID=+15551234567
PUBLIC_BASE_URL=https://your-ngrok-url.ngrok-free.app
ELEVENLABS_API_KEY=your_elevenlabs_api_key
ELEVENLABS_AGENT_ID=your_agent_id

# --- Feature flags ---
SIMULATED_CALLS=true          # Set to false to use real Twilio + ElevenLabs
ALLOW_ALL_CORS=true            # Permissive CORS for frontend dev

# --- Google integrations (all optional, default off) ---
USE_REAL_CALENDAR=false
GOOGLE_CREDENTIALS_JSON=path/to/service-account.json
GOOGLE_CALENDAR_ID=primary

USE_GOOGLE_PLACES=false
GOOGLE_PLACES_API_KEY=your_key

USE_GOOGLE_DISTANCE=false
GOOGLE_MAPS_API_KEY=your_key
```

### 4. Expose with ngrok

Twilio needs a public HTTPS URL to hit your webhooks:

```bash
ngrok http 8000
```

Copy the `https://...ngrok-free.app` URL and set it as `PUBLIC_BASE_URL` in `.env`.

### 5. Run

```bash
cd callpilot/backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The server starts at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

### 6. Run Tests

```bash
cd callpilot/backend
python3 -m pytest tests/ -v
```

---

## API Endpoints

### Health Check

```bash
curl http://localhost:8000/health
# {"ok": true}
```

### Start a Campaign

```bash
curl -X POST http://localhost:8000/campaigns \
  -H "Content-Type: application/json" \
  -d '{
    "service": "dentist",
    "location": "San Francisco",
    "date_range_start": "2025-03-15T08:00:00Z",
    "date_range_end": "2025-03-20T18:00:00Z",
    "duration_min": 30,
    "max_providers": 10,
    "max_parallel": 5,
    "preferences": {
      "earliest_weight": 0.5,
      "rating_weight": 0.25,
      "distance_weight": 0.2,
      "preference_weight": 0.05
    }
  }'
# Returns 202: {"campaign_id": "abc123def456", "status": "running"}
```

### Poll Campaign Status

```bash
curl http://localhost:8000/campaigns/{campaign_id}
# Returns: {
#   "campaign_id": "...",
#   "status": "running|completed|failed",
#   "progress": { "total_providers": 10, "completed_calls": 4, ... },
#   "best": { ... } | null,
#   "ranked": [ ... ],
#   "debug": { ... }
# }
```

### Confirm a Slot

```bash
curl -X POST http://localhost:8000/campaigns/{campaign_id}/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "provider_id": "prov_bright_smile",
    "start": "2025-03-15T10:00:00Z",
    "end": "2025-03-15T10:30:00Z",
    "user_contact": { "name": "Jane Doe", "phone": "+15559999999" }
  }'
# Returns: { "campaign_id": "...", "confirmed": true, "confirmation_ref": "CONF-A1B2C3D4" }
```

---

## Twilio Webhook Routes

These routes are called by Twilio, not by the frontend.

### POST /twilio/voice

**Called by:** Twilio when an outbound call connects.

**Purpose:** Returns TwiML that says a brief disclosure then connects a
bidirectional Media Stream to the backend's WebSocket.

**Query params:** `campaign_id`, `provider_id` (set when creating the call).

**TwiML returned:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Joanna">This is an automated assistant calling to schedule an appointment.</Say>
  <Connect>
    <Stream url="wss://your-public-url/twilio/stream/{call_sid}?campaign_id=...&amp;provider_id=..." />
  </Connect>
</Response>
```

### POST /twilio/voice/status

**Called by:** Twilio for call lifecycle events (initiated, ringing, answered,
completed, busy, no-answer, failed).

**Purpose:** Updates call status in the store. If the call ends in a terminal
failure state (busy, no-answer, failed), it signals the swarm manager.

### WebSocket /twilio/stream/{call_id}

**Called by:** Twilio Media Streams after `<Connect><Stream>` in the TwiML.

**Purpose:** Bidirectional audio bridge. Receives mu-law 8 kHz audio from
Twilio, transcodes to PCM 16 kHz, and forwards to ElevenLabs. Receives
ElevenLabs agent audio (PCM 16 kHz), transcodes to mu-law 8 kHz, and sends
back to Twilio.

**Also handles:**
- ElevenLabs tool calls (calendar_check, distance_check, etc.)
- Ping/pong keepalive
- Transcript capture
- Call completion signaling

---

## Architecture

```
Frontend (Lovable)
    │
    ├── POST /campaigns ──────► FastAPI ──► Swarm Manager
    ├── GET  /campaigns/{id} ──► FastAPI ──► In-Memory Store
    └── POST /campaigns/{id}/confirm ──► FastAPI
                                            │
                                   Swarm Manager
                                   (asyncio.Semaphore)
                                            │
                              ┌─────────────┼─────────────┐
                              │             │             │
                        Twilio Call 1  Twilio Call 2  Twilio Call N
                              │             │             │
                        TwiML Webhook   TwiML Webhook  TwiML Webhook
                              │             │             │
                        Media Stream WS  Media Stream WS  ...
                              │             │
                        ┌─────┴─────┐  ┌────┴─────┐
                        │ mulaw→PCM │  │ PCM→mulaw│
                        └─────┬─────┘  └────┬─────┘
                              │             │
                        ElevenLabs WS  ElevenLabs WS
                              │             │
                        Tool Calls ─── Tool Calls
                        (Calendar,     (Calendar,
                         Distance,      Distance,
                         Logging)       Logging)
```

---

## Feature Flags

| Flag | Default | Description |
|------|---------|-------------|
| `SIMULATED_CALLS` | `true` | Use deterministic simulated receptionist instead of real Twilio + ElevenLabs |
| `USE_REAL_CALENDAR` | `false` | Use Google Calendar API instead of mock busy blocks |
| `USE_GOOGLE_PLACES` | `false` | Use Google Places API for provider search instead of demo JSON |
| `USE_GOOGLE_DISTANCE` | `false` | Use Google Distance Matrix API instead of hash-based mock |

---

## ElevenLabs Agent Setup

The ElevenLabs agent must have these **client tools** configured in the dashboard
with matching names and parameter schemas:

| Tool Name | Parameters | Description |
|-----------|-----------|-------------|
| `calendar_check` | `start` (string, ISO datetime), `end` (string, ISO datetime) | Check if time slot is free |
| `validate_slot` | `provider_id` (string), `start` (string), `end` (string) | Validate slot within date range |
| `distance_check` | `provider_id` (string) | Get estimated travel minutes |
| `log_event` | `message` (string), `data` (object) | Log call summary and offers |
| `provider_lookup` | `service` (string), `location` (string), `exclude_ids` (array) | Search alternative providers |
| `propose_alternatives` | `constraints` (object) | Get alternative suggestions |

All tools should have **"Wait for response"** enabled in the ElevenLabs dashboard.

---

## Project Structure

```
callpilot/backend/
├── app/
│   ├── main.py              # FastAPI app, all endpoints
│   ├── config.py             # Pydantic Settings (env vars)
│   ├── schemas.py            # Pydantic models (Provider, SlotOffer, etc.)
│   ├── store.py              # In-memory campaign & call state
│   ├── logging_utils.py      # Structured JSON logging
│   ├── data/
│   │   └── providers_demo.json  # 12 demo providers
│   ├── services/
│   │   ├── providers.py      # Provider search (demo + Google Places)
│   │   ├── calendar.py       # Calendar service (mock + Google Calendar)
│   │   ├── distance.py       # Distance estimation (mock + Google Distance Matrix)
│   │   └── scoring.py        # Weighted scoring engine
│   ├── telephony/
│   │   ├── twilio_client.py  # Outbound call creation via Twilio SDK
│   │   ├── twiml.py          # TwiML generation (Say + Connect Stream)
│   │   ├── audio.py          # Audio transcoding (mulaw <-> PCM)
│   │   └── media_stream.py   # Twilio Media Stream WS handler + ElevenLabs bridge
│   ├── voice/
│   │   ├── eleven_client.py  # ElevenLabs Conversational AI WS client
│   │   ├── tools_registry.py # Tool dispatch for agent tool calls
│   │   └── prompts.py        # Agent system prompt builder
│   └── swarm/
│       ├── models.py         # CallOutcome enum, ProviderCallResult
│       └── manager.py        # Campaign orchestrator (parallel calls + scoring)
├── tests/
│   ├── test_scoring.py       # Scoring engine tests
│   └── test_api.py           # API endpoint tests (mocked telephony)
├── pyproject.toml
└── README.md
```
