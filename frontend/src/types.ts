export type Pace = {
    minutes: number;
    seconds: number;
}

type WorkoutSegmentRequest = {
    distance_km: number;
    pace: Pace;
    step_length_m: number;
};

export type WorkoutRequest =
    | ({
          workout_type: "steady";
      } & WorkoutSegmentRequest)
    | {
          workout_type: "interval";
          intervals: WorkoutSegmentRequest[];
      };

export type User = {
    spotify_account_id: string;
    spotify_display_name: string | null;
}


export type WorkoutTrack = {
    spotify_id: string;
    name: string;
    artist: string;
    duration_seconds: number;
    bpm: number | null;
    spotify_url?: string | null;
    spotify_uri?: string | null;
};

export type MatchedSegment = {
    name: string;
    duration_seconds: number;
    target_spm: number;
    min_spm: number;
    max_spm: number;
    selected_tracks: WorkoutTrack[];
    selected_duration_seconds: number;
    duration_difference_seconds: number;
    candidate_count: number;
};

export type WorkoutResult = {
    segments: MatchedSegment[];
    total_workout_seconds: number;
    total_music_seconds: number;
    warnings: string[];
};