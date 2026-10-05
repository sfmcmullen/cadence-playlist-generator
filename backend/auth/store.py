"""
store.py

Persistent, server-side session store for Spotify OAuth tokens and user information.

SQLite used here due to dependency-free nature and simplicity.
Refresh/access tokens are encrypted before storage using Fernet symmetric encryption.
"""

# ==================================================
# Imports and Configuration
# ==================================================

from __future__ import annotations

import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from ..spotify.auth import SpotifyToken

# ==================================================
# Dataclass for Stored Session
# ==================================================


@dataclass(frozen=True)
class StoredSession:
    session_id: str
    spotify_account_id: str
    spotify_display_name: str | None
    access_token: str
    refresh_token: str
    access_token_expires_at: float
    created_at: float
    expires_at: float
    scope: str | None

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at


# ==================================================
# SQLite-backed Session Store
# ==================================================


class SessionStore:

    def __init__(
        self,
        database_path: str,
        encryption_key: str,
        *,
        session_ttl_seconds: int = 2_592_000,
        oauth_state_ttl_seconds: int = 300,
    ) -> None:
        """Set up a new session store backed by SQLite."""
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.fernet = Fernet(encryption_key.encode("ascii"))
        self.session_ttl_seconds = session_ttl_seconds
        self.oauth_state_ttl_seconds = oauth_state_ttl_seconds
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        """Create a new SQLite connection with the appropriate settings."""
        connection = sqlite3.connect(self.database_path)
        # Return rows as dictionaries, rather than tuples
        connection.row_factory = sqlite3.Row
        # Enable 'Write-Ahead Logging' for better concurrency and performance
        connection.execute("PRAGMA journal_mode=WAL")
        # Enforce foreign key constraints for data integrity
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialise(self) -> None:
        """Create the necessary tables and indexes in the SQLite database if they don't already exist."""
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS oauth_states (
                    state TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    spotify_account_id TEXT NOT NULL,
                    spotify_display_name TEXT,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT NOT NULL,
                    access_token_expires_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    scope TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_expires_at
                    ON sessions(expires_at);
                CREATE INDEX IF NOT EXISTS idx_oauth_states_expires_at
                    ON oauth_states(expires_at);
                """)

            # Table 1: oauth_states
            # - Store single-use OAuth states for CSRF protection, generated during 'GET /auth/spotfy'.
            # Table 2: sessions
            # - Map user's secret session_ID cookie to Spotify credentials.
            # Indexes:
            # - idx_sessions_expires_at: Optimize queries for expired sessions.
            # - idx_oauth_states_expires_at: Optimize queries for expired OAuth states.

    def cleanup_expired(self) -> None:
        """Remove expired OAuth states and sessions from the database to prevent bloat and potential security issues."""
        now = time.time()
        with self._connect() as connection:
            connection.execute("DELETE FROM oauth_states WHERE expires_at <= ?", (now,))
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))

    def create_oauth_state(self) -> str:
        """Generate a new single-use OAuth state for CSRF protection during the Spotify OAuth flow."""
        self.cleanup_expired()
        state = secrets.token_urlsafe(32)
        now = time.time()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO oauth_states(state, created_at, expires_at) VALUES (?, ?, ?)",
                (state, now, now + self.oauth_state_ttl_seconds),
            )
        return state

    def consume_oauth_state(self, state: str) -> bool:
        """Check if the provided OAuth state is valid and has not expired.
        If valid, consume it (delete from DB) to prevent reuse."""
        now = time.time()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT expires_at FROM oauth_states WHERE state = ?",
                (state,),
            ).fetchone()
            if row is None:
                return False

            connection.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
            return float(row["expires_at"]) > now

    def create_session(
        self,
        token: SpotifyToken,
        *,
        spotify_account_id: str,
        spotify_display_name: str | None,
    ) -> str:
        """Create a new session for a user after successful Spotify OAuth authentication.
        The session stores encrypted Spotify credentials and user information."""

        self.cleanup_expired()
        session_id = secrets.token_urlsafe(32)
        now = time.time()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions(
                    session_id,
                    spotify_account_id,
                    spotify_display_name,
                    access_token,
                    refresh_token,
                    access_token_expires_at,
                    created_at,
                    expires_at,
                    scope
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    spotify_account_id,
                    spotify_display_name,
                    self._encrypt(token.access_token),
                    self._encrypt(token.refresh_token),
                    token.expires_at,
                    now,
                    now + self.session_ttl_seconds,
                    token.scope,
                ),
            )

        return session_id

    def get_session(self, session_id: str) -> StoredSession | None:
        """Retrieve a stored session by its session ID.
        If the session exists and is valid, return a StoredSession object."""
        self.cleanup_expired()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()

        if row is None:
            return None

        try:
            return StoredSession(
                session_id=row["session_id"],
                spotify_account_id=row["spotify_account_id"],
                spotify_display_name=row["spotify_display_name"],
                access_token=self._decrypt(row["access_token"]),
                refresh_token=self._decrypt(row["refresh_token"]),
                access_token_expires_at=float(row["access_token_expires_at"]),
                created_at=float(row["created_at"]),
                expires_at=float(row["expires_at"]),
                scope=row["scope"],
            )
        except InvalidToken as exc:
            self.delete_session(session_id)
            raise RuntimeError(
                "Stored Spotify credentials could not be decrypted"
            ) from exc

    def update_token(self, session_id: str, token: SpotifyToken) -> None:
        """Update the Spotify access and refresh tokens for an existing session."""
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE sessions
                SET access_token = ?,
                    refresh_token = ?,
                    access_token_expires_at = ?,
                    scope = ?
                WHERE session_id = ?
                """,
                (
                    self._encrypt(token.access_token),
                    self._encrypt(token.refresh_token),
                    token.expires_at,
                    token.scope,
                    session_id,
                ),
            )

    def delete_session(self, session_id: str) -> None:
        """Delete a session from the store, typically called when a session is expired or invalid."""
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE session_id = ?", (session_id,)
            )

    def _encrypt(self, value: str) -> str:
        return self.fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def _decrypt(self, value: str) -> str:
        return self.fernet.decrypt(value.encode("ascii")).decode("utf-8")
