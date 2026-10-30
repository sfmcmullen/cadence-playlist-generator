"""
main.py

FastAPI entry point for the running playlist generator.
"""

# ==================================================
# Imports and Configuration
# ==================================================

from __future__ import annotations

import os
import json
from collections.abc import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .auth.config import get_frontend_url
from .auth.dependencies import AuthenticatedSpotify, get_authenticated_spotify
from .auth.routes import router as auth_router
from .core.cadence import build_workout_plan
from .core.fake_data import build_fake_song_pool
from .core.matcher import match_playlist_for_workout
from .core.models import WorkoutMatch, WorkoutRequest
from .spotify.bpm import (
    FallbackBpmProvider,
    GetSongBpmProvider,
    ReccoBeatsProvider,
)
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
# Helper Functions
# ==================================================


def build_plan_for_request(workout: WorkoutRequest):
    """Build a plan for either a steady run or multiple intervals."""

    if workout.workout_type != "interval":
        return build_workout_plan(workout)

    if not workout.intervals:
        raise ValueError("An interval workout requires at least one interval.")

    combined_plan = []

    for interval in workout.intervals:
        # Convert this interval into the existing steady-run format.
        interval_request = WorkoutRequest(
            workout_type="steady",
            distance_km=interval.distance_km,
            pace=interval.pace,
            step_length_m=interval.step_length_m,
        )

        # Reuse the existing cadence calculations.
        interval_plan = build_workout_plan(interval_request)

        # Preserve the order of the user's intervals.
        combined_plan.extend(interval_plan)

    return combined_plan


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

    segments = build_plan_for_request(workout)
    fake_pool = build_fake_song_pool()
    return match_playlist_for_workout(segments, fake_pool)


@app.post("/api/spotify/generate-playlist")
async def generate_spotify_playlist(
    workout: WorkoutRequest,
    auth: AuthenticatedSpotify = Depends(get_authenticated_spotify),
    playlist_name: str = "Running Playlist",
    genres: list[str] | None = Query(default=None),
    artists: list[str] | None = Query(default=None),
    search_queries: list[str] | None = Query(default=None),
    include_user_top_tracks: bool = True,
    top_tracks_time_range: str = "medium_term",
    expected_usable_rate: float = 0.40,
    max_candidates: int = 100,
):
    """Generate a Spotify playlist and stream progress updates."""

    async def event_generator() -> AsyncGenerator[str, None]:

        def progress(percent: int, message: str):
            return (
                json.dumps(
                    {
                        "type": "progress",
                        "percent": percent,
                        "message": message,
                    }
                )
                + "\n"
            )

        try:
            yield progress(5, "Preparing your workout...")

            api_key = os.getenv("GETSONGBPM_API_KEY")

            providers = []

            if api_key:
                providers.append(GetSongBpmProvider(api_key))

            providers.append(ReccoBeatsProvider())
            bpm_provider = FallbackBpmProvider(providers)

            segments = build_plan_for_request(workout)
            total_duration_seconds = sum(
                segment.duration_seconds for segment in segments
            )

            spotify = auth.client

            yield progress(15, "Finding songs for your workout...")

            song_pool = await build_spotify_song_pool(
                spotify,
                bpm_provider,
                workout_duration_seconds=total_duration_seconds,
                genres=genres,
                artists=artists,
                search_queries=search_queries,
                include_user_top_tracks=include_user_top_tracks,
                top_tracks_time_range=top_tracks_time_range,
                expected_usable_rate=expected_usable_rate,
                max_candidates=max_candidates,
                market=os.getenv("SPOTIFY_MARKET", "GB"),
            )

            if not song_pool:
                raise RuntimeError(
                    "No usable BPM data could be retrieved from "
                    "GetSongBPM or ReccoBeats."
                )

            yield progress(75, "Matching songs to your running cadence...")

            result = match_playlist_for_workout(segments, song_pool)

            yield progress(90, "Creating your Spotify playlist...")

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
                result.feedback.append(f"Spotify playlist created: {playlist_url}")
            else:
                result.feedback.append(f"Spotify playlist created: {playlist['id']}")

            yield progress(100, "Your playlist is ready!")

            yield json.dumps(
                {
                    "type": "result",
                    "data": result.model_dump(),
                }
            ) + "\n"

        except SpotifyAPIError as exc:
            yield json.dumps(
                {
                    "type": "error",
                    "message": str(exc),
                }
            ) + "\n"

        except RuntimeError as exc:
            yield json.dumps(
                {
                    "type": "error",
                    "message": str(exc),
                }
            ) + "\n"

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
    )
