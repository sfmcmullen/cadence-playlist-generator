from pathlib import Path

from cryptography.fernet import Fernet

from backend.auth.store import SessionStore
from backend.spotify.auth import SpotifyToken


def test_oauth_state_is_one_time_use(tmp_path: Path) -> None:
    store = SessionStore(
        str(tmp_path / "auth.db"),
        Fernet.generate_key().decode(),
    )

    state = store.create_oauth_state()

    assert store.consume_oauth_state(state) is True
    assert store.consume_oauth_state(state) is False


def test_session_tokens_are_persisted_and_decrypted(tmp_path: Path) -> None:
    database = tmp_path / "auth.db"
    key = Fernet.generate_key().decode()

    store = SessionStore(str(database), key)
    token = SpotifyToken(
        access_token="access-secret",
        refresh_token="refresh-secret",
        expires_at=9_999_999_999,
        scope="playlist-modify-private",
    )

    session_id = store.create_session(
        token,
        spotify_account_id="account-123",
        spotify_display_name="Runner",
    )

    stored = store.get_session(session_id)

    assert stored is not None
    assert stored.access_token == "access-secret"
    assert stored.refresh_token == "refresh-secret"
    assert stored.spotify_account_id == "account-123"
    assert stored.scope == "playlist-modify-private"

    raw_database = database.read_bytes()
    assert b"access-secret" not in raw_database
    assert b"refresh-secret" not in raw_database
