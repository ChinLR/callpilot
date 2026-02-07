# CallPilot - AI-Powered Voice Agent for Autonomous Appointment Scheduling

An agentic Voice AI system that autonomously calls service providers, negotiates appointment slots in natural conversation, and selects the optimal match based on calendar availability, location, and user preferences.

## Tech Stack

### Backend

- **Python 3.11+** - Backend runtime
- **FastAPI** - High-performance async API framework
- **Twilio Programmable Voice** - Outbound phone calls + Media Streams
- **ElevenLabs Conversational AI** - Voice agent with tool-calling capabilities
- **Pydantic** - Data validation and settings management
- **asyncio** - Concurrent multi-provider call orchestration

### Frontend (Lovable - separate repo)

- Polls backend REST endpoints for campaign status
- No real-time WebSocket UI required for MVP

## Project Structure

```
callpilot/
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── main.py             # FastAPI app, all endpoints
│   │   ├── config.py           # Environment configuration
│   │   ├── schemas.py          # Pydantic data models
│   │   ├── store.py            # In-memory state management
│   │   ├── logging_utils.py    # Structured JSON logging
│   │   ├── data/
│   │   │   └── providers_demo.json
│   │   ├── services/
│   │   │   ├── providers.py    # Provider search (demo + Google Places)
│   │   │   ├── calendar.py     # Calendar (mock + Google Calendar)
│   │   │   ├── distance.py     # Distance (mock + Google Maps)
│   │   │   └── scoring.py      # Weighted scoring engine
│   │   ├── telephony/
│   │   │   ├── twilio_client.py  # Outbound call creation
│   │   │   ├── twiml.py         # TwiML generation
│   │   │   ├── audio.py         # Audio transcoding (mulaw <-> PCM)
│   │   │   └── media_stream.py  # Twilio <-> ElevenLabs audio bridge
│   │   ├── voice/
│   │   │   ├── eleven_client.py  # ElevenLabs WS client
│   │   │   ├── tools_registry.py # Agent tool dispatch
│   │   │   └── prompts.py       # Agent system prompts
│   │   └── swarm/
│   │       ├── models.py        # Call outcome models
│   │       └── manager.py       # Campaign orchestrator
│   ├── tests/
│   │   ├── test_scoring.py
│   │   └── test_api.py
│   ├── pyproject.toml
│   └── README.md
│
├── .gitignore
├── LICENSE
└── README.md
```

## Features

### Core (Implemented)

- Autonomous outbound calling via Twilio Programmable Voice
- ElevenLabs Conversational AI agent with tool-calling for mid-call decisions
- Multi-provider parallel outreach ("Swarm Mode") with configurable concurrency
- Real-time calendar checking to prevent double-booking
- Weighted scoring engine (earliest availability, rating, distance, preferences)
- Polling-friendly REST API for frontend integration
- Bidirectional audio bridge (Twilio Media Streams <-> ElevenLabs WebSocket)
- Audio transcoding (mu-law 8kHz <-> PCM 16kHz)
- Simulated receptionist mode for demo without live telephony

### Optional Integrations (Feature-Flagged)

- Google Calendar API for real user schedule
- Google Places API for live provider search with ratings
- Google Distance Matrix API for real travel times

## Quick Start

### Prerequisites

- Python 3.11+
- Twilio account (for real calls)
- ElevenLabs account (for voice agent)
- ngrok (for exposing webhooks)

### Setup

1. **Clone and navigate to project**

```bash
git clone https://github.com/YOUR_USERNAME/callpilot.git
cd callpilot
```

2. **Set up backend**

```bash
cd backend
pip install -e ".[dev]"
cp .env.example .env
# Edit .env with your API keys
```

3. **Expose with ngrok** (for real calls)

```bash
ngrok http 8000
# Copy the HTTPS URL to PUBLIC_BASE_URL in .env
```

4. **Run the server**

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

5. **Try it out**

```bash
# Start a campaign (simulated mode)
curl -X POST http://localhost:8000/campaigns \
  -H "Content-Type: application/json" \
  -d '{
    "service": "dentist",
    "location": "San Francisco",
    "date_range_start": "2025-03-15T08:00:00Z",
    "date_range_end": "2025-03-20T18:00:00Z"
  }'

# Poll for results
curl http://localhost:8000/campaigns/{campaign_id}
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/campaigns` | Start a scheduling campaign |
| `GET` | `/campaigns/{id}` | Poll campaign status & results |
| `POST` | `/campaigns/{id}/confirm` | Confirm a chosen slot |
| `POST` | `/twilio/voice` | TwiML webhook (Twilio calls this) |
| `POST` | `/twilio/voice/status` | Call status callback |
| `WS` | `/twilio/stream/{call_id}` | Bidirectional media stream |

## Architecture

```
User Request ──► FastAPI ──► Swarm Manager
                                  │
                    ┌─────────────┼─────────────┐
                    │             │             │
              Twilio Call 1  Twilio Call 2  Twilio Call N
                    │             │             │
              Media Stream    Media Stream    Media Stream
                    │             │             │
              ElevenLabs WS  ElevenLabs WS  ElevenLabs WS
                    │             │             │
              Tool Calls      Tool Calls     Tool Calls
              (Calendar,      (Calendar,     (Calendar,
               Distance,       Distance,      Distance,
               Scoring)        Scoring)       Scoring)
                    │             │             │
                    └─────────────┼─────────────┘
                                  │
                          Score & Rank ──► Ranked Shortlist
```

## Running Tests

```bash
cd backend
python3 -m pytest tests/ -v
```

## License

MIT
