from backend.core.matcher import best_bpm_match, match_playlist_for_workout
from backend.core.models import Track, WorkoutSegment


def make_track(
    track_id: str, bpm: float, duration: int = 210, artist: str = "Artist"
) -> Track:
    return Track(
        spotify_id=track_id,
        name=f"Track {track_id}",
        artist=artist,
        duration_seconds=duration,
        bpm=bpm,
    )


def make_segment(duration: int = 300, target_spm: int = 180) -> WorkoutSegment:
    return WorkoutSegment(
        name="Main Run",
        duration_seconds=duration,
        pace_seconds_per_km=300,
        target_spm=target_spm,
        min_spm=target_spm - 3,
        max_spm=target_spm + 3,
    )


def test_direct_bpm_match_wins():
    match = best_bpm_match(182, 180)
    assert match.distance == 2
    assert match.effective_bpm == 182
    assert match.multiplier == 1


def test_half_and_double_time_are_considered():
    assert best_bpm_match(90, 180).distance == 0
    assert best_bpm_match(360, 180).distance == 0


def test_matcher_uses_best_candidates_not_pool_order():
    segment = make_segment()
    pool = [
        make_track("poor", 160),
        make_track("great", 180),
        make_track("also-good", 178, artist="Other Artist"),
        make_track("great-too", 181, artist="Third Artist"),
    ]

    result = match_playlist_for_workout([segment], pool)
    selected = result.segments[0].selected_tracks

    assert selected
    assert selected[0].spotify_id in {"great", "also-good", "great-too"}
    assert "poor" not in {track.spotify_id for track in selected}
