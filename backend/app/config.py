"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All configuration is read from env vars (or a .env file)."""

    # --- Core ---
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_caller_id: str = ""
    public_base_url: str = "http://localhost:8000"
    elevenlabs_api_key: str = ""
    elevenlabs_agent_id: str = ""
    allow_all_cors: bool = True
    simulated_calls: bool = True

    # --- Google Calendar (service-account, legacy) ---
    use_real_calendar: bool = False
    google_credentials_json: str = ""
    google_calendar_id: str = "primary"

    # --- Google OAuth 2.0 (user-linked calendars) ---
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = ""  # e.g. http://localhost:8000/auth/google/callback
    frontend_url: str = "http://localhost:3000"  # where to redirect after OAuth

    # --- Google Places ---
    use_google_places: bool = False
    google_places_api_key: str = ""

    # --- Google Distance ---
    use_google_distance: bool = False
    google_maps_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()
