"""Track catalogue for development and testing of the matching algorithm.

Allows for matching algorithm development without requiring external services.
"""

# ==================================================
# Imports and Configuration
# ==================================================

from __future__ import annotations

import random

from .models import Track

# ==================================================
# Function Definitions
# ==================================================


def build_fake_song_pool(count: int = 150, seed: int = 42) -> list[Track]:
    """Create a realistic synthetic track pool for local testing."""

    rng = random.Random(seed)
    artists = [
        "Demo Artist A",
        "Demo Artist B",
        "Demo Artist C",
        "Demo Artist D",
        "Demo Artist E",
        "Demo Artist F",
        "Demo Artist G",
        "Demo Artist H",
    ]

    tracks: list[Track] = []

    for index in range(1, count + 1):
        bpm = rng.randint(70, 200)
        duration = rng.randint(170, 310)
        artist = rng.choice(artists)

        tracks.append(
            Track(
                spotify_id=f"demo-{index:04d}",
                name=f"Demo Track {index:03d}",
                artist=artist,
                duration_seconds=duration,
                bpm=bpm,
                explicit=False,
            )
        )

    return tracks


if __name__ == "__main__":
    for track in build_fake_song_pool(20):
        print(track.model_dump())
