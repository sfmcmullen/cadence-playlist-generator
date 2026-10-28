import { useEffect, useState } from "react";
import type { WorkoutRequest, User, WorkoutResult } from "./types";

const API_URL = import.meta.env.VITE_API_URL;

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
    // States for user authentication and workout results
    const [user, setUser] = useState<User | null>(null);
    const [result, setResult] = useState<WorkoutResult | null>(null);

    // States for loading and error handling
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // States for workout form inputs
    const [distance, setDistance] = useState<number>(10);
    const [paceMinutes, setPaceMinutes] = useState<number>(5);
    const [paceSeconds, setPaceSeconds] = useState<number>(0);
    const [stepLength, setStepLength] = useState<number>(1.2);

    // States for music discovery preferences
    const [genresInput, setGenresInput] = useState("");
    const [artistsInput, setArtistsInput] = useState("");
    const [searchQueriesInput, setSearchQueriesInput] = useState("");
    const [includeUserTopTracks, setIncludeUserTopTracks] = useState(true);
    const [topTracksTimeRange, setTopTracksTimeRange] = useState("medium_term");

    // Pool-sizing controls. The backend still estimates the number of tracks
    // from workout duration; these values tune that estimate and its upper cap.
    const [expectedUsableRatePercent, setExpectedUsableRatePercent] =
        useState<number>(40);
    const [maxCandidates, setMaxCandidates] = useState<number>(300);

    // Check the application session when the page loads.
    useEffect(() => {
        checkAuthentication();
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
        window.location.href = `${API_URL}/auth/spotify`;
    }

    function signOutOfSpotify() {
        fetch(`${API_URL}/auth/logout`, {
            method: "POST",
            credentials: "include",
        })
            .then((response) => {
                if (!response.ok) {
                    throw new Error("Logout failed");
                }
                setUser(null);
                setResult(null);
            })
            .catch((logoutError) => {
                console.error("Logout error:", logoutError);
                setError("Could not log out of Spotify. Please try again.");
            });
    }

    // Temporary debugging function to test Spotify search functionality.
    function searchSpotfy() {
        fetch(`${API_URL}/spotify/search?q=Milky Chance`, {
            method: "GET",
            credentials: "include",
        })
            .then(async (response) => {
                if (!response.ok) {
                    throw new Error(`Search failed (${response.status})`);
                }
                return response.json();
            })
            .then((data) => console.log("Search results:", data))
            .catch((searchError) =>
                console.error("Search error:", searchError)
            );
    }

    // Temporary debugging function to test BPM retrieval functionality.
    function getBpm() {
        fetch(`${API_URL}/spotify/bpm?q=The Weeknd`, {
            method: "GET",
            credentials: "include",
        })
            .then(async (response) => {
                if (!response.ok) {
                    throw new Error(`BPM test failed (${response.status})`);
                }
                return response.json();
            })
            .then((data) => console.log("BPM results:", data))
            .catch((bpmError) => console.error("BPM error:", bpmError));
    }

    // Send a workout to the Spotify-independent preview endpoint.
    async function generatePreviewWorkout() {
        setLoading(true);
        setError(null);
        setResult(null);

        try {
            const workout: WorkoutRequest = {
                distance_km: distance,
                pace: {
                    minutes: paceMinutes,
                    seconds: paceSeconds,
                },
                step_length_m: stepLength,
            };

            const response = await fetch(`${API_URL}/api/workouts/preview`, {
                method: "POST",
                credentials: "include",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ workout }),
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

    // Generate a real Spotify playlist using the workout and discovery controls.
    async function generateWorkout() {
        setLoading(true);
        setError(null);
        setResult(null);

        try {
            const workout: WorkoutRequest = {
                distance_km: distance,
                pace: {
                    minutes: paceMinutes,
                    seconds: paceSeconds,
                },
                step_length_m: stepLength,
            };

            // The discovery options are FastAPI query parameters. Repeating a
            // parameter (e.g. genres=pop&genres=rock) is how FastAPI receives
            // a list[str] query parameter.
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

            console.log("WorkoutRequest:", workout);
            console.log("Discovery preferences:", {
                genres: parseCommaSeparated(genresInput),
                artists: parseCommaSeparated(artistsInput),
                search_queries: parseLines(searchQueriesInput),
                include_user_top_tracks: includeUserTopTracks,
                top_tracks_time_range: topTracksTimeRange,
                expected_usable_rate: expectedUsableRatePercent / 100,
                max_candidates: maxCandidates,
            });

            const response = await fetch(endpoint, {
                method: "POST",
                credentials: "include",
                headers: {
                    "Content-Type": "application/json",
                },
                // Keep the body shape currently used by the working endpoint.
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

                if (typeof errorData.detail === "string") {
                    throw new Error(errorData.detail);
                }

                throw new Error(
                    `Playlist generation failed (${response.status})`
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

    return (
        <main>
            <h1>Running Playlist Generator</h1>

            {/* SPOTIFY AUTHENTICATION */}
            <section>
                {user ? (
                    <>
                        <p>
                            Logged in as{" "}
                            <strong>
                                {user.spotify_display_name ??
                                    user.spotify_account_id}
                            </strong>
                        </p>
                        <button onClick={signOutOfSpotify} disabled={loading}>
                            Logout of Spotify
                        </button>
                    </>
                ) : (
                    <>
                        <p>You are not logged in to Spotify.</p>
                        <button onClick={loginWithSpotify}>
                            Login with Spotify
                        </button>
                    </>
                )}
            </section>

            {/* WORKOUT INPUTS */}
            <section>
                <h2>Workout</h2>

                <label>
                    Distance (km)
                    <input
                        type="number"
                        value={distance}
                        onChange={(event) =>
                            setDistance(Number(event.target.value))
                        }
                        min={0.1}
                        step={0.1}
                    />
                </label>

                <label>
                    Pace minutes per km
                    <input
                        type="number"
                        value={paceMinutes}
                        onChange={(event) =>
                            setPaceMinutes(Number(event.target.value))
                        }
                        min={0}
                        max={59}
                    />
                </label>

                <label>
                    Pace seconds
                    <input
                        type="number"
                        value={paceSeconds}
                        onChange={(event) =>
                            setPaceSeconds(Number(event.target.value))
                        }
                        min={0}
                        max={59}
                    />
                </label>

                <label>
                    Step length (metres per step)
                    <input
                        type="number"
                        value={stepLength}
                        onChange={(event) =>
                            setStepLength(Number(event.target.value))
                        }
                        min={0.3}
                        max={3}
                        step={0.1}
                    />
                </label>
            </section>

            {/* MUSIC DISCOVERY PREFERENCES */}
            <section>
                <h2>Music discovery</h2>
                <p>
                    Add one or more discovery sources. Results are combined and
                    duplicate tracks are removed before BPM lookup.
                </p>

                <label>
                    Genres (comma-separated)
                    <input
                        type="text"
                        value={genresInput}
                        onChange={(event) => setGenresInput(event.target.value)}
                        placeholder="pop, rock, hip-hop, indie"
                    />
                </label>

                <label>
                    Artists (comma-separated)
                    <input
                        type="text"
                        value={artistsInput}
                        onChange={(event) =>
                            setArtistsInput(event.target.value)
                        }
                        placeholder="Milky Chance, The Weeknd"
                    />
                </label>

                <label>
                    Custom Spotify search queries (one per line)
                    <textarea
                        value={searchQueriesInput}
                        onChange={(event) =>
                            setSearchQueriesInput(event.target.value)
                        }
                        rows={4}
                        placeholder={
                            "artist:Milky Chance\ntrack:Midnight City artist:M83\nindie electronic"
                        }
                    />
                </label>
                <p>
                    Use plain searches such as <code>indie electronic</code>, or
                    Spotify search expressions such as{" "}
                    <code>artist:Milky Chance</code>.
                </p>

                <label>
                    <input
                        type="checkbox"
                        checked={includeUserTopTracks}
                        onChange={(event) =>
                            setIncludeUserTopTracks(event.target.checked)
                        }
                    />
                    Include my Spotify top tracks
                </label>

                <label>
                    Top tracks time range
                    <select
                        value={topTracksTimeRange}
                        onChange={(event) =>
                            setTopTracksTimeRange(event.target.value)
                        }
                        disabled={!includeUserTopTracks}
                    >
                        <option value="short_term">
                            Recent (about 4 weeks)
                        </option>
                        <option value="medium_term">
                            Medium term (about 6 months)
                        </option>
                        <option value="long_term">
                            Long term (about 1 year)
                        </option>
                    </select>
                </label>
            </section>

            {/* POOL SIZING */}
            <section>
                <h2>Candidate pool size</h2>
                <p>
                    The backend estimates how many tracks to search for based on
                    your workout duration and the expected BPM success rate.
                    These settings tune that estimate; they do not specify the
                    final playlist length.
                </p>

                <label>
                    Expected usable BPM rate (%)
                    <input
                        type="number"
                        value={expectedUsableRatePercent}
                        onChange={(event) => {
                            const value = Number(event.target.value);
                            setExpectedUsableRatePercent(
                                Math.max(10, Math.min(80, value || 40))
                            );
                        }}
                        min={10}
                        max={80}
                        step={5}
                    />
                </label>
                <p>
                    Lower this value if many candidate tracks have no BPM data.
                    For example, 25% tells the backend to search more broadly
                    than 40% for the same workout.
                </p>

                <label>
                    Maximum candidate tracks
                    <input
                        type="number"
                        value={maxCandidates}
                        onChange={(event) => {
                            const value = Number(event.target.value);
                            setMaxCandidates(
                                Math.max(10, Math.min(500, value || 500))
                            );
                        }}
                        min={10}
                        max={500}
                        step={5}
                    />
                </label>
            </section>

            {/* GENERATION */}
            <section>
                <button onClick={generatePreviewWorkout} disabled={loading}>
                    {loading ? "Generating..." : "Generate Preview Workout"}
                </button>
                <button
                    onClick={generateWorkout}
                    disabled={loading || !user}
                    title={!user ? "Log in to Spotify first" : undefined}
                >
                    {loading ? "Generating..." : "Generate Spotify Playlist"}
                </button>
                {!user && (
                    <p>Log in to Spotify before generating a playlist.</p>
                )}
            </section>

            {/* ERRORS */}
            {error && (
                <section role="alert">
                    <p>
                        <strong>Error:</strong> {error}
                    </p>
                </section>
            )}

            {/* WORKOUT RESULTS */}
            {result && (
                <section>
                    <h2>Workout Result</h2>
                    <p>
                        Duration: {Math.floor(result.duration_seconds / 60)} min{" "}
                        {result.duration_seconds % 60} sec
                    </p>

                    <p>Segments:</p>
                    <ul>
                        {result.segments.map((segment, index) => (
                            <li key={index}>{JSON.stringify(segment)}</li>
                        ))}
                    </ul>

                    <p>Warnings / playlist information:</p>
                    <ul>
                        {result.warnings.map((warning, index) => (
                            <li key={index}>{warning}</li>
                        ))}
                    </ul>
                </section>
            )}

            {/* TEMPORARY DEBUGGING */}
            <details>
                <summary>Developer debugging tools</summary>
                <button onClick={searchSpotfy} disabled={loading}>
                    Test Spotify search
                </button>
                <button onClick={getBpm} disabled={loading}>
                    Test BPM lookup
                </button>
            </details>

            {/* GETSONGBPM ATTRIBUTION */}
            <p>
                BPM data provided by{" "}
                <a
                    href="https://getsongbpm.com"
                    target="_blank"
                    rel="noopener noreferrer"
                >
                    GetSongBPM
                </a>
            </p>
        </main>
    );
}

export default App;
