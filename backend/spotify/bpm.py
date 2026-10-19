"""
bpm.py

Spotify no longer provides BPM data in their API, so we use GetSongBPM to enrich tracks with BPM information.
 - GetSongBPM requires an API key and attribution/backlink
"""

# ==================================================
# Imports and Configuration
# ==================================================

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Protocol

import httpx

from ..core.models import Track

import logging

GETSONGBPM_BASE_URL = "https://api.getsong.co"
RECCOBEATS_BASE_URL = "https://api.reccobeats.com/v1"

logger = logging.getLogger(__name__)


# ==================================================
# Classes and Functions
# ==================================================


class BpmProvider(Protocol):

    async def enrich(self, track: Track) -> Track:
        """Return a copy of ``track`` with BPM populated where available."""


class GetSongBpmProvider:

    def __init__(self, api_key: str, timeout: float = 15.0) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self._cache: dict[str, float | None] = {}
        self._disabled = (
            False  # Flag to disable the provider if the API key is not working
        )

    async def enrich(self, track: Track) -> Track:
        """Return a copy of ``track`` with BPM populated where available."""
        if track.bpm is not None:
            return track

        if track.spotify_id in self._cache:
            bpm = self._cache[track.spotify_id]
            return track.model_copy(update={"bpm": bpm})

        bpm = await self._lookup_bpm(track)
        self._cache[track.spotify_id] = bpm
        return track.model_copy(update={"bpm": bpm})

    async def _lookup_bpm(self, track: Track) -> float | None:
        """Lookup the BPM for a track using the GetSongBPM API."""
        # If the API has already rejected our credentials,
        # don't keep sending requests with the same invalid key.
        if self._disabled:
            return None

        # Construct a lookup string that includes the track name and the first artist
        lookup = f"song:{track.name} artist:{track.artist.split(',')[0]}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{GETSONGBPM_BASE_URL}/search/",
                params={
                    "api_key": self.api_key,
                    "type": "both",
                    "lookup": lookup,
                    "limit": 10,
                },
            )

        if response.status_code in (401, 403):
            # Stop repeatedly trying a key that has been rejected.
            self._disabled = True

            raise RuntimeError(
                f"GetSongBPM authentication failed: " f"HTTP {response.status_code}"
            )

        if response.status_code >= 400:
            raise RuntimeError(
                f"GetSongBPM lookup failed: " f"{response.status_code} {response.text}"
            )

        data = response.json()
        results = data.get("search", [])

        if not results:
            return None

        best_result: dict | None = None
        best_score = 0.0

        # Score each result based on title and artist similarity to the track
        for result in results:
            title_score = SequenceMatcher(
                None,
                _normalise(track.name),
                _normalise(str(result.get("title", ""))),
            ).ratio()

            artist_values = result.get("artist") or []
            if isinstance(artist_values, dict):
                artist_values = [artist_values]

            artist_score = max(
                (
                    SequenceMatcher(
                        None,
                        _normalise(track.artist),
                        _normalise(str(artist.get("name", ""))),
                    ).ratio()
                    for artist in artist_values
                    if isinstance(artist, dict)
                ),
                default=0.0,
            )

            score = (title_score * 0.65) + (artist_score * 0.35)
            if score > best_score:
                best_score = score
                best_result = result

        # If the best match is below a certain threshold, we consider it unreliable and return None
        if best_result is None or best_score < 0.78:
            return None

        # Return the BPM from the best result, if available
        try:
            return float(best_result["tempo"])
        except (KeyError, TypeError, ValueError):
            return None


class ReccoBeatsProvider:
    """Look up track tempo using the ReccoBeats API."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self._cache: dict[str, float | None] = {}

    async def enrich(self, track: Track) -> Track:
        """Return a track enriched with BPM where available."""

        if track.bpm is not None:
            return track

        if track.spotify_id in self._cache:
            return track.model_copy(update={"bpm": self._cache[track.spotify_id]})

        bpm = await self._lookup_bpm(track)

        self._cache[track.spotify_id] = bpm

        return track.model_copy(update={"bpm": bpm})

    async def _lookup_bpm(self, track: Track) -> float | None:
        """Request audio features for a Spotify track ID."""

        url = f"{RECCOBEATS_BASE_URL}/audio-features"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                url,
                params={"ids": track.spotify_id},
            )

        # A missing track is not necessarily an API failure.
        # It may simply not exist in this provider's database.
        if response.status_code == 404:
            return None

        if response.status_code >= 400:
            raise RuntimeError(
                f"ReccoBeats lookup failed: " f"{response.status_code} {response.text}"
            )

        data = response.json()

        # Usually the endpoint returns one feature object.
        # Handle a content-list response as well.
        if isinstance(data, dict) and isinstance(data.get("content"), list):
            data = next(
                (
                    item
                    for item in data["content"]
                    if isinstance(item, dict) and item.get("tempo") is not None
                ),
                {},
            )

        try:
            bpm = float(data["tempo"])
        except (KeyError, TypeError, ValueError):
            return None

        # Reject invalid tempo values.
        if bpm <= 0:
            return None

        return bpm


class FallbackBpmProvider:
    """Try multiple BPM providers in priority order."""

    def __init__(self, providers: list[BpmProvider]) -> None:
        if not providers:
            raise ValueError("At least one BPM provider is required.")

        self.providers = providers

    async def enrich(self, track: Track) -> Track:
        """Use the first provider that returns a valid BPM."""

        if track.bpm is not None:
            return track

        for provider in self.providers:
            try:
                enriched_track = await provider.enrich(track)

            except (RuntimeError, httpx.HTTPError, ValueError) as exc:
                # This provider failed, so try the next one.
                logger.warning(
                    "%s failed for track %r: %s",
                    type(provider).__name__,
                    track.name,
                    exc,
                )
                continue

            if enriched_track.bpm is not None and enriched_track.bpm > 0:
                return enriched_track

            # No BPM was found; try the next provider.

        # Every provider failed or had no BPM for this song.
        return track.model_copy(update={"bpm": None})


def _normalise(value: str) -> str:
    return " ".join(value.lower().replace("'", "").split())
