"""
main.py

FastAPI entry point for the running playlist generator.
"""

# ==================================================
# Imports and Configuration
# ==================================================

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .auth.config import get_frontend_url
from .auth.dependencies import AuthenticatedSpotify, get_authenticated_spotify
from .auth.routes import router as auth_router
from .core.cadence import build_workout_plan
from .core.fake_data import build_fake_song_pool
from .core.matcher import match_playlist_for_workout
from .core.models import WorkoutMatch, WorkoutRequest
from .spotify.bpm import GetSongBpmProvider
from .spotify.client import SpotifyAPIError
from .spotify.discovery import build_spotify_song_pool
from .spotify.routes import router as spotify_router

# ==================================================
# FastAPI Application Setup
# ==================================================

frontend_url = get_frontend_url()

app = FastAPI(title="Running Playlist Generator", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(spotify_router)

# ==================================================
# API Endpoints
# ==================================================


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/workouts/preview", response_model=WorkoutMatch)
async def preview_workout(workout: WorkoutRequest) -> WorkoutMatch:
    """Run the complete matching algorithm without Spotify."""
    # Note: FastAPI and Pydantic will automatically:
    # - Read the JSON body
    # - Convert it to a WorkoutRequest object
    # - Validate the fields and types
    # - Return the resulting Python object

    segments = build_workout_plan(workout)
    fake_pool = build_fake_song_pool()
    return match_playlist_for_workout(segments, fake_pool)


@app.post("/api/spotify/generate-playlist", response_model=WorkoutMatch)
async def generate_spotify_playlist(
    workout: WorkoutRequest,
    auth: AuthenticatedSpotify = Depends(get_authenticated_spotify),
    playlist_name: str = "Running Playlist",
    genres: list[str] | None = None,
) -> WorkoutMatch:
    """Generate and create a Spotify playlist for the supplied workout."""

    # Note: Using ``Depends(get_authenticated_spotify)`` ensures that
    # the user is authenticated with Spotify.

    api_key = os.getenv("GETSONGBPM_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="GETSONGBPM_API_KEY is not configured",
        )

    spotify = auth.client
    bpm_provider = GetSongBpmProvider(api_key)

    try:
        song_pool = await build_spotify_song_pool(
            spotify,
            bpm_provider,
            genres=genres,
            market=os.getenv("SPOTIFY_MARKET", "GB"),
        )

        segments = build_workout_plan(workout)
        result = match_playlist_for_workout(segments, song_pool)

        playlist = await spotify.create_playlist(
            playlist_name,
            public=False,
            description="Running playlist generated from workout cadence.",
        )

        track_ids = [
            track.spotify_id
            for segment in result.segments
            for track in segment.selected_tracks
        ]
        await spotify.add_items_to_playlist(playlist["id"], track_ids)

        playlist_url = playlist.get("external_urls", {}).get("spotify")
        if playlist_url:
            result.warnings.append(f"Spotify playlist created: {playlist_url}")
        else:
            result.warnings.append(f"Spotify playlist created: {playlist['id']}")

        return result

    except SpotifyAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
