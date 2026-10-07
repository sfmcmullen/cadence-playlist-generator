export type Pace = {
    minutes: number;
    seconds: number;
}

export type WorkoutRequest = {
    distance_km?: number;
    pace?: Pace;
    step_length_m: number;
}

export type User = {
    spotify_account_id: string;
    spotify_display_name: string | null;
}


export type WorkoutResult = {
    duration_seconds: number;
    segments: unknown[];
    warnings: string[];
};