"""Google OAuth 2.0 endpoints — lets users link their Google Calendar."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import get_settings
from app.store import GoogleOAuthToken, store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google", tags=["auth"])

# Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# Scopes needed to read calendar availability
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "openid",
    "email",
]


# ---------------------------------------------------------------------------
# Step 1: Generate the Google consent URL
# ---------------------------------------------------------------------------


@router.get("/authorize")
async def google_authorize(user_id: str = Query(..., description="Unique user identifier")) -> dict:
    """Return the Google OAuth consent URL the frontend should redirect to.

    The frontend passes its `user_id` so we can associate the token after
    the callback.
    """
    settings = get_settings()

    if not settings.google_oauth_client_id:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not configured (GOOGLE_OAUTH_CLIENT_ID missing)",
        )

    redirect_uri = settings.google_oauth_redirect_uri or (
        f"{settings.public_base_url}/auth/google/callback"
    )

    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",      # get a refresh_token
        "prompt": "consent",            # always show consent to get refresh_token
        "state": user_id,               # round-trip the user_id
    }

    url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    logger.info("OAuth authorize: user_id=%s", user_id)

    return {"authorize_url": url}


# ---------------------------------------------------------------------------
# Step 2: Handle Google's redirect after consent
# ---------------------------------------------------------------------------


def _success_html(user_id: str) -> str:
    """Return a simple HTML page confirming Google Calendar was linked."""
    return f"""<!DOCTYPE html>
<html>
<head><title>CallPilot — Google Calendar Linked</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         display: flex; align-items: center; justify-content: center; height: 100vh;
         margin: 0; background: #f8f9fa; color: #333; }}
  .card {{ background: #fff; padding: 2.5rem; border-radius: 12px;
           box-shadow: 0 2px 12px rgba(0,0,0,.08); text-align: center; max-width: 420px; }}
  .check {{ font-size: 3rem; margin-bottom: .5rem; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 .5rem; }}
  p  {{ color: #666; font-size: .95rem; margin: 0; }}
  code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-size: .85rem; }}
</style></head>
<body><div class="card">
  <div class="check">&#10003;</div>
  <h1>Google Calendar Connected</h1>
  <p>Your calendar has been linked successfully.<br>
     User ID: <code>{user_id}</code></p>
  <p style="margin-top:1rem;color:#999;font-size:.85rem;">You can close this tab.</p>
</div></body></html>"""


def _error_html(detail: str) -> str:
    """Return a simple HTML page showing an OAuth error."""
    return f"""<!DOCTYPE html>
<html>
<head><title>CallPilot — OAuth Error</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         display: flex; align-items: center; justify-content: center; height: 100vh;
         margin: 0; background: #f8f9fa; color: #333; }}
  .card {{ background: #fff; padding: 2.5rem; border-radius: 12px;
           box-shadow: 0 2px 12px rgba(0,0,0,.08); text-align: center; max-width: 420px; }}
  .icon {{ font-size: 3rem; margin-bottom: .5rem; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 .5rem; color: #c0392b; }}
  p  {{ color: #666; font-size: .95rem; margin: 0; }}
  code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-size: .85rem; }}
</style></head>
<body><div class="card">
  <div class="icon">&#10007;</div>
  <h1>OAuth Error</h1>
  <p><code>{detail}</code></p>
  <p style="margin-top:1rem;color:#999;font-size:.85rem;">Please try linking again.</p>
</div></body></html>"""


@router.get("/callback", response_model=None)
async def google_callback(
    code: str = Query(...),
    state: str = Query(""),
    error: str = Query(""),
) -> HTMLResponse | RedirectResponse:
    """Google redirects here after the user grants (or denies) consent.

    Exchanges the authorization code for tokens and stores them.
    If a frontend URL is configured and reachable, redirects there;
    otherwise renders a simple confirmation page.
    """
    settings = get_settings()

    # If a frontend URL is configured, redirect there (original behaviour)
    use_redirect = bool(settings.frontend_url)

    if error:
        logger.warning("OAuth callback error: %s", error)
        if use_redirect:
            return RedirectResponse(
                url=f"{settings.frontend_url}/book?oauth=error&detail={error}"
            )
        return HTMLResponse(_error_html(error))

    user_id = state
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing state (user_id)")

    redirect_uri = settings.google_oauth_redirect_uri or (
        f"{settings.public_base_url}/auth/google/callback"
    )

    # Exchange authorization code for tokens
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )

    if resp.status_code != 200:
        logger.error("Token exchange failed: %s %s", resp.status_code, resp.text)
        if use_redirect:
            return RedirectResponse(
                url=f"{settings.frontend_url}/book?oauth=error&detail=token_exchange_failed"
            )
        return HTMLResponse(_error_html("token_exchange_failed"), status_code=502)

    data = resp.json()
    access_token = data.get("access_token", "")
    refresh_token = data.get("refresh_token", "")

    if not access_token:
        if use_redirect:
            return RedirectResponse(
                url=f"{settings.frontend_url}/book?oauth=error&detail=no_access_token"
            )
        return HTMLResponse(_error_html("no_access_token"), status_code=502)

    # Store the token
    token = GoogleOAuthToken(
        user_id=user_id,
        access_token=access_token,
        refresh_token=refresh_token,
    )
    await store.save_oauth_token(token)

    logger.info("OAuth tokens saved for user_id=%s", user_id)

    if use_redirect:
        return RedirectResponse(
            url=f"{settings.frontend_url}/book?oauth=success"
        )
    return HTMLResponse(_success_html(user_id))


# ---------------------------------------------------------------------------
# Step 3: Check link status
# ---------------------------------------------------------------------------


@router.get("/status")
async def google_status(user_id: str = Query(...)) -> dict:
    """Check whether a user has linked their Google account."""
    token = await store.get_oauth_token(user_id)
    if token is None:
        return {"linked": False}

    return {
        "linked": True,
        "linked_at": token.linked_at.isoformat(),
        "scopes": token.scopes,
    }


# ---------------------------------------------------------------------------
# Step 4: Verify the connection actually works
# ---------------------------------------------------------------------------


GCAL_FREEBUSY_URL = "https://www.googleapis.com/calendar/v3/freeBusy"


@router.get("/verify")
async def google_verify(user_id: str = Query(...)) -> dict:
    """Verify that a user's linked Google Calendar is actually accessible.

    Makes a real FreeBusy API call to confirm the token works.
    Returns connection health, the user's email, and upcoming busy block
    count so the frontend can show meaningful confirmation.
    """
    token = await store.get_oauth_token(user_id)
    if token is None:
        return {
            "connected": False,
            "reason": "no_token",
            "message": "No Google account linked. Please connect first.",
        }

    settings = get_settings()

    # --- 1. Try a FreeBusy query (next 24 hours) --------------------------
    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(hours=24)).isoformat()

    headers = {"Authorization": f"Bearer {token.access_token}"}
    body = {
        "timeMin": time_min,
        "timeMax": time_max,
        "items": [{"id": "primary"}],
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(GCAL_FREEBUSY_URL, json=body, headers=headers)

    # --- 2. Handle expired token — refresh once and retry -----------------
    if resp.status_code == 401 and token.refresh_token:
        refresh_resp = await _refresh_token(token, settings)
        if refresh_resp is None:
            return {
                "connected": False,
                "reason": "refresh_failed",
                "message": "Google token expired and could not be refreshed. Please re-link your account.",
            }
        # Retry with the new access token
        headers = {"Authorization": f"Bearer {token.access_token}"}
        async with httpx.AsyncClient() as client:
            resp = await client.post(GCAL_FREEBUSY_URL, json=body, headers=headers)

    # --- 3. Interpret the response ----------------------------------------
    if resp.status_code == 401:
        return {
            "connected": False,
            "reason": "unauthorized",
            "message": "Google rejected the token. Please re-link your account.",
        }

    if resp.status_code == 403:
        return {
            "connected": False,
            "reason": "forbidden",
            "message": "Calendar access was denied. Please re-link and grant calendar permissions.",
        }

    if resp.status_code != 200:
        return {
            "connected": False,
            "reason": "api_error",
            "message": f"Google Calendar API returned status {resp.status_code}.",
        }

    # --- 4. Parse the successful response ---------------------------------
    data = resp.json()
    # Google may return the actual email as the key instead of "primary",
    # so fall back to the first calendar entry in the response.
    calendars = data.get("calendars", {})
    cal_data = calendars.get("primary", {})
    if not cal_data.get("busy") and not cal_data.get("errors") and calendars:
        cal_data = next(iter(calendars.values()), {})
    busy_blocks = cal_data.get("busy", [])
    errors = cal_data.get("errors", [])

    if errors:
        return {
            "connected": False,
            "reason": "calendar_error",
            "message": f"Google Calendar reported errors: {errors}",
        }

    return {
        "connected": True,
        "message": "Google Calendar is connected and working.",
        "linked_at": token.linked_at.isoformat(),
        "upcoming_busy_blocks_24h": len(busy_blocks),
    }


async def _refresh_token(
    token: GoogleOAuthToken, settings
) -> str | None:
    """Refresh the access token in-place. Returns new token or None on failure."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_oauth_client_id,
                    "client_secret": settings.google_oauth_client_secret,
                    "refresh_token": token.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        if resp.status_code != 200:
            logger.error("Token refresh failed: %s", resp.text)
            return None

        data = resp.json()
        token.access_token = data["access_token"]
        if "refresh_token" in data:
            token.refresh_token = data["refresh_token"]
        await store.save_oauth_token(token)
        return token.access_token
    except Exception:
        logger.exception("Token refresh request failed")
        return None


# ---------------------------------------------------------------------------
# Step 5: Unlink
# ---------------------------------------------------------------------------


@router.delete("/unlink")
async def google_unlink(user_id: str = Query(...)) -> dict:
    """Revoke and remove a user's Google Calendar link."""
    token = await store.get_oauth_token(user_id)
    if token is None:
        raise HTTPException(status_code=404, detail="No linked account found")

    # Best-effort: revoke the token at Google
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": token.access_token},
            )
    except Exception:
        logger.warning("Token revocation request failed (continuing anyway)")

    await store.delete_oauth_token(user_id)
    logger.info("Google account unlinked for user_id=%s", user_id)

    return {"unlinked": True}
