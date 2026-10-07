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
from .discovery import build_spotify_song_pool

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
