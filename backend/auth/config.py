"""
config.py

Configuration for the backend-owned authentication/session layer.
"""

# ==================================================
# Imports and Configuration
# ==================================================

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# ==================================================
# Dataclass & Helper Functions
# ==================================================


@dataclass(frozen=True)
class AuthSettings:
    spotify_client_id: str
    spotify_client_secret: str
    spotify_redirect_uri: str
    frontend_url: str
    database_path: str
    encryption_key: str
    session_ttl_seconds: int
    oauth_state_ttl_seconds: int
    cookie_name: str
    oauth_state_cookie_name: str
    cookie_secure: bool
    cookie_samesite: str


def get_auth_settings() -> AuthSettings:
    """Load full auth settings, failing only when auth is actually used."""

    return AuthSettings(
        spotify_client_id=_required("SPOTIFY_CLIENT_ID"),
        spotify_client_secret=_required("SPOTIFY_CLIENT_SECRET"),
        spotify_redirect_uri=_required("SPOTIFY_REDIRECT_URI"),
        frontend_url=get_frontend_url(),
        database_path=os.getenv("AUTH_DATABASE_PATH", "./data/auth.db"),
        encryption_key=_required("SESSION_ENCRYPTION_KEY"),
        session_ttl_seconds=int(os.getenv("APP_SESSION_TTL_SECONDS", "2592000")),
        oauth_state_ttl_seconds=int(os.getenv("OAUTH_STATE_TTL_SECONDS", "300")),
        cookie_name=os.getenv("APP_SESSION_COOKIE", "running_playlist_session"),
        oauth_state_cookie_name=os.getenv(
            "SPOTIFY_STATE_COOKIE", "running_playlist_spotify_state"
        ),
        cookie_secure=_env_bool("COOKIE_SECURE", False),
        cookie_samesite=os.getenv("COOKIE_SAMESITE", "lax").lower(),
    )


def get_frontend_url() -> str:
    """Get the frontend URL from the environment, defaulting to localhost for development."""
    return os.getenv("FRONTEND_URL", "http://127.0.0.1:5173").rstrip("/")


def _required(name: str) -> str:
    """Get a required environment variable, raising an error if it's not set."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def _env_bool(name: str, default: bool) -> bool:
    """Get a boolean environment variable, returning a default if it's not set."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
