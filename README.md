# CallPilot - AI-Powered Voice Agent for Autonomous Appointment Scheduling

An agentic Voice AI system that autonomously calls service providers, negotiates appointment slots in natural conversation, and selects the optimal match based on calendar availability, location, and user preferences.

Here is the link to the ElevenLabs AI agent I created to look for available appointment slots (It doesn't really work on its own as it needs access to the user's calendar which can be connected on the CallPilot site) : https://elevenlabs.io/app/talk-to?agent_id=agent_8301kgxdsjgafq5ryv9s8kz780d8&branch_id=agtbrch_1601kgxdsk5fffhb69e8wm8vtfre

---

## Post-Hackathon Updates

The following capabilities were added after the initial hackathon build:

- **Browser geolocation**: Users can grant location permissions to automatically detect their position, which is reverse-geocoded via Nominatim and displayed in the search form.
- **Manual address input**: Users can type a city, neighbourhood, address, or postcode. The backend uses this text (or the precise coordinates from geolocation) to search for real providers.
- **Real provider search via Google Places**: When enabled, the backend queries Google Places Nearby Search (with coordinates) or Text Search (with text) to find real healthcare providers, including their names, addresses, phone numbers, ratings, and coordinates.
- **Interactive provider map**: The provider selection screen now includes a Leaflet/OpenStreetMap map showing provider pins and the user's search location. Selected providers are highlighted; deselected ones are dimmed.
- **Provider ID cache**: Providers returned during the initial search are cached in-memory by ID so that the campaign can retrieve the exact same providers the user selected, avoiding mismatches between different search API calls.

---

## Important: Simulated Calls Only

CallPilot's swarm calling feature places multiple parallel outbound calls to providers simultaneously. **In the current setup, only simulated calls are functional** for the following reasons:

1. **No Twilio Pro account**: Twilio's free/standard tier provides a single phone number, which can only sustain one concurrent outbound call. Parallel real calls would require multiple Twilio numbers (one per concurrent call), which requires a paid Twilio plan.
2. **Demo safety**: For demonstrations and development, we do not want to actually call real healthcare providers. Simulated calls replicate the full campaign flow -- provider discovery, parallel "calling", slot negotiation, calendar checking, scoring, and booking -- entirely in-process with realistic delays, without dialling any real phone numbers.

The server ships with `SIMULATED_CALLS=true` by default. Leave this enabled unless you have a Twilio Pro account with multiple numbers and genuinely intend to place real calls.

**Note** that I have tried and tested an actual call with the ElevenLabs agent. Here is the link with the recording and transcript of that call: https://drive.google.com/file/d/1FrA6vBfxsDQn2aEMOq2q1f-vInjf6ke4/view?usp=sharing

---

## Planned Future Improvements

1. **Callback to confirm booking**: Currently only the first calling feature (asking providers for available slots) is implemented. The callback feature to confirm the actual booking with the provider has yet to be built.
2. **Minor UI/UX fixes**: Polish the frontend interface, improve responsive layouts, and refine the user flow.
3. **Real Twilio integration at scale**: With a Twilio Pro account and multiple numbers, enable true parallel outbound calling to providers.
4. **Persistent provider data**: Replace the in-memory provider cache with a database-backed store so provider data survives server restarts.
5. **Expanded provider search**: Support more provider types and regions beyond healthcare, and integrate additional search APIs.

---

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
│   │   │   ├── providers.py        # Provider search (demo + Google Places) + ID cache
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
│   │   │   ├── LocationInput.tsx   # Geolocation + manual address input
│   │   │   ├── ProviderMap.tsx     # Leaflet/OpenStreetMap provider map
│   │   │   ├── ProviderSelection.tsx # Provider picker + map integration
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

- Service search with location input (manual address or browser geolocation)
- Interactive provider map with Leaflet/OpenStreetMap showing provider pins
- Provider selection before campaign launch with map highlighting
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

- **Backend:** Python 3.11+
- **Frontend:** Node.js 18+ and npm (or Bun)
- **Optional:** Twilio account + ElevenLabs account + ngrok (only needed for real calls)
- **Optional:** Google Maps API key with Places and Distance Matrix enabled (for real provider search)

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
│  LandingPage ──► SearchForm (geolocation / manual address)      │
│                       │                                         │
│                  POST /providers/search (service, location,     │
│                       │                  lat, lng)              │
│                       ▼                                         │
│              ProviderSelection + ProviderMap (Leaflet/OSM)      │
│                       │                                         │
│                  POST /campaigns                                │
│                       │                                         │
│               CampaignProgress                                  │
│            (polls GET /campaigns/{id})                           │
│                       │                                         │
│               AgentResults ──► ConfirmSlot                      │
│                               POST /confirm                     │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                          REST / JSON
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  Backend (FastAPI)                                              │
│                                                                 │
│  POST /providers/search ──► Google Places (Nearby / Text)       │
│                              or demo JSON fallback              │
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
