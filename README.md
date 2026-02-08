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

### Frontend

- **React 18** - UI framework
- **TypeScript** - Type-safe development
- **Vite** - Fast build tooling and dev server
- **Tailwind CSS** - Utility-first styling
- **shadcn/ui** - Accessible component library (Radix UI primitives)
- **TanStack React Query** - Server state management and polling
- **React Router** - Client-side routing

## Project Structure

```
callpilot/
├── backend/                        # FastAPI application (Python)
│   ├── app/
│   │   ├── main.py                 # FastAPI app, all endpoints
│   │   ├── config.py               # Environment configuration
│   │   ├── schemas.py              # Pydantic data models
│   │   ├── store.py                # In-memory state management
│   │   ├── logging_utils.py        # Structured JSON logging
│   │   ├── auth.py                 # Google OAuth flow
│   │   ├── data/
│   │   │   └── providers_demo.json # 12 demo providers
│   │   ├── services/
│   │   │   ├── providers.py        # Provider search (demo + Google Places)
│   │   │   ├── calendar.py         # Calendar (mock + Google Calendar)
│   │   │   ├── distance.py         # Distance estimation (mock + Google Maps)
│   │   │   └── scoring.py          # Weighted scoring engine
│   │   ├── telephony/
│   │   │   ├── twilio_client.py    # Outbound call creation
│   │   │   ├── twiml.py            # TwiML generation
│   │   │   ├── audio.py            # Audio transcoding (mulaw <-> PCM)
│   │   │   └── media_stream.py     # Twilio <-> ElevenLabs audio bridge
│   │   ├── voice/
│   │   │   ├── eleven_client.py    # ElevenLabs WS client
│   │   │   ├── tools_registry.py   # Agent tool dispatch
│   │   │   └── prompts.py          # Agent system prompts
│   │   └── swarm/
│   │       ├── models.py           # Call outcome models
│   │       └── manager.py          # Campaign orchestrator
│   ├── tests/
│   ├── pyproject.toml
│   └── README.md                   # Detailed backend docs
│
├── frontend/                       # React SPA (TypeScript)
│   ├── src/
│   │   ├── pages/
│   │   │   ├── LandingPage.tsx     # Landing / hero page
│   │   │   └── BookAppointment.tsx # Main booking flow
│   │   ├── components/
│   │   │   ├── SearchForm.tsx      # Service + location search
│   │   │   ├── ProviderSelection.tsx # Provider picker
│   │   │   ├── CampaignProgress.tsx  # Live call progress
│   │   │   ├── AgentResults.tsx    # Ranked results display
│   │   │   ├── ConfirmSlot.tsx     # Slot confirmation
│   │   │   ├── BookingSuccess.tsx  # Booking confirmation
│   │   │   ├── GoogleCalendarButton.tsx # Google Calendar OAuth
│   │   │   └── ui/                 # shadcn/ui components
│   │   ├── hooks/
│   │   │   ├── useCampaign.ts      # Campaign polling logic
│   │   │   └── useGoogleAuth.ts    # Google OAuth hook
│   │   ├── lib/
│   │   │   └── api.ts              # Backend API client
│   │   └── types/
│   │       └── campaign.ts         # TypeScript type definitions
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.ts
│
├── .gitignore
├── LICENSE
└── README.md
```

## Features

### Core

- Autonomous outbound calling via Twilio Programmable Voice
- ElevenLabs Conversational AI agent with tool-calling for mid-call decisions
- Multi-provider parallel outreach ("Swarm Mode") with configurable concurrency
- Real-time calendar checking to prevent double-booking
- Weighted scoring engine (earliest availability, rating, distance, preferences)
- Bidirectional audio bridge (Twilio Media Streams <-> ElevenLabs WebSocket)
- Audio transcoding (mu-law 8kHz <-> PCM 16kHz)
- Simulated receptionist mode for demo without live telephony

### Frontend

- Service search with location input
- Provider selection before campaign launch
- Live campaign progress tracking with polling
- Ranked results display with scoring breakdown
- One-click slot confirmation flow
- Google Calendar integration for availability sync
- Responsive, modern UI built with shadcn/ui + Tailwind

### Optional Integrations (Feature-Flagged)

- Google Calendar API for real user schedule
- Google Places API for live provider search with ratings
- Google Distance Matrix API for real travel times
- Google OAuth for calendar authorization

## Quick Start

### Prerequisites

- **Backend:** Python 3.11+, Twilio account, ElevenLabs account, ngrok
- **Frontend:** Node.js 18+ and npm (or Bun)

### 1. Clone the repo

```bash
git clone https://github.com/ChinLR/callpilot.git
cd callpilot
```

### 2. Set up the backend

```bash
cd backend
pip install -e ".[dev]"
cp .env.example .env
# Edit .env with your API keys (see backend/README.md for full details)
```

### 3. Expose with ngrok (for real calls)

```bash
ngrok http 8000
# Copy the HTTPS URL to PUBLIC_BASE_URL in backend/.env
```

### 4. Run the backend

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API server starts at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.

### 5. Set up the frontend

```bash
cd frontend
npm install
```

### 6. Run the frontend

```bash
cd frontend
npm run dev
```

The frontend starts at `http://localhost:5173` (Vite default).

> **Note:** Update `API_BASE` in `frontend/src/lib/api.ts` to point to your backend URL (e.g. `http://localhost:8000` for local dev, or your ngrok URL for remote access).

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/campaigns` | Start a scheduling campaign |
| `GET` | `/campaigns/{id}` | Poll campaign status & results |
| `POST` | `/campaigns/{id}/confirm` | Confirm a chosen slot |
| `POST` | `/providers/search` | Search for providers by service + location |
| `GET` | `/settings/call-mode` | Get current call mode setting |
| `PUT` | `/settings/call-mode` | Toggle simulated/real call mode |
| `GET` | `/auth/google/authorize` | Start Google OAuth flow |
| `POST` | `/twilio/voice` | TwiML webhook (Twilio calls this) |
| `POST` | `/twilio/voice/status` | Call status callback |
| `WS` | `/twilio/stream/{call_id}` | Bidirectional media stream |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (React + Vite)                                        │
│                                                                 │
│  LandingPage ──► SearchForm ──► ProviderSelection               │
│                                      │                          │
│                                 POST /campaigns                 │
│                                      │                          │
│                              CampaignProgress                   │
│                           (polls GET /campaigns/{id})           │
│                                      │                          │
│                              AgentResults ──► ConfirmSlot       │
│                                              POST /confirm      │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                          REST / JSON
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  Backend (FastAPI)                                              │
│                                                                 │
│  POST /campaigns ──► Swarm Manager                              │
│                          │                                      │
│            ┌─────────────┼─────────────┐                        │
│            │             │             │                         │
│       Provider 1    Provider 2    Provider N                    │
│            │             │             │                         │
│    ┌── call_mode? ──┐    │             │                         │
│    │                │    │             │                         │
│  [real]        [simulated]            ...                       │
│    │                │                                           │
│  Twilio Call    Simulated Call                                  │
│    │            (2-6s delay)                                    │
│  Media Stream WS     │                                          │
│    │            Offers generated                                │
│  ElevenLabs WS                                                  │
│    │                                                            │
│  Tool Calls (Calendar, Distance, Scoring)                       │
│    │                                                            │
│  Score & Rank ──► Ranked Shortlist                              │
└─────────────────────────────────────────────────────────────────┘
```

## Running Tests

```bash
# Backend tests
cd backend
python3 -m pytest tests/ -v

# Frontend tests
cd frontend
npm test
```

## License

MIT
