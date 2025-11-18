import sys
import json
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

import click
import requests

from mcpbox.shared.config import Config, load_env


AUTH_FILE = Path.home() / ".mcpbox" / "auth.json"
IDENTITY_BASE_URL = "https://identitytoolkit.googleapis.com/v1"
SECURE_TOKEN_URL = "https://securetoken.googleapis.com/v1/token"


def _env_load() -> None:
    """Load environment variables from .env file in current directory"""
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        load_env(env_path)


def _config_load() -> Config:
    """Load environment variables and return Config instance"""
    _env_load()
    return Config()


def _read_auth() -> Optional[Dict[str, Any]]:
    """Read authentication tokens from local auth file"""
    if not AUTH_FILE.exists():
        return None
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_auth(payload: Dict[str, Any]) -> None:
    """Save authentication tokens to local auth file"""
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _identity_url(endpoint: str, api_key: str) -> str:
    """Build Firebase Identity Toolkit API URL"""
    return f"{IDENTITY_BASE_URL}/{endpoint}?key={api_key}"


def _error_text(response: requests.Response) -> str:
    """Extract error message from HTTP response"""
    try:
        data = response.json()
        return data.get("error", {}).get("message", response.text)
    except Exception:
        return response.text


def _session_active(cfg: Config) -> bool:
    """Check if current authentication session is valid"""
    tokens = _read_auth()
    if not tokens or not tokens.get("id_token"):
        return False

    try:
        response = requests.post(
            _identity_url("accounts:lookup", cfg.FIREBASE_API_KEY),
            json={"idToken": tokens.get("id_token")},
            timeout=30,
        )
        return response.status_code == 200 and bool(response.json().get("users"))
    except Exception:
        return False


def _login_email(cfg: Config, email: Optional[str], password: Optional[str]) -> None:
    """Authenticate user with email and password via Firebase"""
    url = _identity_url("accounts:signInWithPassword", cfg.FIREBASE_API_KEY)
    email_value = email or click.prompt("Email")
    password_value = password or click.prompt("Password", hide_input=True)

    payload = {"email": email_value, "password": password_value, "returnSecureToken": True}
    response = requests.post(url, json=payload, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(_error_text(response))

    data = response.json()
    _save_auth(
        {
            "email": data.get("email") or email_value,
            "id_token": data.get("idToken"),
            "refresh_token": data.get("refreshToken"),
            "expires_in": int(data.get("expiresIn", "0")),
            "local_id": data.get("localId"),
            "provider": "password",
        }
    )
    click.echo("Login successful.")


def _device_login(cfg: Config, provider: str) -> None:
    """Authenticate user via OAuth device code flow (Google/GitHub)"""
    api_url = cfg.MCPBOX_API_URL
    if not api_url:
        raise RuntimeError("MCPBOX_API_URL is required for OAuth device login.")

    base_url = api_url.rstrip("/")
    try:
        response = requests.post(
            f"{base_url}/auth/device/start",
            json={"provider": provider},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to start device login: {exc}") from exc

    if response.status_code != 200:
        raise RuntimeError(_error_text(response))

    data = response.json()
    device_code = data.get("device_code")
    user_code = data.get("user_code")
    verification_uri = data.get("verification_uri")
    direct_uri = data.get("verification_uri_complete") or verification_uri
    interval = data.get("interval", 5)
    expires_in = data.get("expires_in", 600)

    if not device_code or not user_code or not verification_uri:
        raise RuntimeError("Device login response missing required fields.")

    click.echo("\n=== Device Login ===")
    click.echo(f"Provider: {provider}")
    click.echo(f"User code: {user_code}")
    click.echo(f"Verification URL: {verification_uri}")
    if direct_uri and direct_uri != verification_uri:
        click.echo(f"Direct link: {direct_uri}")

    opened = False
    if direct_uri:
        opened = webbrowser.open(direct_uri)
    if not opened:
        opened = webbrowser.open(verification_uri)
    if opened:
        click.echo("Opened verification page in your browser.")
    else:
        click.echo("Open the URL above in your browser and enter the code.")

    click.echo("Waiting for authorization...")
    start_time = time.time()

    while True:
        if time.time() - start_time >= expires_in:
            raise RuntimeError("Device authorization timed out.")

        try:
            poll_response = requests.post(
                f"{base_url}/auth/device/poll",
                json={"device_code": device_code},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Device polling failed: {exc}") from exc

        if poll_response.status_code == 202:
            time.sleep(interval)
            continue

        if poll_response.status_code == 200:
            tokens = poll_response.json()
            tokens.setdefault("provider", provider)
            _save_auth(tokens)
            click.echo("Login successful.")
            return

        if poll_response.status_code == 410:
            raise RuntimeError("Device authorization expired. Please start again.")

        error = _error_text(poll_response)
        raise RuntimeError(f"Device login failed: {error}")


@click.group()
def auth() -> None:
    """Authenticate against the MCP Box registry"""


@auth.command()
@click.option("--email", prompt=True, help="Firebase email address")
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=False,
    help="Firebase password",
)
def register(email: str, password: str) -> None:
    """Create a new MCP Box account via Firebase"""
    try:
        cfg = _config_load()
        url = _identity_url("accounts:signUp", cfg.FIREBASE_API_KEY)
        payload = {
            "email": email,
            "password": password,
            "returnSecureToken": True,
        }
        response = requests.post(url, json=payload, timeout=30)

        if response.status_code != 200:
            error = _error_text(response)
            click.echo(f"Registration failed: {error}")
            sys.exit(1)

        data = response.json()
        _save_auth(
            {
                "email": data.get("email"),
                "id_token": data.get("idToken"),
                "refresh_token": data.get("refreshToken"),
                "expires_in": int(data.get("expiresIn", "0")),
                "local_id": data.get("localId"),
                "provider": "password",
            }
        )
        click.echo("Registration successful. You are now logged in.")
    except Exception as exc:
        click.echo(f"\nError: {exc}")
        sys.exit(1)


@auth.command()
@click.option(
    "--provider",
    type=click.Choice(["email", "google", "github"], case_sensitive=False),
    default="email",
    show_default=True,
    help="Authentication provider to use",
)
@click.option("--email", help="Firebase email address (email provider only)")
@click.option("--password", hide_input=True, help="Firebase password (email provider only)")
def login(provider: str, email: Optional[str], password: Optional[str]) -> None:
    """Authenticate and store credentials locally"""
    provider_name = (provider or "email").lower()

    try:
        cfg = _config_load()
        if _session_active(cfg):
            click.echo("Already logged in. Use 'mcpbox auth logout' to switch accounts.")
            return

        if provider_name == "email":
            _login_email(cfg, email, password)
        elif provider_name == "google":
            _device_login(cfg, "google")
        elif provider_name == "github":
            _device_login(cfg, "github")
        else:
            raise RuntimeError(f"Unsupported provider '{provider_name}'.")
    except Exception as exc:
        click.echo(f"\nError: {exc}")
        sys.exit(1)


@auth.command()
def refresh() -> None:
    """Refresh the stored authentication token"""
    tokens = _read_auth()
    if not tokens or "refresh_token" not in tokens:
        click.echo("No refresh token found. Please login first.")
        sys.exit(1)

    try:
        cfg = _config_load()
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
        }
        response = requests.post(
            f"{SECURE_TOKEN_URL}?key={cfg.FIREBASE_API_KEY}",
            data=payload,
            timeout=30,
        )

        if response.status_code != 200:
            error = _error_text(response)
            click.echo(f"Token refresh failed: {error}")
            sys.exit(1)

        data = response.json()
        tokens.update(
            {
                "id_token": data.get("id_token"),
                "refresh_token": data.get("refresh_token"),
                "expires_in": int(data.get("expires_in", "0")),
                "local_id": data.get("user_id", tokens.get("local_id")),
            }
        )
        _save_auth(tokens)
        click.echo("Token refreshed.")
    except Exception as exc:
        click.echo(f"\nError: {exc}")
        sys.exit(1)


@auth.command()
def status() -> None:
    """Display current authentication status"""
    tokens = _read_auth()
    if not tokens:
        click.echo("Not logged in.")
        return

    try:
        cfg = _config_load()
        lookup_url = _identity_url("accounts:lookup", cfg.FIREBASE_API_KEY)
        payload = {"idToken": tokens.get("id_token")}
        response = requests.post(lookup_url, json=payload, timeout=30)

        if response.status_code != 200:
            error = _error_text(response)
            click.echo(f"Stored credentials appear invalid: {error}")
            return

        data = response.json()
        users = data.get("users", [])
        if not users:
            click.echo("Logged in, but no profile information available.")
            return

        user = users[0]
        click.echo("Logged in.")
        click.echo(f"  Email: {user.get('email')}")
        if user.get("displayName"):
            click.echo(f"  Display Name: {user.get('displayName')}")
        click.echo(f"  User ID: {user.get('localId')}")
        click.echo(f"  Email Verified: {user.get('emailVerified', False)}")
        if tokens.get("provider"):
            click.echo(f"  Provider: {tokens.get('provider')}")
    except Exception as exc:
        click.echo(f"\nError retrieving status: {exc}")


@auth.command()
def logout() -> None:
    """Remove stored credentials"""
    if AUTH_FILE.exists():
        AUTH_FILE.unlink()
        click.echo("Logged out.")
    else:
        click.echo("No credentials stored.")
