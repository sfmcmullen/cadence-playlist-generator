"""
routes.py

FastAPI routes for Spotify login/logout and session management/inspection.
This acts as the main entry point for the backend-owned authentication/session layer.
"""

# ==================================================
# Imports and Configuration
# ==================================================

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from ..spotify.auth import SpotifyAuthorizationError, authorization_url, exchange_code
from ..spotify.client import SpotifyAPIError, SpotifyClient
from .config import get_auth_settings
from .dependencies import AuthenticatedSpotify, get_authenticated_spotify, get_store

router = APIRouter(prefix="/auth", tags=["auth"])


# ==================================================
# Routes
# ==================================================


@router.get("/spotify")
async def spotify_login() -> RedirectResponse:
    """Redirect the user to the Spotify authorization URL to initiate the OAuth flow."""

    settings = get_auth_settings()
    store = get_store()
    state = store.create_oauth_state()

    url = authorization_url(
        settings.spotify_client_id,
        settings.spotify_redirect_uri,
        state,
        public_playlists=False,
    )

    response = RedirectResponse(url, status_code=307)
    _set_cookie(
        response,
        key=settings.oauth_state_cookie_name,
        value=state,
        max_age=settings.oauth_state_ttl_seconds,
        settings=settings,
    )
    return response


@router.get("/spotify/callback")
async def spotify_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Handle the callback from Spotify after the user authorizes the app."""

    settings = get_auth_settings()
    store = get_store()

    # If user denied access to the app
    if error:
        response = RedirectResponse(
            f"{settings.frontend_url}/?spotify_auth=error&reason=access_denied",
            status_code=303,
        )
        response.delete_cookie(settings.oauth_state_cookie_name, path="/")
        return response

    expected_state = request.cookies.get(settings.oauth_state_cookie_name)
    if not code or not state or not expected_state or state != expected_state:
        raise HTTPException(status_code=400, detail="Invalid Spotify OAuth state")

    if not store.consume_oauth_state(state):
        raise HTTPException(status_code=400, detail="Spotify OAuth state expired")

    # Exchange the authorization code for an access token and get the user's Spotify profile
    try:
        token = await exchange_code(
            code,
            settings.spotify_client_id,
            settings.spotify_client_secret,
            settings.spotify_redirect_uri,
        )
        spotify = SpotifyClient(token.access_token)
        profile = await spotify.get_current_user()
    except (SpotifyAuthorizationError, SpotifyAPIError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Store the session in the database and set a cookie for the frontend to use
    account_id = profile.get("account_id") or profile.get("id")
    if not account_id:
        raise HTTPException(
            status_code=502, detail="Spotify profile did not include an account ID"
        )

    session_id = store.create_session(
        token,
        spotify_account_id=account_id,
        spotify_display_name=profile.get("display_name"),
    )

    response = RedirectResponse(settings.frontend_url, status_code=303)
    _set_cookie(
        response,
        key=settings.cookie_name,
        value=session_id,
        max_age=settings.session_ttl_seconds,
        settings=settings,
    )
    # Delete the OAuth state cookie since it's no longer needed after the callback
    response.delete_cookie(settings.oauth_state_cookie_name, path="/")
    return response


@router.get("/me")
async def auth_me(
    authenticated: AuthenticatedSpotify = Depends(get_authenticated_spotify),
) -> dict[str, str | bool | None]:
    """Return safe session information without exposing Spotify tokens."""

    return {
        "authenticated": True,
        "spotify_account_id": authenticated.spotify_account_id,
        "spotify_display_name": authenticated.spotify_display_name,
    }


@router.post("/logout", status_code=204)
async def logout(request: Request) -> Response:
    """Log the user out by deleting their session from the store and clearing the session cookie."""

    settings = get_auth_settings()
    store = get_store()
    session_id = request.cookies.get(settings.cookie_name)
    if session_id:
        store.delete_session(session_id)

    response = Response(status_code=204)
    response.delete_cookie(settings.cookie_name, path="/")
    return response


def _set_cookie(
    response: Response,
    *,
    key: str,
    value: str,
    max_age: int,
    settings,
) -> None:
    """Set a cookie on the response with appropriate security settings."""

    response.set_cookie(
        key=key,
        value=value,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
