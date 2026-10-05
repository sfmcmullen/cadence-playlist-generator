# Running Playlist Generator

A FastAPI backend that generates running playlists from a workout plan. It converts pace and step length into a target running cadence, finds suitable Spotify tracks, enriches them with BPM data, ranks them against the target cadence, and creates a private Spotify playlist.

> **Status:** Backend foundation complete. The next step is a minimal React frontend for end-to-end testing.

## Architecture

```text
React frontend
      │
      │ HTTP / JSON + session cookie
      ▼
┌─────────────────────────────┐
│       FastAPI / main.py     │
└──────────────┬──────────────┘
               │
       ┌───────┼────────┐
       ▼       ▼        ▼
     auth/   core/    spotify/
       │       │        │
       │       │        ├── Spotify Web API
       │       │        └── BPM provider
       │       │
       │       └── Workout, cadence & matching logic
       │
       └── OAuth, sessions & token storage
```

The main idea is to keep `main.py` thin and separate the application's core logic, Spotify integration, and authentication.

## Repository

```text
running-playlist-generator/
├── backend/
│   ├── main.py
│   ├── core/
│   │   ├── models.py
│   │   ├── cadence.py
│   │   ├── matcher.py
│   │   └── fake_data.py
│   ├── spotify/
│   │   ├── auth.py
│   │   ├── client.py
│   │   ├── discovery.py
│   │   └── bpm.py
│   └── auth/
│       ├── config.py
│       ├── routes.py
│       ├── dependencies.py
│       └── store.py
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

### Backend files

| File | Purpose |
|---|---|
| `main.py` | Creates the FastAPI app and connects the API routes to the backend services. |
| `core/models.py` | Defines workout, track and playlist data models. |
| `core/cadence.py` | Converts pace and step length into target cadence and workout segments. |
| `core/matcher.py` | Ranks tracks by how closely their BPM matches the target cadence. |
| `core/fake_data.py` | Provides synthetic tracks for testing without Spotify. |
| `spotify/auth.py` | Handles Spotify OAuth and access-token refresh. |
| `spotify/client.py` | Wraps the Spotify Web API calls used by the application. |
| `spotify/discovery.py` | Searches Spotify and builds a BPM-enriched candidate track pool. |
| `spotify/bpm.py` | Defines the BPM provider interface and the GetSongBPM implementation. |
| `auth/config.py` | Loads authentication and application settings from environment variables. |
| `auth/routes.py` | Provides the Spotify login, callback, session and logout endpoints. |
| `auth/dependencies.py` | Validates sessions and creates an authenticated Spotify client for protected routes. |
| `auth/store.py` | Persists OAuth state and encrypted Spotify session credentials in SQLite. |

## Core logic

A workout can be either a steady run or a set of custom/interval segments.

For each segment:

```text
pace + step length
        ↓
target cadence (SPM)
        ↓
acceptable cadence range
        ↓
candidate Spotify tracks
        ↓
BPM matching
        ↓
ranked playlist
```

The cadence calculation uses:

```text
steps/km = 1000 / step_length_m

SPM = steps/km ÷ (pace_seconds_per_km / 60)
```

The matcher considers a track's BPM directly, at half-time, and at double-time. BPM fit is the main ranking factor, with smaller penalties for artist repetition and unsuitable track duration.

## Spotify integration

Spotify is used for authentication, track discovery and playlist creation. BPM is supplied separately through the `BpmProvider` interface.

```text
Spotify search
      ↓
track metadata
      ↓
BPM provider
      ↓
Track + BPM
      ↓
core matcher
      ↓
private Spotify playlist
```

This separation means the matching logic does not depend directly on Spotify's API.

## Authentication

The backend uses Spotify Authorization Code OAuth with a server-side application session.

```text
Browser
   │
   │ Spotify login
   ▼
FastAPI → Spotify OAuth
   │
   │ encrypted tokens
   ▼
SQLite session store
   │
   │ opaque session ID
   ▼
HttpOnly browser cookie
```

The React frontend never receives or stores Spotify access/refresh tokens. Authenticated endpoints use `get_authenticated_spotify()` to validate the application session, refresh Spotify tokens when required, and provide an authenticated Spotify client.

### Auth endpoints

| Endpoint | Purpose |
|---|---|
| `GET /auth/spotify` | Starts Spotify OAuth. |
| `GET /auth/spotify/callback` | Completes OAuth and creates the application session. |
| `GET /auth/me` | Returns safe information about the current session. |
| `POST /auth/logout` | Deletes the application session. |

## API

| Endpoint | Purpose |
|---|---|
| `GET /health` | Basic health check. |
| `POST /api/workouts/preview` | Tests the workout/cadence/matching pipeline using fake tracks. |
| `POST /api/spotify/generate-playlist` | Generates a private Spotify playlist for an authenticated user. |

The real playlist endpoint takes a `WorkoutRequest`, discovers Spotify tracks, enriches them with BPM, matches them to the workout, and creates the playlist.

## Local development

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create `.env` from `.env.example`, then provide the required Spotify, BPM-provider and session-encryption settings.

Generate the session encryption key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Run the backend:

```bash
uvicorn backend.main:app --reload
```

API documentation is available at `http://127.0.0.1:8000/docs`.

## Environment variables

| Variable | Purpose |
|---|---|
| `SPOTIFY_CLIENT_ID` | Spotify application client ID. |
| `SPOTIFY_CLIENT_SECRET` | Spotify application client secret. |
| `SPOTIFY_REDIRECT_URI` | Spotify OAuth callback URL. |
| `FRONTEND_URL` | React frontend origin. |
| `GETSONGBPM_API_KEY` | BPM provider API key. |
| `SESSION_ENCRYPTION_KEY` | Fernet key used to encrypt stored Spotify tokens. |
| `AUTH_DATABASE_PATH` | SQLite session database path. |
| `COOKIE_SECURE` | Enables secure cookies for HTTPS deployments. |

Never commit `.env` or the session database to source control.

## Testing

The project uses `pytest`.

```bash
pytest
```

The current tests cover the main cadence calculations, track matching behaviour, and authentication/session storage.

## Current limitations

- Music discovery is currently genre-based rather than personalised to the user's Spotify library.
- BPM depends on an external provider and may occasionally produce metadata mismatches.
- Playlist timing uses whole tracks, so segment boundaries are not guaranteed to be exact.
- The matching algorithm is intentionally simple and mainly prioritises BPM fit.
- SQLite is intended for local development rather than a scaled deployment.
- Production deployment still needs stronger security, rate limiting, retry handling and monitoring.

## Next step

The immediate goal is a minimal React client that proves the complete backend flow:

```text
React
  → FastAPI
  → authentication
  → Spotify + BPM
  → matcher
  → Spotify playlist
  → React
```

The frontend should initially focus on Spotify login, authentication status, a simple workout form, workout preview, and playlist generation.
