# CallPilot Backend

Agentic Voice AI for Autonomous Appointment Scheduling. This FastAPI backend
places outbound phone calls via Twilio, bridges audio to an ElevenLabs
Conversational AI agent that negotiates appointment slots, scores the offers,
and returns a ranked shortlist.

Here is the link to the ElevenLabs AI agent I created to look for available appointment slots: https://elevenlabs.io/app/talk-to?agent_id=agent_8301kgxdsjgafq5ryv9s8kz780d8&branch_id=agtbrch_1601kgxdsk5fffhb69e8wm8vtfre

## Post-Hackathon Updates

The following capabilities were added after the initial hackathon build:

- **Browser geolocation**: Users can grant location permissions to automatically
  detect their position, which is reverse-geocoded via Nominatim and displayed
  in the search form.
- **Manual address input**: Users can type a city, neighbourhood, address, or
  postcode. The backend uses this text (or the precise coordinates from
  geolocation) to search for real providers.
- **Real provider search via Google Places**: When enabled, the backend queries
  Google Places Nearby Search (with coordinates) or Text Search (with text) to
  find real healthcare providers, including their names, addresses, phone
  numbers, ratings, and coordinates.
- **Interactive provider map**: The provider selection screen now includes a
  Leaflet/OpenStreetMap map showing provider pins and the user's search
  location. Selected providers are highlighted; deselected ones are dimmed.
- **Provider ID cache**: Providers returned during the initial search are cached
  in-memory by ID so that the campaign can retrieve the exact same providers the
  user selected, avoiding mismatches between different search API calls.

## Important: Simulated Calls Only

CallPilot's swarm calling feature places multiple parallel outbound calls to
providers simultaneously. **In the current setup, only simulated calls are
functional** for the following reasons:

1. **No Twilio Pro account**: Twilio's free/standard tier provides a single
   phone number, which can only sustain one concurrent outbound call. Parallel
   real calls would require multiple Twilio numbers (one per concurrent call),
   which requires a paid Twilio plan.
2. **Demo safety**: For demonstrations and development, we do not want to
   actually call real healthcare providers. Simulated calls replicate the full
   campaign flow -- provider discovery, parallel "calling", slot negotiation,
   calendar checking, scoring, and booking -- entirely in-process with realistic
   delays, without dialling any real phone numbers.

The server ships with `SIMULATED_CALLS=true` by default. Leave this enabled
unless you have a Twilio Pro account with multiple numbers and genuinely intend
to place real calls.

---

## Planned improvements in the future
1. I want to implement the call back feature, now it only implements the first
calling feature to ask for slots, but I have yet to implement the call back
to confirm booking feature.
2. Minor UI fixes.

---

## Quick Start

### 1. Prerequisites

- Python 3.11+ (3.12 recommended)
- (Optional) A Twilio account with a phone number -- only needed for real calls
- (Optional) An ElevenLabs account with a Conversational AI agent -- only needed for real calls
- (Optional) [ngrok](https://ngrok.com/) -- only needed for real calls
- (Optional) A Google Maps API key with Places and Distance Matrix enabled -- for real provider search

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
# --- Required for real calls (leave blank if using simulated only) ---
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_CALLER_ID=+15551234567
PUBLIC_BASE_URL=https://your-ngrok-url.ngrok-free.app
ELEVENLABS_API_KEY=your_elevenlabs_api_key
ELEVENLABS_AGENT_ID=your_agent_id

# --- Feature flags ---
SIMULATED_CALLS=true          # Keep true for demos; only set false with a Twilio Pro account
ALLOW_ALL_CORS=true            # Permissive CORS for frontend dev

# --- Google Places (recommended — enables real provider search) ---
USE_GOOGLE_PLACES=true
GOOGLE_PLACES_API_KEY=your_key   # Needs Places API enabled in Google Cloud Console

# --- Google Distance Matrix (optional — real travel-time estimates) ---
USE_GOOGLE_DISTANCE=true
GOOGLE_MAPS_API_KEY=your_key     # Needs Distance Matrix API enabled

# --- Google Calendar (optional) ---
USE_REAL_CALENDAR=false
GOOGLE_CREDENTIALS_JSON=path/to/service-account.json
GOOGLE_CALENDAR_ID=primary
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

### Call Mode Settings

```bash
# Get current server default and available modes
curl http://localhost:8000/settings/call-mode

# Toggle server default at runtime (no restart needed)
curl -X PUT "http://localhost:8000/settings/call-mode?mode=simulated"
curl -X PUT "http://localhost:8000/settings/call-mode?mode=real"
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
    "call_mode": "hybrid",
    "preferences": {
      "earliest_weight": 0.5,
      "rating_weight": 0.25,
      "distance_weight": 0.2,
      "preference_weight": 0.05
    }
  }'
# Returns 202: {"campaign_id": "abc123def456", "status": "running", "call_mode": "hybrid"}
```

> **`call_mode` values:** `auto` (default — uses server setting), `real`, `simulated`, `hybrid` (first call real, rest simulated).

### Poll Campaign Status

```bash
curl http://localhost:8000/campaigns/{campaign_id}
# Returns: {
#   "campaign_id": "...",
#   "status": "running|completed|failed",
#   "progress": { "total_providers": 10, "completed_calls": 4, ... },
#   "best": { ... } | null,
#   "ranked": [ ... ],
#   "debug": { "call_mode": "hybrid", "scoring": { ... }, "provider_outcomes": { ... } }
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
Frontend (React / Vite)
    │
    ├── Browser geolocation ──► Nominatim reverse-geocode
    │
    ├── POST /providers/search ──► FastAPI ──► Google Places (Nearby / Text Search)
    │   (service, location, lat, lng)           or demo JSON fallback
    │
    ├── POST /campaigns ──────► FastAPI ──► Swarm Manager
    │   (with call_mode: auto|real|simulated|hybrid)
    ├── GET  /campaigns/{id} ──► FastAPI ──► In-Memory Store
    ├── PUT  /settings/call-mode ──► Toggle server default
    └── POST /campaigns/{id}/confirm ──► FastAPI
                                            │
                                   Swarm Manager
                                   (asyncio.Semaphore)
                                            │
                              ┌─────────────┼─────────────┐
                              │             │             │
                         Provider 1    Provider 2    Provider N
                              │             │             │
                  ┌───── call_mode? ─────┐  │             │
                  │                      │  │             │
             [real/hybrid-1st]    [simulated/hybrid-rest] │
                  │                      │                │
            Twilio Call           Simulated Call    Simulated Call
                  │               (2-6s delay)      (2-6s delay)
            TwiML Webhook              │                │
                  │                    │                │
            Media Stream WS      Offers generated  Offers generated
                  │              from calendar      from calendar
            ┌─────┴─────┐
            │ mulaw→PCM │
            └─────┬─────┘
                  │
            ElevenLabs WS
                  │
            Tool Calls
            (Calendar,
             Distance,
             Logging)
```

---

## Feature Flags

| Flag | Default | Description |
|------|---------|-------------|
| `SIMULATED_CALLS` | `true` | Server-wide default: use simulated receptionist instead of real Twilio + ElevenLabs. **Keep `true` unless you have a Twilio Pro account.** Can be overridden per-campaign via `call_mode`. |
| `USE_GOOGLE_PLACES` | `false` | Use Google Places API for real provider search. **Recommended `true`** with a valid API key for real provider names, addresses, and map pins. Falls back to demo JSON if disabled or if the API call fails. |
| `USE_GOOGLE_DISTANCE` | `false` | Use Google Distance Matrix API for real driving-time estimates. Falls back to hash-based mock distances if disabled. |
| `USE_REAL_CALENDAR` | `false` | Use Google Calendar API instead of mock busy blocks. |

---

## Call Modes (Real vs. Simulated vs. Hybrid)

Since Twilio's free plan only provides a single phone number, you can't place
multiple parallel real calls. CallPilot supports **per-campaign call modes** so
you can demo the parallel calling functionality without needing extra numbers.

### Available Modes

| Mode | Description |
|------|-------------|
| `auto` | **(default)** Uses the server-wide `SIMULATED_CALLS` env var to decide. |
| `real` | Every call goes through Twilio + ElevenLabs. Requires one Twilio number per parallel call. |
| `simulated` | All calls are simulated locally with realistic delays (2–6 seconds). No Twilio needed. |
| `hybrid` | The **first** call is a real Twilio call; all remaining calls run as simulated calls in parallel. Best for demos on a single Twilio number. |

### Setting the Mode Per-Campaign

Pass `call_mode` in the campaign request body:

```json
{
  "service": "dentist",
  "location": "San Francisco",
  "call_mode": "hybrid",
  "..."
}
```

The response includes the effective mode that was used:

```json
{"campaign_id": "abc123def456", "status": "running", "call_mode": "hybrid"}
```

### Toggling the Server-Wide Default at Runtime

You can change the default without restarting the server:

```bash
# Check current mode
curl http://localhost:8000/settings/call-mode

# Switch to simulated (all campaigns using call_mode=auto will simulate)
curl -X PUT "http://localhost:8000/settings/call-mode?mode=simulated"

# Switch to real
curl -X PUT "http://localhost:8000/settings/call-mode?mode=real"
```

### Recommended Setup for Demos

1. Keep `SIMULATED_CALLS=true` in `.env` -- this ensures no real phone calls
   are placed to providers.
2. Enable `USE_GOOGLE_PLACES=true` with a valid API key so the search returns
   real provider names, addresses, and map pins.
3. Use the default `call_mode: "auto"` (or explicitly `"simulated"`) when
   creating campaigns. The full parallel campaign flow runs end-to-end --
   provider discovery, simultaneous "calls", slot negotiation, calendar
   checking, scoring, and booking -- all without dialling a single real number.
4. For best results, select 5+ providers and a date range spanning 3+ days to
   ensure the simulation produces available time slots.

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
callpilot/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, all endpoints
│   │   ├── config.py             # Pydantic Settings (env vars)
│   │   ├── schemas.py            # Pydantic models (Provider, SlotOffer, etc.)
│   │   ├── store.py              # In-memory campaign & call state (file-backed)
│   │   ├── logging_utils.py      # Structured JSON logging
│   │   ├── data/
│   │   │   └── providers_demo.json  # 12 demo providers (fallback)
│   │   ├── services/
│   │   │   ├── providers.py      # Provider search (demo + Google Places) + ID cache
│   │   │   ├── calendar.py       # Calendar service (mock + Google Calendar)
│   │   │   ├── distance.py       # Distance estimation (mock + Google Distance Matrix)
│   │   │   └── scoring.py        # Weighted scoring engine
│   │   ├── telephony/
│   │   │   ├── twilio_client.py  # Outbound call creation via Twilio SDK
│   │   │   ├── twiml.py          # TwiML generation (Say + Connect Stream)
│   │   │   ├── audio.py          # Audio transcoding (mulaw <-> PCM)
│   │   │   └── media_stream.py   # Twilio Media Stream WS handler + ElevenLabs bridge
│   │   ├── voice/
│   │   │   ├── eleven_client.py  # ElevenLabs Conversational AI WS client
│   │   │   ├── tools_registry.py # Tool dispatch for agent tool calls
│   │   │   └── prompts.py        # Agent system prompt builder
│   │   └── swarm/
│   │       ├── models.py         # CallOutcome enum, ProviderCallResult
│   │       └── manager.py        # Campaign orchestrator (parallel calls + scoring)
│   ├── tests/
│   │   ├── test_scoring.py       # Scoring engine tests
│   │   └── test_api.py           # API endpoint tests (mocked telephony)
│   ├── pyproject.toml
│   └── README.md
├── frontend/
│   └── src/
│       └── components/
│           ├── LocationInput.tsx  # Geolocation + manual address input
│           ├── ProviderMap.tsx    # Leaflet/OpenStreetMap provider map
│           ├── ProviderSelection.tsx  # Provider list + map integration
│           └── SearchForm.tsx     # Main search form with location support
```
