import { useEffect, useState } from "react";
import type { Pace, WorkoutRequest, User, WorkoutResult } from "./types";

const API_URL = import.meta.env.VITE_API_URL;

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

    // Browser only stores session cookies, so we authenticate on page load to see if the user is logged in.
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

    // Spootify login and logout functions
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
            })
            .catch((error) => {
                console.error("Logout error:", error);
            });
    }

    // Debugging function to test Spotify search functionality
    function searchSpotfy() {
        fetch(`${API_URL}/spotify/search?q=Milky Chance`, {
            method: "GET",
            credentials: "include",
        })
            .then((response) => {
                if (!response.ok) {
                    throw new Error("Search failed");
                }
                return response.json();
            })
            .then((data) => {
                console.log("Search results:", data);
            })
            .catch((error) => {
                console.error("Search error:", error);
            });
    }

    // Function to build a WorkoutRequest from the current form state and send it to the backend API.
    async function generateWorkout() {
        setLoading(true);
        setError(null);
        setResult(null);

        try {
            // Build the WorkoutRequest object from the current form state
            const workout: WorkoutRequest = {
                distance_km: distance,
                pace: {
                    minutes: paceMinutes,
                    seconds: paceSeconds,
                },
                step_length_m: stepLength,
            };

            // Send the WorkoutRequest to the backend API and handle the response
            const response = await fetch(`${API_URL}/api/workouts/preview`, {
                method: "POST",
                credentials: "include",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(workout),
            });

            // Handle errors from the API response
            if (!response.ok) {
                const errorData = await response.json();
                setError(
                    errorData.detail ??
                        "Something went wrong. Please try again."
                );
                return;
            }

            // Parse the successful response and update the result state
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

    // --------------------------------------------------
    // Main Page Rendering
    // --------------------------------------------------
    return (
        <main>
            <h1>Running Playlist Generator</h1>

            {/* AUTH */}
            {user ? (
                <section>
                    <p>
                        Logged in as{" "}
                        <strong>
                            {user.spotify_display_name ??
                                user.spotify_account_id}
                        </strong>
                    </p>

                    <button onClick={signOutOfSpotify}>
                        Logout of Spotify
                    </button>
                </section>
            ) : (
                <section>
                    <p>You are not logged in to Spotify.</p>

                    <button onClick={loginWithSpotify}>
                        Login with Spotify
                    </button>
                </section>
            )}

            {/* WORKOUT INPUT */}
            <section>
                <h2>Workout</h2>

                <input
                    type="number"
                    value={distance}
                    onChange={(event) =>
                        setDistance(Number(event.target.value))
                    }
                    min={0}
                    step={0.1}
                />
                <input
                    type="number"
                    value={paceMinutes}
                    onChange={(event) =>
                        setPaceMinutes(Number(event.target.value))
                    }
                    min={0}
                    max={59}
                />
                <input
                    type="number"
                    value={paceSeconds}
                    onChange={(event) =>
                        setPaceSeconds(Number(event.target.value))
                    }
                    min={0}
                    max={59}
                />
                <input
                    type="number"
                    value={stepLength}
                    onChange={(event) =>
                        setStepLength(Number(event.target.value))
                    }
                    min={0}
                    max={5}
                    step={0.1}
                />

                <button onClick={generateWorkout} disabled={loading}>
                    {loading ? "Generating..." : "Generate Workout"}
                </button>
            </section>

            {/* ERRORS */}
            {error && (
                <section>
                    <p>
                        <strong>Error:</strong> {error}
                    </p>
                </section>
            )}

            {/* WORKOUT RESULTS */}

            {result && (
                <section>
                    <h2>Workout Result</h2>

                    <p>Duration: {result.duration_seconds} seconds</p>

                    {/* Temporary debugging output */}
                    {/* <pre>{JSON.stringify(result, null, 2)}</pre> */}

                    <p>Segments:</p>
                    <ul>
                        {result.segments.map((segment, index) => (
                            <li key={index}>{JSON.stringify(segment)}</li>
                        ))}
                    </ul>

                    <p>Warnings:</p>
                    <ul>
                        {result.warnings.map((warning, index) => (
                            <li key={index}>{warning}</li>
                        ))}
                    </ul>
                </section>
            )}

            {/* DEBUGGING */}
            <section>
                {/* debug for spotify search working */}
                <button onClick={searchSpotfy} disabled={loading}>
                    Search for tracks
                </button>
            </section>

            {/* BACKLINK */}
            <a
                href="https://getsongbpm.com"
                target="_blank"
                rel="noopener noreferrer"
            >
                BPM data provided by GetSongBPM
            </a>
        </main>
    );
}

export default App;
