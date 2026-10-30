import { useEffect, useState } from "react";
import type { WorkoutRequest, User, WorkoutResult } from "./types";
import "./App.css";
import heroImage from "./assets/hero.jpg";

const API_URL = import.meta.env.VITE_API_URL;

type WorkoutType = "steady" | "interval";

type IntervalInput = {
    id: number;
    distance: number;
    paceMinutes: number;
    paceSeconds: number;
    stepLength: number;
};

// The form uses comma-separated values for genres and artists, and one
// Spotify search expression per line in the custom-query box.
function parseCommaSeparated(input: string): string[] {
    return input
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
}

function parseLines(input: string): string[] {
    return input
        .split(/\r?\n/)
        .map((value) => value.trim())
        .filter(Boolean);
}

function App() {
    const [user, setUser] = useState<User | null>(null);
    const [result, setResult] = useState<WorkoutResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [progressMessage, setProgressMessage] = useState("");
    const [error, setError] = useState<string | null>(null);

    type AppPage = "generator" | "how";
    const [activePage, setActivePage] = useState<AppPage>("generator");

    // Workout controls. Defaults are close to the supplied design mock-up.
    const [workoutType, setWorkoutType] = useState<WorkoutType>("steady");
    const [distance, setDistance] = useState<number>(5);
    const [paceMinutes, setPaceMinutes] = useState<number>(5);
    const [paceSeconds, setPaceSeconds] = useState<number>(30);
    const [stepLength, setStepLength] = useState<number>(0.8);
    const [nextIntervalId, setNextIntervalId] = useState(4);
    const [intervals, setIntervals] = useState<IntervalInput[]>([
        {
            id: 1,
            distance: 1,
            paceMinutes: 6,
            paceSeconds: 0,
            stepLength: 0.78,
        },
        { id: 2, distance: 2, paceMinutes: 5, paceSeconds: 0, stepLength: 0.9 },
        {
            id: 3,
            distance: 1,
            paceMinutes: 6,
            paceSeconds: 30,
            stepLength: 0.75,
        },
    ]);

    // Music discovery preferences.
    const [genresInput, setGenresInput] = useState("");
    const [artistsInput, setArtistsInput] = useState("");
    const [searchQueriesInput, setSearchQueriesInput] = useState("");
    const [includeUserTopTracks, setIncludeUserTopTracks] = useState(true);
    const [topTracksTimeRange, setTopTracksTimeRange] = useState("medium_term");

    // Candidate-pool sizing controls.
    const [expectedUsableRatePercent, setExpectedUsableRatePercent] =
        useState<number>(40);
    const [maxCandidates, setMaxCandidates] = useState<number>(150);

    useEffect(() => {
        if (API_URL) {
            void checkAuthentication();
        }
    }, []);

    async function checkAuthentication() {
        try {
            const response = await fetch(`${API_URL}/auth/me`, {
                credentials: "include",
            });

            if (!response.ok) {
                setUser(null);
                return;
            }

            const data: User = await response.json();
            setUser(data);
        } catch {
            setUser(null);
        }
    }

    function loginWithSpotify() {
        if (!API_URL) {
            setError(
                "Set VITE_API_URL to your backend URL before connecting Spotify."
            );
            return;
        }
        window.location.href = `${API_URL}/auth/spotify`;
    }

    function signOutOfSpotify() {
        if (!API_URL) return;

        fetch(`${API_URL}/auth/logout`, {
            method: "POST",
            credentials: "include",
        })
            .then((response) => {
                if (!response.ok) throw new Error("Logout failed");
                setUser(null);
                setResult(null);
            })
            .catch((logoutError) => {
                console.error("Logout error:", logoutError);
                setError("Could not log out of Spotify. Please try again.");
            });
    }

    // Temporary debugging tools are retained under the developer details panel.
    function searchSpotfy() {
        if (!API_URL) return;
        fetch(`${API_URL}/spotify/search?q=Milky Chance`, {
            method: "GET",
            credentials: "include",
        })
            .then(async (response) => {
                if (!response.ok)
                    throw new Error(`Search failed (${response.status})`);
                return response.json();
            })
            .then((data) => console.log("Search results:", data))
            .catch((searchError) =>
                console.error("Search error:", searchError)
            );
    }

    function getBpm() {
        if (!API_URL) return;
        fetch(`${API_URL}/spotify/bpm?q=The Weeknd`, {
            method: "GET",
            credentials: "include",
        })
            .then(async (response) => {
                if (!response.ok)
                    throw new Error(`BPM test failed (${response.status})`);
                return response.json();
            })
            .then((data) => console.log("BPM results:", data))
            .catch((bpmError) => console.error("BPM error:", bpmError));
    }

    function intervalFieldChange(
        id: number,
        field: keyof Omit<IntervalInput, "id">,
        value: number
    ) {
        setIntervals((current) =>
            current.map((interval) =>
                interval.id === id ? { ...interval, [field]: value } : interval
            )
        );
    }

    function addInterval() {
        setIntervals((current) => [
            ...current,
            {
                id: nextIntervalId,
                distance: 1,
                paceMinutes: 6,
                paceSeconds: 0,
                stepLength: 0.8,
            },
        ]);
        setNextIntervalId((current) => current + 1);
    }

    function removeInterval(id: number) {
        setIntervals((current) =>
            current.filter((interval) => interval.id !== id)
        );
    }

    function getWorkoutRequest(): WorkoutRequest {
        if (workoutType === "interval") {
            return {
                workout_type: "interval",
                intervals: intervals.map((interval) => ({
                    distance_km: interval.distance,
                    pace: {
                        minutes: interval.paceMinutes,
                        seconds: interval.paceSeconds,
                    },
                    step_length_m: interval.stepLength,
                })),
            };
        }

        return {
            workout_type: "steady",
            distance_km: distance,
            pace: {
                minutes: paceMinutes,
                seconds: paceSeconds,
            },
            step_length_m: stepLength,
        };
    }

    // Spotify-independent preview endpoint.
    async function generatePreviewWorkout() {
        setError(null);
        if (!API_URL) {
            setError(
                "Set VITE_API_URL to your backend URL before generating a workout."
            );
            return;
        }

        setLoading(true);
        setResult(null);
        try {
            const workout = getWorkoutRequest();
            const response = await fetch(`${API_URL}/api/workouts/preview`, {
                method: "POST",
                credentials: "include",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(workout),
            });

            if (!response.ok) {
                const errorData = await response.json();
                const detail = errorData.detail;
                throw new Error(
                    typeof detail === "string"
                        ? detail
                        : `Preview failed (${response.status})`
                );
            }

            const data: WorkoutResult = await response.json();
            setResult(data);
        } catch (err) {
            setError(
                err instanceof Error ? err.message : "Something went wrong"
            );
        } finally {
            setLoading(false);
        }
    }

    // Generate a Spotify playlist using the workout and discovery controls.
    async function generateWorkout() {
        setError(null);
        if (!API_URL) {
            setError(
                "Set VITE_API_URL to your backend URL before generating a playlist."
            );
            return;
        }
        if (!user) {
            setError(
                "Connect your Spotify account before generating a playlist."
            );
            return;
        }

        setLoading(true);
        setResult(null);
        setProgress(0);
        setProgressMessage("Preparing your workout...");
        try {
            const workout = getWorkoutRequest();
            const queryParams = new URLSearchParams();

            for (const genre of parseCommaSeparated(genresInput)) {
                queryParams.append("genres", genre);
            }
            for (const artist of parseCommaSeparated(artistsInput)) {
                queryParams.append("artists", artist);
            }
            for (const query of parseLines(searchQueriesInput)) {
                queryParams.append("search_queries", query);
            }

            queryParams.set(
                "include_user_top_tracks",
                String(includeUserTopTracks)
            );
            queryParams.set("top_tracks_time_range", topTracksTimeRange);
            queryParams.set(
                "expected_usable_rate",
                String(expectedUsableRatePercent / 100)
            );
            queryParams.set("max_candidates", String(maxCandidates));

            const endpoint = `${API_URL}/api/spotify/generate-playlist?${queryParams.toString()}`;
            const response = await fetch(endpoint, {
                method: "POST",
                credentials: "include",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(workout),
            });

            if (!response.ok) {
                const errorData = await response.json();
                if (Array.isArray(errorData.detail)) {
                    const messages = errorData.detail.map(
                        (item: { loc?: (string | number)[]; msg?: string }) => {
                            const location = item.loc
                                ? item.loc.join(".")
                                : "request";
                            return `${location}: ${
                                item.msg ?? "Invalid value"
                            }`;
                        }
                    );
                    throw new Error(messages.join("\n"));
                }
                if (typeof errorData.detail === "string")
                    throw new Error(errorData.detail);
                throw new Error(
                    `Playlist generation failed (${response.status})`
                );
            }

            // Read the progress updates sent by the backend.
            if (!response.body) {
                throw new Error(
                    "Could not read progress updates from the server."
                );
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            let buffer = "";

            while (true) {
                const { value, done } = await reader.read();

                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Each backend message is on a separate line.
                const messages = buffer.split("\n");

                // Keep any incomplete message for the next read.
                buffer = messages.pop() ?? "";

                for (const message of messages) {
                    if (!message.trim()) continue;

                    const event = JSON.parse(message);

                    if (event.type === "progress") {
                        setProgress(event.percent);
                        setProgressMessage(event.message);
                    }

                    if (event.type === "result") {
                        setResult(event.data as WorkoutResult);
                    }

                    if (event.type === "error") {
                        throw new Error(event.message);
                    }
                }
            }

            // Process any remaining data after the stream finishes.
            if (buffer.trim()) {
                const event = JSON.parse(buffer);

                if (event.type === "result") {
                    setResult(event.data as WorkoutResult);
                }

                if (event.type === "error") {
                    throw new Error(event.message);
                }
            }
        } catch (err) {
            setError(
                err instanceof Error ? err.message : "Something went wrong"
            );
        } finally {
            setLoading(false);
        }
    }

    const totalIntervalDistance = intervals.reduce(
        (total, interval) => total + interval.distance,
        0
    );

    return (
        <div className="app-shell">
            <header className="topbar">
                <a className="brand" href="#top" aria-label="Cadentic home">
                    <span className="brand-mark" aria-hidden="true">
                        <span />
                        <span />
                        <span />
                        <span />
                        <span />
                    </span>
                    <span>cadentic</span>
                </a>

                <nav className="main-nav" aria-label="Main navigation">
                    <button
                        type="button"
                        className={`nav-link ${
                            activePage === "generator" ? "active" : ""
                        }`}
                        onClick={() => setActivePage("generator")}
                        aria-pressed={activePage === "generator"}
                    >
                        Playlist generator
                    </button>

                    <button
                        type="button"
                        className={`nav-link ${
                            activePage === "how" ? "active" : ""
                        }`}
                        onClick={() => setActivePage("how")}
                        aria-pressed={activePage === "how"}
                    >
                        How it works
                    </button>
                </nav>

                <div className="topbar-actions">
                    {user ? (
                        <div className="spotify-session">
                            <span className="online-dot" />
                            <span className="session-name">
                                {user.spotify_display_name ??
                                    user.spotify_account_id}
                            </span>
                            <button
                                className="text-button"
                                onClick={signOutOfSpotify}
                                disabled={loading}
                            >
                                Log out
                            </button>
                        </div>
                    ) : (
                        <button
                            className="preview-pill"
                            onClick={loginWithSpotify}
                        >
                            <span className="online-dot" /> Connect Spotify
                        </button>
                    )}
                </div>
            </header>

            <main className="page-content" id="top">
                <div
                    key={activePage}
                    className={`page-view page-view-${activePage}`}
                >
                    {activePage === "generator" ? (
                        <>
                            <section
                                className="hero-banner"
                                aria-labelledby="hero-title"
                            >
                                <div className="hero-copy">
                                    <p className="eyebrow">
                                        BUILT FOR YOUR EVERY KILOMETRE
                                    </p>
                                    <h1 id="hero-title">
                                        Find your running rhythm.
                                    </h1>
                                    <p className="hero-description">
                                        Set the run. Shape the soundtrack. Build
                                        a playlist around your distance, pace
                                        and estimated step length.
                                    </p>
                                </div>
                                <div className="hero-art" aria-hidden="true">
                                    <img
                                        className="hero-image"
                                        src={heroImage}
                                        alt="Dartmoor"
                                    />
                                </div>
                            </section>

                            <div className="workspace-grid" id="generator">
                                <div className="setup-column">
                                    <section
                                        className="panel setup-panel"
                                        aria-labelledby="setup-title"
                                    >
                                        <div className="panel-heading">
                                            <div>
                                                <h2 id="setup-title">
                                                    Set up your run
                                                </h2>
                                                <p>
                                                    {workoutType === "steady"
                                                        ? "Tell us how you plan to move."
                                                        : "Build your workout, one interval at a time."}
                                                </p>
                                            </div>
                                        </div>

                                        <div className="field-block workout-type-field">
                                            <label htmlFor="workout-type">
                                                Workout type
                                            </label>
                                            <div className="select-wrap">
                                                <span
                                                    className="type-icon"
                                                    aria-hidden="true"
                                                >
                                                    {workoutType === "steady"
                                                        ? "→"
                                                        : "▥"}
                                                </span>
                                                <select
                                                    id="workout-type"
                                                    value={workoutType}
                                                    onChange={(event) => {
                                                        setWorkoutType(
                                                            event.target
                                                                .value as WorkoutType
                                                        );
                                                        setError(null);
                                                    }}
                                                >
                                                    <option value="steady">
                                                        Steady run
                                                    </option>
                                                    <option value="interval">
                                                        Interval run
                                                    </option>
                                                </select>
                                                <span
                                                    className="select-chevron"
                                                    aria-hidden="true"
                                                >
                                                    ⌄
                                                </span>
                                            </div>
                                            <p className="field-hint">
                                                {workoutType === "steady"
                                                    ? "One distance. One pace. A consistent rhythm from start to finish."
                                                    : "Change the rhythm across multiple run segments."}
                                            </p>
                                        </div>

                                        {workoutType === "steady" ? (
                                            <div className="steady-fields">
                                                <div className="form-grid steady-top-fields">
                                                    <div className="field-block">
                                                        <label htmlFor="distance">
                                                            Distance
                                                        </label>
                                                        <div className="input-with-unit">
                                                            <input
                                                                id="distance"
                                                                type="number"
                                                                min={0.1}
                                                                step={0.1}
                                                                value={distance}
                                                                onChange={(
                                                                    event
                                                                ) =>
                                                                    setDistance(
                                                                        Number(
                                                                            event
                                                                                .target
                                                                                .value
                                                                        )
                                                                    )
                                                                }
                                                            />
                                                            <span>km</span>
                                                        </div>
                                                    </div>
                                                    <div className="field-block pace-field">
                                                        <label htmlFor="pace-minutes">
                                                            Pace
                                                        </label>
                                                        <div className="pace-inputs">
                                                            <div className="input-with-unit">
                                                                <input
                                                                    id="pace-minutes"
                                                                    type="number"
                                                                    min={0}
                                                                    max={59}
                                                                    value={
                                                                        paceMinutes
                                                                    }
                                                                    onChange={(
                                                                        event
                                                                    ) =>
                                                                        setPaceMinutes(
                                                                            Number(
                                                                                event
                                                                                    .target
                                                                                    .value
                                                                            )
                                                                        )
                                                                    }
                                                                />
                                                                <span>min</span>
                                                            </div>
                                                            <span className="pace-separator">
                                                                :
                                                            </span>
                                                            <div className="input-with-unit">
                                                                <input
                                                                    aria-label="Pace seconds"
                                                                    type="number"
                                                                    min={0}
                                                                    max={59}
                                                                    value={
                                                                        paceSeconds
                                                                    }
                                                                    onChange={(
                                                                        event
                                                                    ) =>
                                                                        setPaceSeconds(
                                                                            Number(
                                                                                event
                                                                                    .target
                                                                                    .value
                                                                            )
                                                                        )
                                                                    }
                                                                />
                                                                <span>sec</span>
                                                            </div>
                                                        </div>
                                                        <span className="unit-caption">
                                                            / km
                                                        </span>
                                                    </div>
                                                </div>

                                                <div className="field-block step-length-field">
                                                    <label htmlFor="step-length">
                                                        Estimated step length
                                                    </label>
                                                    <div className="input-with-unit">
                                                        <input
                                                            id="step-length"
                                                            type="number"
                                                            min={0.3}
                                                            max={3}
                                                            step={0.01}
                                                            value={stepLength}
                                                            onChange={(event) =>
                                                                setStepLength(
                                                                    Number(
                                                                        event
                                                                            .target
                                                                            .value
                                                                    )
                                                                )
                                                            }
                                                        />
                                                        <span>m / step</span>
                                                    </div>
                                                </div>
                                            </div>
                                        ) : (
                                            <div className="interval-fields">
                                                <div className="interval-list-heading">
                                                    <h3>Your intervals</h3>
                                                    <span>
                                                        {intervals.length} sets
                                                        · in running order
                                                    </span>
                                                </div>
                                                <p className="field-hint interval-intro">
                                                    Enter an estimated length
                                                    for each set.
                                                </p>

                                                {intervals.map(
                                                    (interval, index) => (
                                                        <div
                                                            className="interval-card"
                                                            key={interval.id}
                                                        >
                                                            <div className="interval-card-heading">
                                                                <span>
                                                                    <b>
                                                                        {String(
                                                                            index +
                                                                                1
                                                                        ).padStart(
                                                                            2,
                                                                            "0"
                                                                        )}
                                                                    </b>{" "}
                                                                    Interval
                                                                </span>
                                                                <button
                                                                    className="icon-button"
                                                                    aria-label={`Remove interval ${
                                                                        index +
                                                                        1
                                                                    }`}
                                                                    title="Remove interval"
                                                                    onClick={() =>
                                                                        removeInterval(
                                                                            interval.id
                                                                        )
                                                                    }
                                                                    disabled={
                                                                        intervals.length <=
                                                                        1
                                                                    }
                                                                >
                                                                    ×
                                                                </button>
                                                            </div>
                                                            <div className="interval-input-grid">
                                                                <div className="field-block">
                                                                    <label
                                                                        htmlFor={`interval-distance-${interval.id}`}
                                                                    >
                                                                        Distance
                                                                    </label>
                                                                    <div className="input-with-unit">
                                                                        <input
                                                                            id={`interval-distance-${interval.id}`}
                                                                            type="number"
                                                                            min={
                                                                                0.1
                                                                            }
                                                                            step={
                                                                                0.1
                                                                            }
                                                                            value={
                                                                                interval.distance
                                                                            }
                                                                            onChange={(
                                                                                event
                                                                            ) =>
                                                                                intervalFieldChange(
                                                                                    interval.id,
                                                                                    "distance",
                                                                                    Number(
                                                                                        event
                                                                                            .target
                                                                                            .value
                                                                                    )
                                                                                )
                                                                            }
                                                                        />
                                                                        <span>
                                                                            km
                                                                        </span>
                                                                    </div>
                                                                </div>
                                                                <div className="field-block">
                                                                    <label
                                                                        htmlFor={`interval-minutes-${interval.id}`}
                                                                    >
                                                                        Pace
                                                                    </label>
                                                                    <div className="pace-inputs interval-pace-inputs">
                                                                        <div className="input-with-unit">
                                                                            <input
                                                                                id={`interval-minutes-${interval.id}`}
                                                                                type="number"
                                                                                min={
                                                                                    0
                                                                                }
                                                                                max={
                                                                                    59
                                                                                }
                                                                                value={
                                                                                    interval.paceMinutes
                                                                                }
                                                                                onChange={(
                                                                                    event
                                                                                ) =>
                                                                                    intervalFieldChange(
                                                                                        interval.id,
                                                                                        "paceMinutes",
                                                                                        Number(
                                                                                            event
                                                                                                .target
                                                                                                .value
                                                                                        )
                                                                                    )
                                                                                }
                                                                            />
                                                                            <span>
                                                                                min
                                                                            </span>
                                                                        </div>
                                                                        <span className="pace-separator">
                                                                            :
                                                                        </span>
                                                                        <div className="input-with-unit">
                                                                            <input
                                                                                aria-label={`Interval ${
                                                                                    index +
                                                                                    1
                                                                                } pace seconds`}
                                                                                type="number"
                                                                                min={
                                                                                    0
                                                                                }
                                                                                max={
                                                                                    59
                                                                                }
                                                                                value={
                                                                                    interval.paceSeconds
                                                                                }
                                                                                onChange={(
                                                                                    event
                                                                                ) =>
                                                                                    intervalFieldChange(
                                                                                        interval.id,
                                                                                        "paceSeconds",
                                                                                        Number(
                                                                                            event
                                                                                                .target
                                                                                                .value
                                                                                        )
                                                                                    )
                                                                                }
                                                                            />
                                                                            <span>
                                                                                sec
                                                                            </span>
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                                <div className="field-block interval-step-field">
                                                                    <label
                                                                        htmlFor={`interval-step-${interval.id}`}
                                                                    >
                                                                        Step
                                                                        length
                                                                    </label>
                                                                    <div className="input-with-unit">
                                                                        <input
                                                                            id={`interval-step-${interval.id}`}
                                                                            type="number"
                                                                            min={
                                                                                0.3
                                                                            }
                                                                            max={
                                                                                3
                                                                            }
                                                                            step={
                                                                                0.01
                                                                            }
                                                                            value={
                                                                                interval.stepLength
                                                                            }
                                                                            onChange={(
                                                                                event
                                                                            ) =>
                                                                                intervalFieldChange(
                                                                                    interval.id,
                                                                                    "stepLength",
                                                                                    Number(
                                                                                        event
                                                                                            .target
                                                                                            .value
                                                                                    )
                                                                                )
                                                                            }
                                                                        />
                                                                        <span>
                                                                            m
                                                                        </span>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    )
                                                )}

                                                <button
                                                    className="add-interval-button"
                                                    onClick={addInterval}
                                                >
                                                    <span>＋</span> Add interval
                                                </button>
                                                <p className="field-hint interval-total">
                                                    Total planned distance:{" "}
                                                    <strong>
                                                        {totalIntervalDistance.toFixed(
                                                            2
                                                        )}{" "}
                                                        km
                                                    </strong>
                                                </p>
                                            </div>
                                        )}

                                        <div className="step-length-note">
                                            <span
                                                className="note-icon"
                                                aria-hidden="true"
                                            >
                                                👣
                                            </span>
                                            <p>
                                                Step length is the distance from
                                                one footfall to the next, not a
                                                full two-step stride. An
                                                estimate is enough.
                                            </p>
                                        </div>

                                        <div className="generation-actions">
                                            <button
                                                className="primary-button"
                                                onClick={generateWorkout}
                                                disabled={loading}
                                            >
                                                {loading
                                                    ? "Generating…"
                                                    : "Generate running playlist"}
                                                <span
                                                    className="button-arrow"
                                                    aria-hidden="true"
                                                >
                                                    →
                                                </span>
                                            </button>

                                            {loading && (
                                                <div className="progress-container">
                                                    <div className="progress-heading">
                                                        <span>
                                                            {progressMessage}
                                                        </span>
                                                        <span>{progress}%</span>
                                                    </div>

                                                    <div
                                                        className="progress-track"
                                                        role="progressbar"
                                                        aria-valuenow={progress}
                                                        aria-valuemin={0}
                                                        aria-valuemax={100}
                                                    >
                                                        <div
                                                            className="progress-fill"
                                                            style={{
                                                                width: `${progress}%`,
                                                            }}
                                                        />
                                                    </div>
                                                </div>
                                            )}

                                            <p className="button-caption">
                                                Uses your distance, pace and
                                                estimated step length.
                                            </p>
                                            <button
                                                className="secondary-action"
                                                onClick={generatePreviewWorkout}
                                                disabled={loading}
                                            >
                                                Preview workout without Spotify
                                            </button>
                                            {!user && (
                                                <p className="button-caption">
                                                    Connect Spotify to create a
                                                    playlist.
                                                </p>
                                            )}
                                        </div>
                                    </section>

                                    <details className="panel secondary-panel">
                                        <summary>
                                            <span className="summary-title">
                                                Music discovery
                                            </span>
                                            <span className="summary-description">
                                                Genres, artists and Spotify
                                                listening history
                                            </span>
                                            <span className="summary-chevron">
                                                ＋
                                            </span>
                                        </summary>
                                        <div className="details-content">
                                            <p className="section-description">
                                                Add discovery sources. Results
                                                are combined and duplicate
                                                tracks are removed before BPM
                                                lookup.
                                            </p>
                                            <div className="field-block">
                                                <label htmlFor="genres">
                                                    Genres{" "}
                                                    <span>
                                                        (comma-separated)
                                                    </span>
                                                </label>
                                                <input
                                                    id="genres"
                                                    type="text"
                                                    value={genresInput}
                                                    onChange={(event) =>
                                                        setGenresInput(
                                                            event.target.value
                                                        )
                                                    }
                                                    placeholder="pop, rock, hip-hop, indie"
                                                />
                                            </div>
                                            <div className="field-block">
                                                <label htmlFor="artists">
                                                    Artists{" "}
                                                    <span>
                                                        (comma-separated)
                                                    </span>
                                                </label>
                                                <input
                                                    id="artists"
                                                    type="text"
                                                    value={artistsInput}
                                                    onChange={(event) =>
                                                        setArtistsInput(
                                                            event.target.value
                                                        )
                                                    }
                                                    placeholder="Milky Chance, The Weeknd"
                                                />
                                            </div>
                                            <div className="field-block">
                                                <label htmlFor="search-queries">
                                                    Custom Spotify search
                                                    queries{" "}
                                                    <span>(one per line)</span>
                                                </label>
                                                <textarea
                                                    id="search-queries"
                                                    value={searchQueriesInput}
                                                    onChange={(event) =>
                                                        setSearchQueriesInput(
                                                            event.target.value
                                                        )
                                                    }
                                                    rows={4}
                                                    placeholder={
                                                        "artist:Milky Chance\ntrack:Midnight City artist:M83\nindie electronic"
                                                    }
                                                />
                                                <p className="field-hint">
                                                    Use plain searches or
                                                    Spotify expressions such as{" "}
                                                    <code>
                                                        artist:Milky Chance
                                                    </code>
                                                    .
                                                </p>
                                            </div>
                                            <label className="checkbox-row">
                                                <input
                                                    type="checkbox"
                                                    checked={
                                                        includeUserTopTracks
                                                    }
                                                    onChange={(event) =>
                                                        setIncludeUserTopTracks(
                                                            event.target.checked
                                                        )
                                                    }
                                                />
                                                <span>
                                                    Include my Spotify top
                                                    tracks
                                                </span>
                                            </label>
                                            <div className="field-block">
                                                <label htmlFor="top-tracks-range">
                                                    Top tracks time range
                                                </label>
                                                <select
                                                    id="top-tracks-range"
                                                    value={topTracksTimeRange}
                                                    onChange={(event) =>
                                                        setTopTracksTimeRange(
                                                            event.target.value
                                                        )
                                                    }
                                                    disabled={
                                                        !includeUserTopTracks
                                                    }
                                                >
                                                    <option value="short_term">
                                                        Recent (about 4 weeks)
                                                    </option>
                                                    <option value="medium_term">
                                                        Medium term (about 6
                                                        months)
                                                    </option>
                                                    <option value="long_term">
                                                        Long term (about 1 year)
                                                    </option>
                                                </select>
                                            </div>
                                        </div>
                                    </details>

                                    <details className="panel secondary-panel">
                                        <summary>
                                            <span className="summary-title">
                                                Advanced settings
                                            </span>
                                            <span className="summary-description">
                                                Tune the size of the candidate
                                                track pool
                                            </span>
                                            <span className="summary-chevron">
                                                ＋
                                            </span>
                                        </summary>
                                        <div className="details-content">
                                            <p className="section-description">
                                                These values tune the backend's
                                                estimate. They do not specify
                                                the final playlist length.
                                            </p>
                                            <div className="form-grid advanced-grid">
                                                <div className="field-block">
                                                    <label htmlFor="usable-rate">
                                                        Expected usable BPM rate
                                                        (%)
                                                    </label>
                                                    <input
                                                        id="usable-rate"
                                                        type="number"
                                                        value={
                                                            expectedUsableRatePercent
                                                        }
                                                        onChange={(event) => {
                                                            const value =
                                                                Number(
                                                                    event.target
                                                                        .value
                                                                );
                                                            setExpectedUsableRatePercent(
                                                                Math.max(
                                                                    10,
                                                                    Math.min(
                                                                        80,
                                                                        value ||
                                                                            40
                                                                    )
                                                                )
                                                            );
                                                        }}
                                                        min={10}
                                                        max={80}
                                                        step={5}
                                                    />
                                                </div>
                                                <div className="field-block">
                                                    <label htmlFor="max-candidates">
                                                        Maximum candidate tracks
                                                    </label>
                                                    <input
                                                        id="max-candidates"
                                                        type="number"
                                                        value={maxCandidates}
                                                        onChange={(event) => {
                                                            const value =
                                                                Number(
                                                                    event.target
                                                                        .value
                                                                );
                                                            setMaxCandidates(
                                                                Math.max(
                                                                    10,
                                                                    Math.min(
                                                                        500,
                                                                        value ||
                                                                            500
                                                                    )
                                                                )
                                                            );
                                                        }}
                                                        min={10}
                                                        max={500}
                                                        step={5}
                                                    />
                                                </div>
                                            </div>
                                            <p className="field-hint">
                                                Lower the usable BPM rate if
                                                many candidate tracks have no
                                                BPM data.
                                            </p>
                                        </div>
                                    </details>
                                </div>

                                <section
                                    className="panel result-panel"
                                    aria-labelledby="result-title"
                                >
                                    <div className="result-heading">
                                        <h2 id="result-title">
                                            Workout result
                                        </h2>
                                        <span
                                            className={`status-pill ${
                                                result ? "status-success" : ""
                                            }`}
                                        >
                                            <span className="online-dot" />
                                            {result
                                                ? "Workout generated"
                                                : API_URL
                                                ? "Ready to generate"
                                                : "Backend not configured"}
                                        </span>
                                    </div>

                                    {error && (
                                        <div
                                            className="error-message"
                                            role="alert"
                                        >
                                            <strong>
                                                Something needs attention
                                            </strong>
                                            <p>{error}</p>
                                            <button
                                                className="dismiss-error"
                                                onClick={() => setError(null)}
                                                aria-label="Dismiss error"
                                            >
                                                ×
                                            </button>
                                        </div>
                                    )}

                                    {result ? (
                                        <div className="result-content">
                                            <p className="result-kicker">
                                                YOUR RUN. YOUR RHYTHM.
                                            </p>
                                            <h3>Your workout is ready.</h3>
                                            <p className="result-description">
                                                Duration:{" "}
                                                {Math.floor(
                                                    result.total_workout_seconds /
                                                        60
                                                )}{" "}
                                                min{" "}
                                                {result.total_workout_seconds %
                                                    60}{" "}
                                                sec
                                            </p>
                                            <div className="result-stats-grid">
                                                <div className="result-stat">
                                                    <span>
                                                        Workout duration
                                                    </span>
                                                    <strong>
                                                        {Math.floor(
                                                            result.total_workout_seconds /
                                                                60
                                                        )}
                                                        m{" "}
                                                        {result.total_workout_seconds %
                                                            60}
                                                        s
                                                    </strong>
                                                </div>
                                                <div className="result-stat">
                                                    <span>Run segments</span>
                                                    <strong>
                                                        {result.segments.length}
                                                    </strong>
                                                </div>
                                                <div className="result-stat">
                                                    <span>Warnings</span>
                                                    <strong>
                                                        {result.warnings.length}
                                                    </strong>
                                                </div>
                                            </div>
                                            <div className="result-detail-box">
                                                <h4>Workout segments</h4>

                                                {result.segments.length > 0 ? (
                                                    <div className="workout-segments">
                                                        {result.segments.map(
                                                            (item, index) => {
                                                                const segment =
                                                                    item;
                                                                // const segment = item as {
                                                                //     name: string;
                                                                //     duration_seconds: number;
                                                                //     target_spm: number;
                                                                //     min_spm: number;
                                                                //     max_spm: number;
                                                                //     selected_tracks: {
                                                                //         spotify_id: string;
                                                                //         name: string;
                                                                //         artist: string;
                                                                //         duration_seconds: number;
                                                                //         bpm: number | null;
                                                                //         spotify_url?:
                                                                //             | string
                                                                //             | null;
                                                                //         spotify_uri?:
                                                                //             | string
                                                                //             | null;
                                                                //     }[];
                                                                //     selected_duration_seconds: number;
                                                                //     duration_difference_seconds: number;
                                                                //     candidate_count: number;
                                                                // };

                                                                const formatTime =
                                                                    (
                                                                        seconds: number
                                                                    ) =>
                                                                        `${Math.floor(
                                                                            seconds /
                                                                                60
                                                                        )}:${String(
                                                                            seconds %
                                                                                60
                                                                        ).padStart(
                                                                            2,
                                                                            "0"
                                                                        )}`;

                                                                const difference =
                                                                    segment.duration_difference_seconds;

                                                                return (
                                                                    <section
                                                                        className="workout-segment-card"
                                                                        key={`${segment.name}-${index}`}
                                                                    >
                                                                        <div className="workout-segment-heading">
                                                                            <div>
                                                                                <span className="segment-number">
                                                                                    SEGMENT{" "}
                                                                                    {index +
                                                                                        1}
                                                                                </span>
                                                                                <h5>
                                                                                    {
                                                                                        segment.name
                                                                                    }
                                                                                </h5>
                                                                            </div>

                                                                            <span className="segment-duration">
                                                                                {formatTime(
                                                                                    segment.duration_seconds
                                                                                )}
                                                                            </span>
                                                                        </div>

                                                                        <div className="segment-cadence">
                                                                            <div>
                                                                                <strong>
                                                                                    {
                                                                                        segment.target_spm
                                                                                    }
                                                                                </strong>
                                                                                <span>
                                                                                    Target
                                                                                    SPM
                                                                                </span>
                                                                            </div>
                                                                            <div>
                                                                                <strong>
                                                                                    {
                                                                                        segment.min_spm
                                                                                    }

                                                                                    –
                                                                                    {
                                                                                        segment.max_spm
                                                                                    }
                                                                                </strong>
                                                                                <span>
                                                                                    Cadence
                                                                                    range
                                                                                </span>
                                                                            </div>
                                                                            <div>
                                                                                <strong>
                                                                                    {
                                                                                        segment.candidate_count
                                                                                    }
                                                                                </strong>
                                                                                <span>
                                                                                    Candidates
                                                                                </span>
                                                                            </div>
                                                                        </div>

                                                                        <div className="segment-tracks">
                                                                            <h6>
                                                                                <span>
                                                                                    ♫
                                                                                </span>{" "}
                                                                                Selected
                                                                                tracks
                                                                                <span className="track-count">
                                                                                    {
                                                                                        segment
                                                                                            .selected_tracks
                                                                                            .length
                                                                                    }
                                                                                </span>
                                                                            </h6>

                                                                            {segment.selected_tracks.map(
                                                                                (
                                                                                    track
                                                                                ) => {
                                                                                    const link =
                                                                                        track.spotify_url ??
                                                                                        track.spotify_uri;

                                                                                    return (
                                                                                        <div
                                                                                            className="segment-track"
                                                                                            key={
                                                                                                track.spotify_id
                                                                                            }
                                                                                        >
                                                                                            <div className="track-info">
                                                                                                <span className="track-title">
                                                                                                    {link ? (
                                                                                                        <a
                                                                                                            href={
                                                                                                                link
                                                                                                            }
                                                                                                            target="_blank"
                                                                                                            rel="noreferrer"
                                                                                                        >
                                                                                                            {
                                                                                                                track.name
                                                                                                            }
                                                                                                        </a>
                                                                                                    ) : (
                                                                                                        track.name
                                                                                                    )}
                                                                                                </span>
                                                                                                <span className="track-artist">
                                                                                                    {
                                                                                                        track.artist
                                                                                                    }
                                                                                                </span>
                                                                                            </div>

                                                                                            <span className="track-bpm">
                                                                                                {track.bpm !=
                                                                                                null
                                                                                                    ? `${Math.round(
                                                                                                          track.bpm
                                                                                                      )} BPM`
                                                                                                    : "BPM n/a"}
                                                                                            </span>
                                                                                            <span className="track-duration">
                                                                                                {formatTime(
                                                                                                    track.duration_seconds
                                                                                                )}
                                                                                            </span>
                                                                                        </div>
                                                                                    );
                                                                                }
                                                                            )}
                                                                        </div>

                                                                        <div className="segment-timing">
                                                                            <span>
                                                                                Music:{" "}
                                                                                <strong>
                                                                                    {formatTime(
                                                                                        segment.selected_duration_seconds
                                                                                    )}
                                                                                </strong>
                                                                            </span>
                                                                            <span>
                                                                                {difference >
                                                                                0
                                                                                    ? `＋${formatTime(
                                                                                          difference
                                                                                      )} over`
                                                                                    : difference <
                                                                                      0
                                                                                    ? `−${formatTime(
                                                                                          Math.abs(
                                                                                              difference
                                                                                          )
                                                                                      )} under`
                                                                                    : "Exact timing"}
                                                                            </span>
                                                                        </div>
                                                                    </section>
                                                                );
                                                            }
                                                        )}
                                                    </div>
                                                ) : (
                                                    <p>
                                                        No segments were
                                                        returned.
                                                    </p>
                                                )}
                                            </div>
                                            {result.warnings.length > 0 && (
                                                <div className="warning-list">
                                                    <h4>
                                                        Warnings / playlist
                                                        information
                                                    </h4>
                                                    <ul>
                                                        {result.warnings.map(
                                                            (
                                                                warning,
                                                                index
                                                            ) => (
                                                                <li key={index}>
                                                                    {warning}
                                                                </li>
                                                            )
                                                        )}
                                                    </ul>
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        <div className="result-content placeholder-content">
                                            <p className="result-kicker">
                                                YOUR RUN. YOUR RHYTHM.
                                            </p>
                                            <h3>
                                                The soundtrack starts with your
                                                run.
                                            </h3>
                                            <p className="result-description">
                                                Your generated workout and
                                                playlist will appear here once
                                                the request completes. Start by
                                                entering your distance, pace and
                                                estimated step length.
                                            </p>
                                            <div className="result-reserved">
                                                <p>
                                                    RESERVED FOR THE BACKEND
                                                    RESPONSE
                                                </p>
                                                <div className="reserved-columns">
                                                    <div>
                                                        <span className="reserved-line" />
                                                        <span>
                                                            Workout summary
                                                        </span>
                                                    </div>
                                                    <div>
                                                        <span className="reserved-line reserved-line-long" />
                                                        <span>
                                                            Playlist tracks
                                                        </span>
                                                    </div>
                                                    <div>
                                                        <span className="reserved-line" />
                                                        <span>
                                                            Playlist link
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    <p className="result-footer">
                                        <span
                                            className="headphone-icon"
                                            aria-hidden="true"
                                        >
                                            ♬
                                        </span>{" "}
                                        Made for movement. Powered by your
                                        inputs.
                                    </p>
                                </section>
                            </div>
                        </>
                    ) : (
                        <section
                            className="how-page"
                            aria-labelledby="how-title"
                        >
                            {/* INTRODUCTION */}
                            <div className="how-hero">
                                <p className="eyebrow">
                                    THE IDEA BEHIND CADENTIC
                                </p>

                                <h1 id="how-title">
                                    Your run sets the rhythm.
                                </h1>

                                <p>
                                    Cadentic uses your running pace and
                                    estimated step length to calculate a target
                                    cadence, then finds music to match the way
                                    you move.
                                </p>

                                <div className="how-flow">
                                    <span className="how-flow-step">
                                        Your workout
                                    </span>
                                    <span className="how-flow-arrow">→</span>
                                    <span className="how-flow-step">
                                        Target cadence
                                    </span>
                                    <span className="how-flow-arrow">→</span>
                                    <span className="how-flow-step">
                                        Your soundtrack
                                    </span>
                                </div>
                            </div>

                            {/* THREE STEPS */}
                            <div className="how-section-heading">
                                <div>
                                    <p className="eyebrow">THE PROCESS</p>
                                    <h2>How it works</h2>
                                </div>

                                <p>
                                    Three simple steps from workout details to
                                    playlist.
                                </p>
                            </div>

                            <div className="how-grid">
                                <article className="how-card">
                                    <div className="how-card-top">
                                        <span className="how-number">
                                            01 / INPUT
                                        </span>
                                        <span className="how-icon">↗</span>
                                    </div>

                                    <h3>Set up your run</h3>

                                    <p>
                                        Choose a steady or interval workout.
                                        Enter your distance, running pace and
                                        estimated step length to calculate your
                                        target cadence.
                                    </p>

                                    <span className="how-card-footer">
                                        Distance · Pace · Step length
                                    </span>
                                </article>

                                <article className="how-card">
                                    <div className="how-card-top">
                                        <span className="how-number">
                                            02 / DISCOVERY
                                        </span>
                                        <span className="how-icon">♫</span>
                                    </div>

                                    <h3>Find your rhythm</h3>

                                    <p>
                                        Discover tracks using your preferred
                                        genres, artists, custom searches and
                                        optionally your Spotify listening
                                        history. BPM data helps identify tracks
                                        that match your cadence.
                                    </p>

                                    <span className="how-card-footer">
                                        Spotify · BPM · Music discovery
                                    </span>
                                </article>

                                <article className="how-card">
                                    <div className="how-card-top">
                                        <span className="how-number">
                                            03 / PLAYLIST
                                        </span>
                                        <span className="how-icon">✓</span>
                                    </div>

                                    <h3>Enjoy the run</h3>

                                    <p>
                                        Suitable tracks are selected for each
                                        workout segment and assembled into a
                                        private Spotify playlist, ready for your
                                        next run.
                                    </p>

                                    <span className="how-card-footer">
                                        Track matching · Playlist creation
                                    </span>
                                </article>
                            </div>

                            {/* SMALL INFORMATION PANEL */}
                            <div className="how-note">
                                <span className="how-note-mark">i</span>
                                <p>
                                    <strong>A note on cadence.</strong> Your
                                    target is estimated from the information you
                                    provide. Your actual running cadence may
                                    vary during a workout.
                                </p>
                            </div>
                        </section>
                    )}
                </div>

                <footer className="page-footer">
                    <p>
                        <strong>cadentic</strong>
                        <span>/</span> Run to your own rhythm.
                    </p>
                    <div className="footer-meta">
                        <span aria-hidden="true">⌁</span> Metric units ·
                        kilometres &amp; metres
                    </div>
                    <a
                        href="https://getsongbpm.com"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="attribution"
                    >
                        BPM data provided by GetSongBPM
                    </a>
                </footer>

                {activePage === "generator" && (
                    <details className="developer-tools">
                        <summary>Developer debugging tools</summary>
                        <div>
                            <button
                                className="outline-button"
                                onClick={searchSpotfy}
                                disabled={loading}
                            >
                                Test Spotify search
                            </button>
                            <button
                                className="outline-button"
                                onClick={getBpm}
                                disabled={loading}
                            >
                                Test BPM lookup
                            </button>
                        </div>
                    </details>
                )}
            </main>
        </div>
    );
}

export default App;
