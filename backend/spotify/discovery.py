"""
discovery.py

Discovery module for Spotify tracks.
Provides functionality to build a candidate pool of tracks based on genres and enrich them with BPM information.
"""

# ==================================================
# Imports and Configuration
# ==================================================

from __future__ import annotations

from .bpm import BpmProvider
from .client import SpotifyClient
from ..core.models import Track

# ==================================================
# Functions
# ==================================================


async def build_spotify_song_pool(
    spotify: SpotifyClient,
    bpm_provider: BpmProvider,
    *,
    genres: list[str] | None = None,
    market: str = "GB",
    pages_per_genre: int = 2,
) -> list[Track]:
    """
    Build a candidate pool using Spotify search, then enrich with BPM.

    Spotify search limits results to 10 tracks per page, so paginate.
    """

    genres = genres or ["pop", "rock", "hip-hop"]

    discovered: dict[str, Track] = {}

    for genre in genres:
        for page in range(max(1, pages_per_genre)):
            tracks = await spotify.search_tracks(
                f"genre:{genre}",
                market=market,
                limit=10,
                offset=page * 10,
            )

            for track in tracks:
                discovered.setdefault(track.spotify_id, track)

    enriched: list[Track] = []
    for track in discovered.values():
        enriched.append(await bpm_provider.enrich(track))

    return [track for track in enriched if track.bpm is not None]
