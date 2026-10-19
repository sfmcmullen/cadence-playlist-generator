"""
routes.py

FastAPI routes for Spotify ...
This acts as the main entry point for the ...
"""

# ==================================================
# Imports and Configuration
# ==================================================

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from fastapi.responses import RedirectResponse

from .auth import SpotifyAuthorizationError, authorization_url, exchange_code
from .client import SpotifyAPIError, SpotifyClient
from ..auth.config import get_auth_settings
from ..auth.dependencies import (
    AuthenticatedSpotify,
    get_authenticated_spotify,
    get_store,
)

from .bpm import (
    FallbackBpmProvider,
    GetSongBpmProvider,
    ReccoBeatsProvider,
)
from ..core.models import Track
import os

router = APIRouter(prefix="/spotify", tags=["spotify"])

# ==================================================
# Routes
# ==================================================


@router.get("/search")
async def search_spotify_tracks(
    q: str = Query(..., description="Search query for tracks"),
    spotify: AuthenticatedSpotify = Depends(get_authenticated_spotify),
):
    """Search Spotify for tracks based on the provided query."""
    try:
        tracks = await spotify.client.search_tracks(
            query=q,
            market="GB",
            limit=10,
        )

        simplified_tracks = [
            {
                "spotify_id": track.spotify_id,
                "name": track.name,
                "artist": track.artist,
                "duration_seconds": track.duration_seconds,
                "bpm": track.bpm,
                "isrc": track.isrc,
                "explicit": track.explicit,
                "popularity": track.popularity,
                "spotify_uri": track.spotify_uri,
                "spotify_url": track.spotify_url,
            }
            for track in tracks
        ]

        return {"tracks": simplified_tracks}

    except SpotifyAPIError as e:
        raise HTTPException(status_code=500, detail=str(e))


# use the search_spotify_tracks function to get a list of tracks and then return the bpm of those tracks
@router.get("/bpm")
@router.get("/bpm")
async def get_bpm_for_tracks(
    q: str = Query(..., description="Search query for tracks"),
    spotify: AuthenticatedSpotify = Depends(get_authenticated_spotify),
):
    """Search Spotify and enrich tracks with BPM data."""
    try:
        # 1. Search Spotify for candidate tracks.
        tracks = await spotify.client.search_tracks(
            query=q,
            market="GB",
            limit=10,
        )

        # 2. Build the provider chain once per request.
        api_key = os.getenv("GETSONGBPM_API_KEY")
        providers = []

        if api_key:
            providers.append(GetSongBpmProvider(api_key))

        # Always provide a fallback that does not require this API key.
        providers.append(ReccoBeatsProvider())

        bpm_provider = FallbackBpmProvider(providers)

        # 3. Enrich the original Track objects.
        enriched_tracks = []

        for track in tracks:
            enriched = await bpm_provider.enrich(track)

            enriched_tracks.append(
                {
                    "spotify_id": enriched.spotify_id,
                    "name": enriched.name,
                    "artist": enriched.artist,
                    "duration_seconds": enriched.duration_seconds,
                    "bpm": enriched.bpm,
                    "isrc": enriched.isrc,
                    "explicit": enriched.explicit,
                    "popularity": enriched.popularity,
                    "spotify_uri": enriched.spotify_uri,
                    "spotify_url": enriched.spotify_url,
                }
            )

        return {"tracks": enriched_tracks}

    except SpotifyAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc
