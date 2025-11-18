import time
import string
import secrets
import urllib.parse
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

import requests
from fastapi import APIRouter, Form, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, TemplateResponse
from fastapi.templating import Jinja2Templates

from mcpbox.shared.config import Config
from mcpbox.shared.models import (
    AuthDevicePollRequest,
    AuthDeviceStartRequest,
    AuthLoginRequest,
    AuthProviderRequest,
    AuthRefreshRequest,
    AuthRegisterRequest,
    AuthResponse,
    AuthUpdateRequest,
    AuthUserProfile,
)

router = APIRouter()
_cfg = Config()

FIREBASE_API_KEY = _cfg.FIREBASE_API_KEY
IDENTITY_BASE_URL = "https://identitytoolkit.googleapis.com/v1"
SECURE_TOKEN_URL = "https://securetoken.googleapis.com/v1/token"

DEVICE_SESSION_TTL = 600  # seconds
DEVICE_POLL_INTERVAL = 5  # seconds

_session_lock = Lock()
_device_sessions: Dict[str, Dict[str, Any]] = {}
_state_index: Dict[str, str] = {}
_user_index: Dict[str, str] = {}

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))


def _code_create() -> str:
    """Generate a random 8-character device code in format XXXX-XXXX"""
    alphabet = string.ascii_uppercase + string.digits
    raw = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def _normalize_code(code: str) -> str:
    """Normalize device code by removing separators and converting to uppercase"""
    return code.replace("-", "").replace(" ", "").upper()


def _session_cleanup() -> None:
    """Remove expired device OAuth sessions from memory"""
    now = time.time()
    expired_codes: list[str] = []
    with _session_lock:
        for device_code, session in _device_sessions.items():
            status = session.get("status", "pending")
            expires_at = session.get("expires_at", 0)
            completed_at = session.get("completed_at", expires_at)
            if expires_at <= now or (
                status in {"complete", "error", "expired"} and now - completed_at > 120
            ):
                expired_codes.append(device_code)
    for code in expired_codes:
        _remove_session(code)


def _store_session(session: Dict[str, Any]) -> None:
    """Store device OAuth session in memory with indexes for lookup"""
    with _session_lock:
        _device_sessions[session["device_code"]] = session
        _user_index[session["normalized_user_code"]] = session["device_code"]
        _state_index[session["state"]] = session["device_code"]


def _remove_session(device_code: str) -> None:
    """Remove device OAuth session and clean up all associated indexes"""
    with _session_lock:
        session = _device_sessions.pop(device_code, None)
        if not session:
            return
        normalized = session.get("normalized_user_code")
        state = session.get("state")
        if normalized:
            _user_index.pop(normalized, None)
        if state:
            _state_index.pop(state, None)


def _session_copy(device_code: str) -> Optional[Dict[str, Any]]:
    """Get a thread-safe copy of device session data"""
    with _session_lock:
        session = _device_sessions.get(device_code)
        if session:
            return dict(session)
    return None


def _session_mark(device_code: str, status: str, *, message: Optional[str] = None) -> None:
    """Mark device session with new status and optional error message"""
    with _session_lock:
        session = _device_sessions.get(device_code)
        if not session:
            return
        session["status"] = status
        session["completed_at"] = time.time()
        if message:
            session["error"] = message
        state = session.get("state")
        if state:
            _state_index.pop(state, None)


def _session_tokens(device_code: str, tokens: Dict[str, Any]) -> None:
    """Store authentication tokens in device session and mark as complete"""
    with _session_lock:
        session = _device_sessions.get(device_code)
        if not session:
            return
        session["status"] = "complete"
        session["tokens"] = tokens
        session["completed_at"] = time.time()
        state = session.get("state")
        if state:
            _state_index.pop(state, None)


def _state_match(state: str) -> Optional[str]:
    """Find device code associated with OAuth state parameter"""
    with _session_lock:
        return _state_index.get(state)


def _device_page(
    request: Request, message: str, *, code: str = "", error: bool = False, show_form: bool = True
) -> TemplateResponse:
    """Render device OAuth verification page template"""
    return _templates.TemplateResponse(
        "auth.html",
        {
            "request": request,
            "message": message,
            "code": code,
            "error": error,
            "show_form": show_form,
        },
    )


def _provider_check(provider: str) -> None:
    """Verify that OAuth provider credentials are configured"""
    if provider == "google" and (not _cfg.GOOGLE_CLIENT_ID or not _cfg.GOOGLE_CLIENT_SECRET):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth is not configured on the server.",
        )
    if provider == "github" and (not _cfg.GITHUB_CLIENT_ID or not _cfg.GITHUB_CLIENT_SECRET):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub OAuth is not configured on the server.",
        )


def _identity_url(endpoint: str) -> str:
    """Build Firebase Identity Toolkit API URL"""
    return f"{IDENTITY_BASE_URL}/{endpoint}?key={FIREBASE_API_KEY}"


def _response_parse(response: requests.Response) -> Dict[str, Any]:
    """Parse Firebase API response and raise HTTPException on error"""
    if response.status_code == 200:
        return response.json()
    try:
        payload = response.json()
    except Exception:
        payload = {"error": {"message": response.text}}

    message = payload.get("error", {}).get("message", "firebase_error")
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _error_text(response: requests.Response) -> str:
    """Extract error message from HTTP response"""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return (
                payload.get("error")
                or payload.get("error_description")
                or payload.get("message")
                or response.text
            )
        return response.text
    except Exception:
        return response.text


def _token_extract(authorization: str = Header(default="")) -> str:
    """Extract Bearer token from Authorization header"""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
        )

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
        )
    return token


def _firebase_exchange(post_body: str) -> Dict[str, Any]:
    """Exchange OAuth provider token for Firebase ID token"""
    payload = {"postBody": post_body, "requestUri": "http://localhost", "returnSecureToken": True}
    response = requests.post(
        f"{IDENTITY_BASE_URL}/accounts:signInWithIdp?key={FIREBASE_API_KEY}",
        json=payload,
        timeout=30,
    )
    return _response_parse(response)


def _auth_parse(payload: Dict[str, Any]) -> AuthResponse:
    """Parse Firebase authentication response into AuthResponse model"""
    expires_in = payload.get("expiresIn") or payload.get("expires_in") or "0"
    return AuthResponse(
        id_token=payload.get("idToken") or payload.get("id_token"),
        refresh_token=payload.get("refreshToken") or payload.get("refresh_token"),
        expires_in=int(expires_in),
        email=payload.get("email"),
        local_id=payload.get("localId") or payload.get("user_id"),
    )


def _profile_parse(payload: Dict[str, Any]) -> AuthUserProfile:
    """Parse Firebase user profile response into AuthUserProfile model"""
    return AuthUserProfile(
        email=payload.get("email"),
        local_id=payload.get("localId"),
        display_name=payload.get("displayName"),
        email_verified=payload.get("emailVerified", False),
        disabled=payload.get("disabled", False),
    )


@router.post("/device/start")
async def device_start(request: Request, payload: AuthDeviceStartRequest) -> JSONResponse:
    """Start OAuth device code flow for Google or GitHub authentication"""
    _session_cleanup()
    provider = payload.provider.lower()
    if provider not in {"google", "github"}:
        raise HTTPException(status_code=400, detail="Unsupported provider.")

    _provider_check(provider)

    now = time.time()
    device_code = secrets.token_urlsafe(40)
    user_code = _code_create()
    normalized = _normalize_code(user_code)
    state = secrets.token_urlsafe(32)

    verification_uri = str(request.url_for("device_form"))
    verification_uri_complete = (
        f"{verification_uri}?code={urllib.parse.quote(user_code)}"
        if verification_uri
        else verification_uri
    )

    session = {
        "device_code": device_code,
        "user_code": user_code,
        "normalized_user_code": normalized,
        "provider": provider,
        "state": state,
        "status": "pending",
        "created_at": now,
        "expires_at": now + DEVICE_SESSION_TTL,
    }
    _store_session(session)

    return JSONResponse(
        content={
            "device_code": device_code,
            "user_code": user_code,
            "verification_uri": verification_uri,
            "verification_uri_complete": verification_uri_complete,
            "interval": DEVICE_POLL_INTERVAL,
            "expires_in": DEVICE_SESSION_TTL,
        }
    )


@router.post("/device/poll")
async def device_poll(payload: AuthDevicePollRequest) -> JSONResponse:
    """Poll device OAuth session status until authorization completes"""
    _session_cleanup()
    session_data = _session_copy(payload.device_code)
    if not session_data:
        raise HTTPException(status_code=404, detail="Unknown device code.")

    now = time.time()
    if session_data.get("expires_at", 0) <= now and session_data.get("status") == "pending":
        _session_mark(payload.device_code, "expired")
        _remove_session(payload.device_code)
        raise HTTPException(status_code=410, detail="Device authorization expired.")

    status_value = session_data.get("status", "pending")
    if status_value in {"pending", "authorizing"}:
        return JSONResponse(content={"status": "pending"}, status_code=202)

    if status_value == "complete":
        tokens = session_data.get("tokens") or {}
        _remove_session(payload.device_code)
        return JSONResponse(content=tokens)

    if status_value == "error":
        message = session_data.get("error") or "Authorization failed."
        _remove_session(payload.device_code)
        raise HTTPException(status_code=400, detail=message)

    if status_value == "expired":
        _remove_session(payload.device_code)
        raise HTTPException(status_code=410, detail="Device authorization expired.")

    _remove_session(payload.device_code)
    raise HTTPException(status_code=400, detail="Invalid device session state.")


@router.get("/device", response_class=HTMLResponse, name="device_form")
async def device_form(request: Request, code: Optional[str] = None) -> HTMLResponse:
    """Display device code verification page for OAuth authorization"""
    message = request.query_params.get("message") or "Enter the device code shown in your CLI."
    error_flag = request.query_params.get("error", "").lower() == "true"
    prefill = code or request.query_params.get("code") or ""
    return _device_page(request, message, code=prefill, error=error_flag, show_form=True)


@router.post("/device", response_class=HTMLResponse, name="device_submit")
async def device_submit(request: Request, code: str = Form(...)) -> HTMLResponse:
    """Handle device code submission and redirect to OAuth provider authorization"""
    normalized = _normalize_code(code)
    now = time.time()

    with _session_lock:
        device_code = _user_index.get(normalized)
        session = _device_sessions.get(device_code) if device_code else None
        if session:
            if session["expires_at"] <= now:
                session["status"] = "expired"
            status_value = session["status"]
            session["last_touched"] = now
            if status_value == "pending":
                session["status"] = "authorizing"
            provider = session["provider"]
            state = session["state"]
        else:
            status_value = None
            provider = None
            state = None

    if not session or not device_code:
        return _device_page(
            request,
            "Invalid or expired device code. Please try again.",
            code=code,
            error=True,
            show_form=True,
        )

    if status_value == "expired":
        _remove_session(device_code)
        return _device_page(
            request,
            "Device code has expired. Restart the login from the CLI.",
            code=code,
            error=True,
            show_form=True,
        )

    if status_value == "complete":
        return _device_page(
            request,
            "This code has already been used. Return to the CLI.",
            error=True,
            show_form=True,
        )

    if provider == "google":
        if not _cfg.GOOGLE_CLIENT_ID or not _cfg.GOOGLE_CLIENT_SECRET:
            _session_mark(device_code, "error", message="Google OAuth not configured.")
            return _device_page(
                request,
                "Google login is not available. Contact support.",
                error=True,
                show_form=True,
            )
        callback_url = request.url_for("callback_google")
        params = {
            "client_id": _cfg.GOOGLE_CLIENT_ID,
            "redirect_uri": callback_url,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        authorize_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
            params
        )
        return RedirectResponse(authorize_url, status_code=302)

    if provider == "github":
        if not _cfg.GITHUB_CLIENT_ID or not _cfg.GITHUB_CLIENT_SECRET:
            _session_mark(device_code, "error", message="GitHub OAuth not configured.")
            return _device_page(
                request,
                "GitHub login is not available. Contact support.",
                error=True,
                show_form=True,
            )
        callback_url = request.url_for("callback_github")
        params = {
            "client_id": _cfg.GITHUB_CLIENT_ID,
            "redirect_uri": callback_url,
            "scope": "read:user user:email",
            "state": state,
            "allow_signup": "false",
        }
        authorize_url = "https://github.com/login/oauth/authorize?" + urllib.parse.urlencode(params)
        return RedirectResponse(authorize_url, status_code=302)

    _session_mark(device_code, "error", message="Unsupported provider.")
    return _device_page(request, "Unsupported provider.", error=True, show_form=True)


@router.get("/device/callback/google", response_class=HTMLResponse, name="callback_google")
async def callback_google(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
) -> HTMLResponse:
    """Handle Google OAuth callback after user authorization"""
    if not state:
        return _device_page(request, "Missing state parameter.", error=True, show_form=False)

    device_code = _state_match(state)
    session = _session_copy(device_code) if device_code else None
    if not device_code or not session:
        return _device_page(
            request,
            "Session not found or expired. Return to the CLI and try again.",
            error=True,
            show_form=False,
        )

    if session.get("expires_at", 0) <= time.time():
        _session_mark(device_code, "expired")
        _remove_session(device_code)
        return _device_page(
            request,
            "Session has expired. Please restart the login from the CLI.",
            error=True,
            show_form=False,
        )

    if error:
        message = urllib.parse.unquote_plus(error.replace("+", " "))
        _session_mark(device_code, "error", message=message)
        return _device_page(
            request,
            f"Authorization failed: {message}",
            error=True,
            show_form=False,
        )

    if not code:
        _session_mark(device_code, "error", message="Missing authorization code.")
        return _device_page(
            request,
            "Missing authorization code.",
            error=True,
            show_form=False,
        )

    token_payload = {
        "code": code,
        "client_id": _cfg.GOOGLE_CLIENT_ID,
        "client_secret": _cfg.GOOGLE_CLIENT_SECRET,
        "redirect_uri": request.url_for("callback_google"),
        "grant_type": "authorization_code",
    }
    try:
        token_response = requests.post(
            "https://oauth2.googleapis.com/token", data=token_payload, timeout=30
        )
    except requests.RequestException as exc:
        _session_mark(device_code, "error", message=str(exc))
        return _device_page(
            request,
            "Failed to contact Google. Please try again.",
            error=True,
            show_form=False,
        )

    if token_response.status_code != 200:
        _session_mark(device_code, "error", message=_error_text(token_response))
        return _device_page(
            request,
            "Google authorization failed. Please try again.",
            error=True,
            show_form=False,
        )

    tokens = token_response.json()
    id_token = tokens.get("id_token")
    if not id_token:
        _session_mark(device_code, "error", message="Missing Google ID token.")
        return _device_page(
            request,
            "Google response did not include an ID token.",
            error=True,
            show_form=False,
        )

    firebase_data = _firebase_exchange(
        f"id_token={urllib.parse.quote(id_token, safe='')}&providerId=google.com"
    )
    auth_response = _auth_parse(firebase_data)
    auth_dict = auth_response.model_dump()
    auth_dict["provider"] = "google"
    _session_tokens(device_code, auth_dict)

    return _device_page(
        request,
        "Authentication complete. You may return to the CLI to finish logging in.",
        show_form=False,
    )


@router.get("/device/callback/github", response_class=HTMLResponse, name="callback_github")
async def callback_github(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
) -> HTMLResponse:
    """Handle GitHub OAuth callback after user authorization"""
    if not state:
        return _device_page(request, "Missing state parameter.", error=True, show_form=False)

    device_code = _state_match(state)
    session = _session_copy(device_code) if device_code else None
    if not device_code or not session:
        return _device_page(
            request,
            "Session not found or expired. Return to the CLI and try again.",
            error=True,
            show_form=False,
        )

    if session.get("expires_at", 0) <= time.time():
        _session_mark(device_code, "expired")
        _remove_session(device_code)
        return _device_page(
            request,
            "Session has expired. Please restart the login from the CLI.",
            error=True,
            show_form=False,
        )

    if error:
        message = urllib.parse.unquote_plus(error.replace("+", " "))
        _session_mark(device_code, "error", message=message)
        return _device_page(
            request,
            f"Authorization failed: {message}",
            error=True,
            show_form=False,
        )

    if not code:
        _session_mark(device_code, "error", message="Missing authorization code.")
        return _device_page(
            request,
            "Missing authorization code.",
            error=True,
            show_form=False,
        )

    token_payload = {
        "client_id": _cfg.GITHUB_CLIENT_ID,
        "client_secret": _cfg.GITHUB_CLIENT_SECRET,
        "code": code,
        "redirect_uri": request.url_for("callback_github"),
        "state": state,
    }
    try:
        token_response = requests.post(
            "https://github.com/login/oauth/access_token",
            data=token_payload,
            headers={"Accept": "application/json"},
            timeout=30,
        )
    except requests.RequestException as exc:
        _session_mark(device_code, "error", message=str(exc))
        return _device_page(
            request,
            "Failed to contact GitHub. Please try again.",
            error=True,
            show_form=False,
        )

    if token_response.status_code != 200:
        _session_mark(device_code, "error", message=_error_text(token_response))
        return _device_page(
            request,
            "GitHub authorization failed. Please try again.",
            error=True,
            show_form=False,
        )

    tokens = token_response.json()
    access_token = tokens.get("access_token")
    if not access_token:
        _session_mark(device_code, "error", message="Missing GitHub access token.")
        return _device_page(
            request,
            "GitHub response did not include an access token.",
            error=True,
            show_form=False,
        )

    firebase_data = _firebase_exchange(
        f"access_token={urllib.parse.quote(access_token, safe='')}&providerId=github.com"
    )
    auth_response = _auth_parse(firebase_data)
    auth_dict = auth_response.model_dump()
    auth_dict["provider"] = "github"
    _session_tokens(device_code, auth_dict)

    return _device_page(
        request,
        "Authentication complete. You may return to the CLI to finish logging in.",
        show_form=False,
    )


@router.post("/register", response_model=AuthResponse)
async def register_user(request: AuthRegisterRequest) -> AuthResponse:
    """Register a new user account with email and password via Firebase"""
    payload: Dict[str, Any] = {
        "email": request.email,
        "password": request.password,
        "returnSecureToken": True,
    }
    if request.display_name:
        payload["displayName"] = request.display_name

    response = requests.post(_identity_url("accounts:signUp"), json=payload, timeout=30)
    data = _response_parse(response)
    return _auth_parse(data)


@router.post("/login", response_model=AuthResponse)
async def login_user(request: AuthLoginRequest) -> AuthResponse:
    """Authenticate user with email and password via Firebase"""
    payload = {
        "email": request.email,
        "password": request.password,
        "returnSecureToken": True,
    }
    response = requests.post(
        _identity_url("accounts:signInWithPassword"),
        json=payload,
        timeout=30,
    )
    data = _response_parse(response)
    return _auth_parse(data)


@router.post("/login/provider", response_model=AuthResponse)
async def login_provider(request: AuthProviderRequest) -> AuthResponse:
    """Authenticate user via OAuth provider (Google or GitHub) using ID/access token"""
    provider = request.provider.lower()

    if provider == "google":
        token = request.id_token or request.access_token
        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing id_token or access_token for Google login.",
            )
        field = "id_token" if request.id_token else "access_token"
        post_body = f"{field}={urllib.parse.quote(token, safe='')}&providerId=google.com"
    elif provider == "github":
        if not request.access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing access_token for GitHub login.",
            )
        post_body = f"access_token={urllib.parse.quote(request.access_token, safe='')}&providerId=github.com"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider '{request.provider}'.",
        )

    data = _firebase_exchange(post_body)
    return _auth_parse(data)


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(request: AuthRefreshRequest) -> AuthResponse:
    """Refresh Firebase ID token using refresh token"""
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": request.refresh_token,
    }
    response = requests.post(
        f"{SECURE_TOKEN_URL}?key={FIREBASE_API_KEY}",
        data=payload,
        timeout=30,
    )
    data = _response_parse(response)
    return _auth_parse(data)


@router.get("/me", response_model=AuthUserProfile)
async def get_profile(
    id_token: str = Header(default=None, alias="X-ID-Token"),
    authorization: str = Header(default=""),
) -> AuthUserProfile:
    """Get current user profile information from Firebase"""
    token = id_token or _token_extract(authorization)
    payload = {"idToken": token}

    response = requests.post(_identity_url("accounts:lookup"), json=payload, timeout=30)
    data = _response_parse(response)

    users = data.get("users", [])
    if not users:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _profile_parse(users[0])


@router.patch("/me", response_model=AuthUserProfile)
async def update_profile(
    request: AuthUpdateRequest,
    authorization: str = Header(default=""),
) -> AuthUserProfile:
    """Update current user profile (display name or password) in Firebase"""
    token = _token_extract(authorization)
    payload: Dict[str, Any] = {"idToken": token, "returnSecureToken": True}

    if request.display_name is not None:
        payload["displayName"] = request.display_name
    if request.password is not None:
        payload["password"] = request.password

    response = requests.post(_identity_url("accounts:update"), json=payload, timeout=30)
    data = _response_parse(response)
    return _profile_parse(data)


@router.delete("/me")
async def delete_profile(authorization: str = Header(default="")) -> JSONResponse:
    """Delete current user account from Firebase"""
    token = _token_extract(authorization)
    payload = {"idToken": token}

    response = requests.post(_identity_url("accounts:delete"), json=payload, timeout=30)
    _response_parse(response)

    return JSONResponse(
        content={"status": "success", "message": "Account deleted successfully."},
        status_code=status.HTTP_200_OK,
    )
