"""
auth.py

Handles Spotify OAuth flow. Application sessions and stored credentials are managed in ``backend.auth``.
"""

# ==================================================
# Imports and Configuration
# ==================================================

from __future__ import annotations

import base64
from dataclasses import dataclass
from time import time
from urllib.parse import urlencode

import httpx

SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

# ==================================================
# High-Level OAuth Flow Diagram
# ==================================================
"""
[ User / Browser ]             [ FastAPI Backend ]             [ Spotify API ]
        │                               │                             │
        │ ─── 1. GET /auth/spotify ───► │                             │
        │                               │ ── Generates State & Cookie │
        │ ◄── 307 Redirect to Spotify ─ │                             │
        │                                                             │
        │ ────────────────── 2. User Grants Access ─────────────────► │
        │ ◄───────────────── 3. Redirect back with Code & State ──────│
        │                                                             │
        │ ─── 4. GET /auth/spotify/callback?code=...&state=... ─────► │
        │                               │ ── Validate State (SQLite)  │
        │                               │ ── Exchange Code ─────────► │
        │                               │ ◄─ Tokens Returned ──────── │
        │                               │ ── Get User Profile ──────► │
        │                               │ ◄─ Profile Data Returned ── │
        │                               │ ── Save Session (SQLite)    │
        │ ◄── 303 Redirect Frontend ────│                             │
        │     (Sets Session Cookie)     │                             │
"""

# ==================================================
# Exception Classes
# ==================================================


class SpotifyAuthorizationError(RuntimeError):
    """Raised when Spotify rejects an OAuth token exchange or refresh."""

    def __init__(self, message: str, *, spotify_error: str | None = None) -> None:
        super().__init__(message)
        self.spotify_error = spotify_error


class InvalidRefreshTokenError(SpotifyAuthorizationError):
    """Raised when Spotify says the refresh token is no longer valid."""


# ==================================================
# Data Classes
# ==================================================


@dataclass(frozen=True)
class SpotifyToken:
    """Represents a Spotify OAuth token, including access and refresh tokens, expiration time, and scope."""

    access_token: str
    refresh_token: str
    expires_at: float
    scope: str | None = None

    @property
    def expired(self) -> bool:
        """Returns True if the access token is expired or will expire within 60 seconds."""
        return time() >= self.expires_at - 60


# ==================================================
# OAuth Functions
# ==================================================


def authorization_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    *,
    public_playlists: bool = False,
) -> str:
    """Generate the Spotify authorization URL for the user to grant access to the application."""

    scopes = ["user-read-private", "playlist-modify-private"]
    if public_playlists:
        scopes.append("playlist-modify-public")

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
    }
    return f"{SPOTIFY_AUTHORIZE_URL}?{urlencode(params)}"


def _basic_auth(client_id: str, client_secret: str) -> str:
    """Return the Basic Authorization header value for Spotify API requests."""
    credentials = f"{client_id}:{client_secret}".encode("utf-8")
    encoded = base64.b64encode(credentials).decode("ascii")
    return f"Basic {encoded}"


async def exchange_code(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> SpotifyToken:
    """Exchange an authorization code for Spotify access and refresh tokens."""

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            SPOTIFY_TOKEN_URL,
            headers={"Authorization": _basic_auth(client_id, client_secret)},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )

    data = _parse_oauth_response(response, "Spotify token exchange failed")
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        raise SpotifyAuthorizationError("Spotify did not return a refresh token")

    return SpotifyToken(
        access_token=data["access_token"],
        refresh_token=refresh_token,
        expires_at=time() + int(data["expires_in"]),
        scope=data.get("scope"),
    )


async def refresh_access_token(
    token: SpotifyToken,
    client_id: str,
    client_secret: str,
) -> SpotifyToken:
    """
    Refresh an expired Spotify access token.

    Spotify may rotate the refresh token. When it does not return a new one,
    the previously stored refresh token remains valid and is retained.
    """

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            SPOTIFY_TOKEN_URL,
            headers={"Authorization": _basic_auth(client_id, client_secret)},
            data={
                "grant_type": "refresh_token",
                "refresh_token": token.refresh_token,
            },
        )

    if response.status_code == 400:
        try:
            data = response.json()
        except ValueError:
            data = {}
        if data.get("error") == "invalid_grant":
            raise InvalidRefreshTokenError(
                "Spotify refresh token is invalid or expired",
                spotify_error="invalid_grant",
            )

    data = _parse_oauth_response(response, "Spotify token refresh failed")
    return SpotifyToken(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", token.refresh_token),
        expires_at=time() + int(data["expires_in"]),
        scope=data.get("scope", token.scope),
    )


def _parse_oauth_response(response: httpx.Response, context: str) -> dict:
    """Parse the JSON response from Spotify's OAuth endpoints and raise an error if the response indicates failure."""
    if response.status_code >= 400:
        try:
            data = response.json()
        except ValueError:
            data = {}
        detail = data.get("error_description") or data.get("error") or response.text
        raise SpotifyAuthorizationError(
            f"{context}: {detail}",
            spotify_error=data.get("error"),
        )

    try:
        return response.json()
    except ValueError as exc:
        raise SpotifyAuthorizationError(f"{context}: invalid JSON response") from exc
