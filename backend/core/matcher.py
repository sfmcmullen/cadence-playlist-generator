"""
matcher.py

Rank and select tracks from a song pool for running-workout segments.
"""

# ==================================================
# Imports and Configuration
# ==================================================

from __future__ import annotations

from dataclasses import dataclass

from .models import MatchedSegment, Track, WorkoutMatch, WorkoutSegment

# ==================================================
# Data Classes
# ==================================================


@dataclass(frozen=True)
class BPMMatch:
    """Best tempo interpretation for a track."""

    # The absolute difference between the effective BPM and the target SPM.
    distance: float
    # The BPM of the track after applying the multiplier (direct, half-time, or double-time).
    effective_bpm: float
    # The multiplier applied to the original BPM (1.0 for direct, 0.5 for half-time, 2.0 for double-time).
    multiplier: float


# ==================================================
# Function Definitions
# ==================================================


def best_bpm_match(song_bpm: float, target_spm: float) -> BPMMatch:
    """Find the closest direct/half-time/double-time interpretation."""

    if song_bpm <= 0:
        raise ValueError("song_bpm must be greater than 0")
    if target_spm <= 0:
        raise ValueError("target_spm must be greater than 0")

    # Generate the three possible interpretations of the song's BPM (direct, half-time, double-time)
    options = (
        (song_bpm, 1.0),
        (song_bpm * 2, 2.0),
        (song_bpm / 2, 0.5),
    )

    # Select the interpretation that is closest to the target SPM
    effective_bpm, multiplier = min(
        options,
        key=lambda option: abs(option[0] - target_spm),
    )

    return BPMMatch(
        distance=abs(effective_bpm - target_spm),
        effective_bpm=effective_bpm,
        multiplier=multiplier,
    )


def is_bpm_match(song_bpm: float, min_spm: int, max_spm: int) -> bool:
    """Return whether a track can match a cadence window."""

    if min_spm > max_spm:
        raise ValueError("min_spm cannot be greater than max_spm")

    match = best_bpm_match(song_bpm, (min_spm + max_spm) / 2)
    return min_spm <= match.effective_bpm <= max_spm


def bpm_distance(song_bpm: float, target_spm: float) -> float:
    """Return the smallest tempo difference across direct/half/double-time."""

    return best_bpm_match(song_bpm, target_spm).distance


def track_score(
    track: Track,
    segment: WorkoutSegment,
    used_artists: set[str] | None = None,
) -> float:
    """
    Lower scores are better.
    BPM fit is the primary factor, with artist repetition and duration difference as secondary factors,
    to make the selection more diverse and better suited to the segment's duration.
    """

    if track.bpm is None:
        return float("inf")

    bpm_fit = bpm_distance(track.bpm, segment.target_spm)

    # Soft penalty for repeating artists -> Encourage diversity
    artist_penalty = (
        2.0 if used_artists and track.artist.lower() in used_artists else 0.0
    )

    # Soft penalty for duration difference -> Encourage better fit to segment duration
    duration_penalty = max(0, track.duration_seconds - segment.duration_seconds) / 120

    return (bpm_fit * 10) + artist_penalty + duration_penalty


def filter_candidate_songs(
    song_pool: list[Track],
    segment: WorkoutSegment,
    used_song_ids: set[str],
    max_bpm_distance: float = 6.0,
) -> list[Track]:
    """Filter out used tracks, missing BPM data and poor cadence matches."""

    candidates: list[Track] = []

    for track in song_pool:
        if track.spotify_id in used_song_ids or track.bpm is None:
            continue

        if bpm_distance(track.bpm, segment.target_spm) <= max_bpm_distance:
            candidates.append(track)

    return candidates


def select_tracks_for_segment(
    segment: WorkoutSegment,
    candidate_songs: list[Track],
    used_song_ids: set[str],
) -> list[Track]:
    """Select tracks from a pool of candidates, using a greedy selection algorithm.

    As tracks are selected, the pool is re-ranked to account for artist repetition and duration fit.
    """

    def get_track_priority(track):
        """Helper function to determine the priority of a track based on score and duration fit."""
        # Primary sorting criteria: track score
        score = track_score(track, segment, used_artists)

        # Secondary tie-breaker: time remaining after adding this track
        remaining_time = segment.duration_seconds - total_duration
        time_difference = abs(remaining_time - track.duration_seconds)

        return (score, time_difference)

    selected: list[Track] = []
    total_duration = 0
    used_artists: set[str] = set()

    # Filter out tracks that have already been used or don't fit the cadence requirements
    remaining = [
        track for track in candidate_songs if track.spotify_id not in used_song_ids
    ]

    # Greedily select tracks until the segment duration is met or exceeded
    while remaining and total_duration < segment.duration_seconds:
        # Sort the remaining tracks based on their priority
        remaining.sort(key=get_track_priority)

        # Select the best track (lowest score and best duration fit)
        track = remaining.pop(0)
        selected.append(track)
        used_song_ids.add(track.spotify_id)
        used_artists.add(track.artist.lower())
        total_duration += track.duration_seconds

    return selected


def match_playlist_for_workout(
    workout_segments: list[WorkoutSegment],
    song_pool: list[Track],
) -> WorkoutMatch:
    """Create a ranked track selection for every workout segment."""

    matched_segments: list[MatchedSegment] = []
    used_song_ids: set[str] = set()
    warnings: list[str] = []

    # Iterate through each workout segment and select tracks from the song pool
    for segment in workout_segments:
        # Filter candidate songs based on cadence and previously used tracks
        candidates = filter_candidate_songs(
            song_pool,
            segment,
            used_song_ids,
        )

        # Select tracks for the current segment from the filtered candidates
        selected_tracks = select_tracks_for_segment(
            segment,
            candidates,
            used_song_ids,
        )

        selected_duration = sum(track.duration_seconds for track in selected_tracks)
        duration_difference = selected_duration - segment.duration_seconds

        # Warn if the selected tracks do not fully cover the segment duration
        if selected_duration < segment.duration_seconds:
            warnings.append(
                f"{segment.name}: only {selected_duration}s of suitable music "
                f"found for a {segment.duration_seconds}s segment."
            )

        # Append the matched segment with its details to the list of matched segments
        matched_segments.append(
            MatchedSegment(
                name=segment.name,
                duration_seconds=segment.duration_seconds,
                target_spm=segment.target_spm,
                min_spm=segment.min_spm,
                max_spm=segment.max_spm,
                selected_tracks=selected_tracks,
                selected_duration_seconds=selected_duration,
                duration_difference_seconds=duration_difference,
                candidate_count=len(candidates),
            )
        )

    total_workout_seconds = sum(
        segment.duration_seconds for segment in workout_segments
    )
    total_music_seconds = sum(
        segment.selected_duration_seconds for segment in matched_segments
    )

    if not song_pool:
        warnings.append("The song pool is empty.")

    return WorkoutMatch(
        segments=matched_segments,
        total_workout_seconds=total_workout_seconds,
        total_music_seconds=total_music_seconds,
        warnings=warnings,
    )
