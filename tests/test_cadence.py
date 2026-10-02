from backend.core.cadence import (
    build_workout_plan,
    calculate_duration_for_distance,
    pace_to_spm,
)
from backend.core.models import PaceInput, WorkoutRequest


def test_pace_to_spm():
    assert pace_to_spm(5, 0, 1.2) == 167
    assert pace_to_spm(6, 0, 1.2) == 139
    assert pace_to_spm(4, 30, 1.2) == 185


def test_steady_run_duration():
    pace = PaceInput(minutes=5, seconds=0)
    assert calculate_duration_for_distance(10, pace) == 3000


def test_steady_run_builds_one_segment():
    workout = WorkoutRequest(
        distance_km=10,
        pace=PaceInput(minutes=5, seconds=0),
        step_length_m=1.2,
    )

    segments = build_workout_plan(workout)

    assert len(segments) == 1
    assert segments[0].duration_seconds == 3000
    assert segments[0].target_spm == 167
    assert segments[0].min_spm == 164
    assert segments[0].max_spm == 170
