"""
cadence.py

This module contains functions to calculate cadence (steps per minute) based on pace and stride length.
"""

# ==================================================
# Imports and Configuration
# ==================================================

from __future__ import annotations

from .models import PaceInput, WorkoutRequest, WorkoutSegment

DEFAULT_CADENCE_TOLERANCE = 3

# ==================================================
# Helper functions for cadence & bpm calculations
# ==================================================


def pace_to_spm(
    pace_minutes: int | float, pace_seconds: int | float, step_length_m: float
) -> int:
    """Convert pace and step length to estimated steps per minute (SPM).

    Args:
        pace_minutes (int | float): The pace in minutes per kilometer.
        pace_seconds (int | float): The pace in seconds per kilometer.
        step_length_m (float): The step length in meters. Deliberately not using stride length to avoid confusion with two-step cycles.

    Returns:
        int: The estimated steps per minute (SPM), rounded to the nearest integer.
    """

    if step_length_m <= 0:
        raise ValueError("step_length_m must be greater than 0")
    if pace_minutes < 0:
        raise ValueError("pace_minutes cannot be negative")
    if not 0 <= pace_seconds < 60:
        raise ValueError("pace_seconds must be between 0 and 59")

    total_seconds_per_km = pace_minutes * 60 + pace_seconds
    if total_seconds_per_km <= 0:
        raise ValueError("pace must be greater than 0")

    steps_per_km = 1000 / step_length_m
    spm = steps_per_km / (total_seconds_per_km / 60)

    return round(spm)


def pace_to_spm_from_model(pace: PaceInput, step_length_m: float) -> int:
    """Wrapper function to convert PaceInput model to steps per minute (SPM)."""
    return pace_to_spm(pace.minutes, pace.seconds, step_length_m)


def calculate_spm_range(
    target_spm: int, tolerance: int = DEFAULT_CADENCE_TOLERANCE
) -> tuple[int, int]:
    """Calculate the acceptable cadence range given a target SPM and a tolerance."""

    if target_spm <= 0:
        raise ValueError("target_spm must be greater than 0")
    if tolerance < 0:
        raise ValueError("tolerance cannot be negative")
    if target_spm - tolerance <= 0:
        raise ValueError("target_spm - tolerance must be greater than 0")

    return target_spm - tolerance, target_spm + tolerance


def calculate_duration_for_distance(
    distance_km: float,
    pace: PaceInput,
) -> int:
    """Calculate a steady-run duration from distance and pace."""

    if distance_km <= 0:
        raise ValueError("distance_km must be greater than 0")

    seconds = distance_km * pace.seconds_per_km
    return round(seconds)


def build_workout_plan(
    workout: WorkoutRequest,
    tolerance: int = DEFAULT_CADENCE_TOLERANCE,
) -> list[WorkoutSegment]:
    """Convert frontend input into the normalised representation used by matching."""

    result: list[WorkoutSegment] = []

    # For custom workouts, calculate cadence with ranges for each segment
    if workout.segments is not None:
        for segment in workout.segments:
            target_spm = pace_to_spm_from_model(segment.pace, workout.step_length_m)
            min_spm, max_spm = calculate_spm_range(target_spm, tolerance)

            result.append(
                WorkoutSegment(
                    name=segment.name,
                    duration_seconds=segment.duration_seconds,
                    pace_seconds_per_km=segment.pace.seconds_per_km,
                    target_spm=target_spm,
                    min_spm=min_spm,
                    max_spm=max_spm,
                )
            )

        return result

    # For steady runs, assert that distance and pace are provided, then calculate duration and cadence
    assert workout.distance_km is not None
    assert workout.pace is not None

    target_spm = pace_to_spm_from_model(workout.pace, workout.step_length_m)
    min_spm, max_spm = calculate_spm_range(target_spm, tolerance)

    result.append(
        WorkoutSegment(
            name="Main Run",
            duration_seconds=calculate_duration_for_distance(
                workout.distance_km,
                workout.pace,
            ),
            pace_seconds_per_km=workout.pace.seconds_per_km,
            target_spm=target_spm,
            min_spm=min_spm,
            max_spm=max_spm,
        )
    )

    return result
