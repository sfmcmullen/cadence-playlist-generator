"""
dependencies.py

FastAPI dependency functions for the backend-owned authentication/session layer.
"""

# ==================================================
# Imports and Configuration
# ==================================================

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from fastapi import HTTPException, Request

from ..spotify.auth import InvalidRefreshTokenError, SpotifyToken, refresh_access_token
from ..spotify.client import SpotifyClient
from .config import get_auth_settings
from .store import SessionStore

# ==================================================
# Dataclass for Authenticated Spotify
# ==================================================


@dataclass(frozen=True)
class AuthenticatedSpotify:
    session_id: str
    spotify_account_id: str
    spotify_display_name: str | None
    client: SpotifyClient


# ==================================================
# Dependency Functions
# ==================================================


@lru_cache(maxsize=1)
def get_store() -> SessionStore:
    """Get a cached instance of the session store. This is used as a FastAPI
    dependency to ensure that the same store instance is used across requests."""

    settings = get_auth_settings()
    return SessionStore(
        settings.database_path,
        settings.encryption_key,
        session_ttl_seconds=settings.session_ttl_seconds,
        oauth_state_ttl_seconds=settings.oauth_state_ttl_seconds,
    )


async def get_authenticated_spotify(request: Request) -> AuthenticatedSpotify:
    """Get the authenticated Spotify client for the current request.
    This is used as a FastAPI dependency to ensure that the user is
    authenticated with Spotify."""

    # Load the auth settings and session store
    settings = get_auth_settings()
    store = get_store()

    # Get the session ID from the request cookies and load the session from the store
    session_id = request.cookies.get(settings.cookie_name)
    if not session_id:
        raise HTTPException(status_code=401, detail="Spotify authentication required")

    session = store.get_session(session_id)
    if session is None or session.expired:
        # If the session is expired, delete it from the store to clean up
        if session is not None:
            store.delete_session(session_id)
        raise HTTPException(status_code=401, detail="Spotify session expired")

    # Check if the access token is expired and refresh it if necessary
    token = SpotifyToken(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_at=session.access_token_expires_at,
        scope=session.scope,
    )

    if token.expired:
        # If the access token is expired, attempt to refresh it using the refresh token
        try:
            refreshed = await refresh_access_token(
                token,
                settings.spotify_client_id,
                settings.spotify_client_secret,
            )
        # If the refresh token is invalid, delete the session and raise an HTTP 401 error
        except InvalidRefreshTokenError:
            store.delete_session(session_id)
            raise HTTPException(
                status_code=401,
                detail="Spotify authorization expired. Please connect Spotify again.",
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        store.update_token(session_id, refreshed)
        token = refreshed

    return AuthenticatedSpotify(
        session_id=session_id,
        spotify_account_id=session.spotify_account_id,
        spotify_display_name=session.spotify_display_name,
        client=SpotifyClient(token.access_token),
    )
