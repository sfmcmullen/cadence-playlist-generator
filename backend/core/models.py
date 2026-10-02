"""
models.py

Shared domain and API models for the running playlist generator.
"""

# ==================================================
# Imports and Configuration
# ==================================================

from __future__ import annotations

# Pydantic is used here for defining the models with strong typing and automatic validation.
# Pydantic automatically validates input types, enforces values constraints,
# executes cross-field logic, and serialises data into standard python objects or JSON response payloads.
# ge = greater than or equal to, le = less than or equal to, lt = less than, gt = greater than
from pydantic import BaseModel, Field, model_validator


class PaceInput(BaseModel):
    """Pace expressed as minutes and seconds per kilometer."""

    minutes: int = Field(
        ge=0, le=60
    )  # Minutes per kilometer, must be between 0 and 60.
    seconds: int = Field(
        ge=0, lt=60
    )  # Seconds per kilometer, must be between 0 and 59.

    @property
    def seconds_per_km(self) -> float:
        """Return the total pace in seconds per kilometer."""
        return self.minutes * 60 + self.seconds


class WorkoutSegmentInput(BaseModel):
    """A single workout phase, such as warmup, interval, or cooldown."""

    name: str = Field(min_length=1, max_length=100)
    duration_seconds: int = Field(gt=0)
    pace: PaceInput


class WorkoutRequest(BaseModel):
    """Frontend request for either steady run or interval workout."""

    # Steady run inputs
    distance_km: float | None = Field(default=None, gt=0)
    pace: PaceInput | None = None

    # Interval workout inputs
    segments: list[WorkoutSegmentInput] | None = None

    # Metres travelled per step, rather than using stride which is two-steps cycle.
    step_length_m: float = Field(gt=0.25, lt=3.0)

    @model_validator(mode="after")
    def validate_workout(self) -> "WorkoutRequest":
        steady_run = self.distance_km is not None and self.pace is not None
        custom_workout = self.segments is not None

        if steady_run and custom_workout:
            raise ValueError(
                "Please provide either a steady run (distance and pace) or a custom workout (segments), not both."
            )

        if not steady_run and not custom_workout:
            raise ValueError(
                "Please provide either a steady run (distance and pace) or a custom workout (segments)."
            )

        if self.distance_km is not None and self.pace is None:
            raise ValueError("A steady run requires both distance_km and pace")

        if self.pace is not None and self.distance_km is None and self.segments is None:
            raise ValueError("A steady run requires both distance_km and pace")

        if self.segments is not None and len(self.segments) == 0:
            raise ValueError("A custom workout requires at least one segment")

        return self


class WorkoutSegment(BaseModel):
    """Normalised segment representation used by matching algorithm."""

    name: str
    duration_seconds: int = Field(gt=0)
    pace_seconds_per_km: float = Field(gt=0)
    target_spm: int = Field(gt=0)
    min_spm: int = Field(gt=0)
    max_spm: int = Field(gt=0)


class Track(BaseModel):
    """Track metadata required by the playlist matching algorithm."""

    spotify_id: str
    name: str
    artist: str
    duration_seconds: int = Field(gt=0)
    bpm: float | None = Field(default=None, gt=0)
    isrc: str | None = None
    explicit: bool | None = None
    popularity: int | None = Field(default=None, ge=0, le=100)
    spotify_uri: str | None = None
    spotify_url: str | None = None


class MatchedSegment(BaseModel):
    """A workout segment and the tracks selected for it."""

    name: str
    duration_seconds: int
    target_spm: int
    min_spm: int
    max_spm: int
    selected_tracks: list[Track]
    selected_duration_seconds: int
    duration_difference_seconds: int
    candidate_count: int


class WorkoutMatch(BaseModel):
    """Full result from the playlist matcher."""

    segments: list[MatchedSegment]
    total_workout_seconds: int
    total_music_seconds: int
    warnings: list[str] = Field(default_factory=list)
