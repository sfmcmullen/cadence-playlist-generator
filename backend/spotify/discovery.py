"""Discover a sufficiently large Spotify candidate pool and enrich tracks with BPM.

The search target accounts for two separate losses:
1. tracks for which no reliable BPM can be found;
2. tracks whose tempo does not match the workout cadence.

Spotify Search returns at most 10 tracks per request, so searches are paginated
and queried round-robin until the unique candidate target is met or sources end.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
from collections.abc import Sequence
from collections import Counter

import httpx

from ..core.models import Track
from .bpm import BpmProvider
from .client import SpotifyAPIError, SpotifyClient

logger = logging.getLogger(__name__)
# Configure logging to display INFO level messages and above, with a specific formatting
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

DEFAULT_GENRES = ("pop", "rock", "hip-hop")
AVERAGE_TRACK_DURATION_SECONDS = 210
EXPECTED_CADENCE_MATCH_RATE = 0.25
CANDIDATE_BUFFER = 10
MIN_CANDIDATES = 10
DEFAULT_MAX_CANDIDATES = 500
MAX_CANDIDATES_ALLOWED = 500
SEARCH_PAGE_SIZE = 10
MAX_SEARCH_OFFSET = 1000
MAX_CONCURRENT_BPM_LOOKUPS = 4
TOP_TRACKS_LIMIT = 50


def estimate_candidate_count(
    workout_duration_seconds: int,
    *,
    expected_usable_rate: float = 0.40,
    expected_cadence_match_rate: float = EXPECTED_CADENCE_MATCH_RATE,
    safety_factor: float = CANDIDATE_BUFFER,
    min_candidates: int = MIN_CANDIDATES,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> int:
    """Estimate raw candidates needed to fill a workout segment/run.

    ``expected_usable_rate`` is the proportion expected to receive a BPM.
    ``expected_cadence_match_rate`` is the proportion of BPM-enriched tracks
    expected to be within the matcher's cadence tolerance. The latter is an
    explicit heuristic: log real counts and tune it with observed results.
    """
    if workout_duration_seconds <= 0:
        raise ValueError("Workout duration must be positive.")
    if not 0 < expected_usable_rate <= 1:
        raise ValueError("Expected usable rate must be between 0 and 1.")
    if not 0 < expected_cadence_match_rate <= 1:
        raise ValueError("Expected cadence-match rate must be between 0 and 1.")
    if safety_factor < 1:
        raise ValueError("Safety factor must be at least 1.")
    if min_candidates < 1 or max_candidates < min_candidates:
        raise ValueError("Invalid candidate count limits.")

    # Estimate how many full-length tracks will cover the workout.
    tracks_needed = math.ceil(workout_duration_seconds / AVERAGE_TRACK_DURATION_SECONDS)

    # A candidate must survive BOTH BPM lookup and cadence matching.
    estimated_yield = expected_usable_rate * expected_cadence_match_rate
    raw_target = math.ceil((tracks_needed / estimated_yield) * safety_factor)

    return min(max_candidates, max(min_candidates, raw_target))


def _build_search_queries(
    *,
    genres: Sequence[str] | None,
    artists: Sequence[str] | None,
    search_queries: Sequence[str] | None,
) -> list[str]:
    """Convert discovery preferences into independent Spotify queries."""
    queries: list[str] = []

    # Custom Spotify queries allow terms like "artist:Milky Chance" or
    # "track:Midnight City artist:M83" and broad free-text searches.
    for query in search_queries or []:
        cleaned = query.strip()
        if cleaned:
            queries.append(cleaned)

    for artist in artists or []:
        cleaned = artist.strip()
        if cleaned:
            queries.append(f'artist:"{cleaned}"')

    for genre in genres or []:
        cleaned = genre.strip()
        if not cleaned:
            continue
        if cleaned.casefold() == "hip hop":
            cleaned = "hip-hop"
        queries.append(f"genre:{cleaned}")

    # Only use defaults when the user supplied no effective source at all.
    if not queries:
        queries = [f"genre:{genre}" for genre in DEFAULT_GENRES]

    # A query can be entered in both the artist field and custom search field.
    # Do not waste requests on exact duplicate strings.
    return list(dict.fromkeys(queries))


async def infer_user_top_genres(
    spotify: SpotifyClient,
    *,
    time_range: str = "medium_term",
    limit: int = 50,
    max_genres: int = 8,
) -> tuple[list[str], list[str]]:
    """Infer likely genres from the user's top artists.

    Returns:
        A tuple containing inferred genres and top artist names.
    """

    top_artists = await spotify.get_user_top_artists(
        limit=limit,
        time_range=time_range,
    )

    # Count how often each genre occurs among the user's top artists.
    genre_counts: Counter[str] = Counter()

    for artist in top_artists:
        for genre in artist.get("genres") or []:
            if isinstance(genre, str) and genre.strip():
                genre_counts[genre.strip().casefold()] += 1

    top_genres = [genre for genre, _ in genre_counts.most_common(max_genres)]

    # These names provide a personalised fallback if Spotify supplies
    # no genre metadata for its top artists.
    artist_names = [
        artist["name"].strip()
        for artist in top_artists
        if isinstance(artist.get("name"), str) and artist["name"].strip()
    ]

    return top_genres, artist_names


async def build_spotify_song_pool(
    spotify: SpotifyClient,
    bpm_provider: BpmProvider,
    *,
    workout_duration_seconds: int,
    genres: Sequence[str] | None = None,
    artists: Sequence[str] | None = None,
    search_queries: Sequence[str] | None = None,
    include_user_top_tracks: bool = True,
    top_tracks_time_range: str = "medium_term",
    market: str = "GB",
    expected_usable_rate: float = 0.40,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> list[Track]:
    """Discover unique candidate tracks and retain those with a positive BPM.

    `max_candidates` is a hard upper bound, not the desired number of results.
    The target is calculated from duration, BPM yield and cadence-match yield.
    """
    if not 10 <= max_candidates <= MAX_CANDIDATES_ALLOWED:
        raise ValueError(
            f"max_candidates must be between 10 and {MAX_CANDIDATES_ALLOWED}."
        )

    # Only infer personal preferences when the user supplied no
    # non-empty genres, artists or custom search queries.
    manual_preferences = any(
        value.strip()
        for values in (genres, artists, search_queries)
        if values
        for value in values
        if isinstance(value, str)
    )

    if not manual_preferences:
        try:
            inferred_genres, top_artist_names = await infer_user_top_genres(
                spotify,
                time_range=top_tracks_time_range,
            )

            if inferred_genres:
                # Spotify returned usable genre metadata.
                genres = inferred_genres

                logger.info(
                    "No discovery preferences supplied. "
                    "Using inferred top genres: %s",
                    inferred_genres,
                )

            elif top_artist_names:
                # Artist genre metadata was empty or unavailable.
                # Use the user's top artists rather than generic defaults.
                artists = top_artist_names[:10]

                logger.warning(
                    "Spotify returned no usable top-artist genres. "
                    "Falling back to top artists: %s",
                    artists,
                )

            else:
                # Leave preferences empty; _build_search_queries()
                # will use the standard default genres.
                logger.warning(
                    "Could not infer top genres or top artists. "
                    "Using default discovery genres."
                )

        except (SpotifyAPIError, httpx.HTTPError, TimeoutError, ValueError) as exc:
            logger.warning(
                "Automatic genre inference failed: %s. "
                "Using default discovery preferences.",
                exc,
            )

    target_count = estimate_candidate_count(
        workout_duration_seconds,
        expected_usable_rate=expected_usable_rate,
        max_candidates=max_candidates,
    )

    queries = _build_search_queries(
        genres=genres,
        artists=artists,
        search_queries=search_queries,
    )

    # log the discovery parameters for debugging and monitoring
    logger.info(
        "Starting Spotify discovery: target=%d, queries=[%s], top_tracks=%s, "
        "top_tracks_time_range=%s, market=%s",
        target_count,
        ", ".join(queries),
        include_user_top_tracks,
        top_tracks_time_range,
        market,
    )

    # Deduplication happens before BPM requests. Spotify's sources overlap,
    # especially top tracks plus artist/genre searches.
    discovered: dict[str, Track] = {}

    if include_user_top_tracks:
        try:
            top_tracks = await spotify.get_user_top_tracks(
                limit=TOP_TRACKS_LIMIT,
                time_range=top_tracks_time_range,
            )
            raw_top_count = len(top_tracks)
            unique_before = len(discovered)
            for track in top_tracks:
                if track.spotify_id not in discovered:
                    discovered[track.spotify_id] = track
                if len(discovered) >= target_count:
                    break
            logger.info(
                "Top-track source: returned=%d, new_unique=%d, pool=%d/%d",
                raw_top_count,
                len(discovered) - unique_before,
                len(discovered),
                target_count,
            )

        except (SpotifyAPIError, httpx.HTTPError, TimeoutError) as exc:
            # A missing `user-top-read` scope or transient issue should not
            # prevent genre/artist/custom search from running.
            logger.warning("Could not fetch Spotify top tracks: %s", exc)

        # Paginate each source in round-robin order.
        # Do not stop just because Spotify returns fewer than 10 tracks:
        # the current API's default page size is 5, and short pages can
        # still have further results available.

        offsets = {query: 0 for query in queries}
        per_query_raw = {query: 0 for query in queries}
        per_query_unique = {query: 0 for query in queries}
        per_query_pages = {query: 0 for query in queries}

        # Remember the last page returned by each individual query.
        # This prevents an infinite loop if Spotify repeats a page.
        last_page_ids: dict[str, tuple[str, ...] | None] = {
            query: None for query in queries
        }

        active_queries = list(queries)

        while active_queries and len(discovered) < target_count:
            for query in list(active_queries):
                if len(discovered) >= target_count:
                    break

                offset = offsets[query]

                # Spotify Search supports offsets up to 1000.
                if offset > MAX_SEARCH_OFFSET:
                    logger.info(
                        "Stopping query %r: maximum search offset reached.",
                        query,
                    )
                    active_queries.remove(query)
                    continue

                page = await spotify.search_tracks(
                    query,
                    market=market,
                    limit=SEARCH_PAGE_SIZE,
                    offset=offset,
                )

                per_query_pages[query] += 1
                per_query_raw[query] += len(page)

                # An empty page means there are no more results for
                # this query, so it can safely be removed.
                if not page:
                    logger.info(
                        "Search source %r returned no results at offset %d.",
                        query,
                        offset,
                    )
                    active_queries.remove(query)
                    continue

                page_ids = tuple(track.spotify_id for track in page)

                # Protect against an API/client response that ignores the
                # offset and repeatedly returns exactly the same page.
                if page_ids == last_page_ids[query]:
                    logger.warning(
                        "Stopping query %r: identical page returned at offset %d.",
                        query,
                        offset,
                    )
                    active_queries.remove(query)
                    continue

                last_page_ids[query] = page_ids

                # Advance by the number actually returned, not the requested
                # page size. For example, if Spotify returns 5, next offset = 5.
                offsets[query] += len(page)

                added = 0

                for track in page:
                    if track.spotify_id not in discovered:
                        discovered[track.spotify_id] = track
                        per_query_unique[query] += 1
                        added += 1

                    if len(discovered) >= target_count:
                        break

                logger.info(
                    "Search source %r page=%d offset=%d returned=%d "
                    "new_unique=%d pool=%d/%d",
                    query,
                    per_query_pages[query],
                    offset,
                    len(page),
                    added,
                    len(discovered),
                    target_count,
                )

                # IMPORTANT:
                # Do not remove the query because len(page) is less than
                # SEARCH_PAGE_SIZE. Continue paging until an empty page,
                # a repeated page, the offset limit, or the target is reached.

    logger.info(
        "Discovery complete: target=%d, unique_raw=%d, search_queries=%d, "
        "top_tracks_enabled=%s",
        target_count,
        len(discovered),
        len(queries),
        include_user_top_tracks,
    )
    for query in queries:
        logger.info(
            "Discovery source %r: returned=%d, new_unique=%d",
            query,
            per_query_raw[query],
            per_query_unique[query],
        )

    candidates = list(discovered.values())
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_BPM_LOOKUPS)

    # Coroutine to enrich a single track with BPM, respecting the concurrency limit (semaphore).
    async def enrich_one(track: Track) -> Track | None:
        async with semaphore:
            try:
                enriched = await bpm_provider.enrich(track)
            except (
                RuntimeError,
                httpx.HTTPError,
                TimeoutError,
                ValueError,
                TypeError,
                KeyError,
            ) as exc:
                logger.warning(
                    "BPM enrichment failed for %r by %s: %s",
                    track.name,
                    track.artist,
                    exc,
                )
                return None

            if enriched.bpm is None or enriched.bpm <= 0:
                return None
            return enriched

    enriched_results = await asyncio.gather(
        *(enrich_one(track) for track in candidates)
    )
    song_pool = [track for track in enriched_results if track is not None]

    logger.info(
        "BPM enrichment complete: %d/%d tracks have usable BPM data.",
        len(song_pool),
        len(candidates),
    )

    if len(discovered) < target_count:
        logger.warning(
            "Candidate target underfilled: wanted %d unique tracks but found %d. "
            "Sources may be exhausted or search results may overlap.",
            target_count,
            len(discovered),
        )

    # Shuffle the final song pool to avoid any ordering bias from the discovery sources.
    random.shuffle(song_pool)

    return song_pool
