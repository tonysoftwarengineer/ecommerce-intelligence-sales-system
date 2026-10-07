import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent


def load_project_dotenv(dotenv_path: Path = PROJECT_ROOT / ".env") -> None:
    """Load only this project's optional local development configuration.

    Deployed environment variables always win, and a missing file is a normal
    configuration state.  This deliberately avoids searching parent folders so
    another project cannot accidentally supply this application's credentials.
    """

    load_dotenv(dotenv_path=dotenv_path, override=False)


load_project_dotenv()

# Anything that differs between a laptop and a deployed server is read from the
# environment, with a working local default. Deploying should never require
# editing source.
# Comma-separated exact origins, e.g. "https://dashboard.example.com".
# Empty (the default) falls back to CORS_ORIGIN_REGEX below.
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

# Any localhost port, because Vite falls back 5173 -> 5174 -> ... when a port
# is taken, and hardcoding one would break the dev server unpredictably.
CORS_ORIGIN_REGEX = os.environ.get("CORS_ORIGIN_REGEX", r"http://(localhost|127\.0\.0\.1):\d+")

# Generic business uploads remain in process memory only and are removed after
# this fixed lifetime. Limits are configurable without editing application code.
UPLOAD_TTL_MINUTES = int(os.environ.get("UPLOAD_TTL_MINUTES", "30"))
UPLOAD_MAX_BYTES = int(os.environ.get("UPLOAD_MAX_BYTES", str(10 * 1024 * 1024)))
# Caps CSV upload attempts per anonymous guest. Parsing costs local CPU and
# memory, so a client cannot keep the server busy with repeated uploads.
UPLOAD_RATE_LIMIT_PER_MINUTE = int(os.environ.get("UPLOAD_RATE_LIMIT_PER_MINUTE", "20"))

# Derived analysis sessions contain no original upload bytes. They live longer
# than uploads so a user can refresh the dashboard and download processed data.
ANALYSIS_TTL_MINUTES = int(os.environ.get("ANALYSIS_TTL_MINUTES", "120"))

# The public portfolio demo has no account screen. A short-lived HttpOnly cookie
# still isolates one visitor's files from another visitor's files.
GUEST_SESSION_TTL_MINUTES = int(os.environ.get("GUEST_SESSION_TTL_MINUTES", "120"))
GUEST_SESSION_COOKIE = os.environ.get("GUEST_SESSION_COOKIE", "ei_guest_session")
GUEST_COOKIE_SECURE = os.environ.get("GUEST_COOKIE_SECURE", "false").lower() in {
    "1",
    "true",
    "yes",
}

DEVELOPMENT_OBSERVABILITY_ENABLED = os.environ.get(
    "DEVELOPMENT_OBSERVABILITY_ENABLED", "false"
).lower() in {"1", "true", "yes"}
# ADR-004 requires the observability endpoints to have administrator
# authentication or not exist at all. A bare on/off toggle cannot satisfy
# that on its own, since a copied .env can carry the toggle into a real
# deployment by accident. Requiring a token turns "must have auth" into a
# fact the app enforces, not a promise a human has to remember.
DEVELOPMENT_OBSERVABILITY_TOKEN = os.environ.get("DEVELOPMENT_OBSERVABILITY_TOKEN", "").strip()


def validate_observability_settings(enabled: bool, token: str) -> None:
    if enabled and not token:
        raise ValueError(
            "DEVELOPMENT_OBSERVABILITY_ENABLED requires DEVELOPMENT_OBSERVABILITY_TOKEN "
            "(a shared secret the caller must present): per ADR-004 the endpoints must have "
            "administrator authentication or not exist."
        )


if UPLOAD_RATE_LIMIT_PER_MINUTE < 1:
    raise ValueError("UPLOAD_RATE_LIMIT_PER_MINUTE must be positive")
validate_observability_settings(DEVELOPMENT_OBSERVABILITY_ENABLED, DEVELOPMENT_OBSERVABILITY_TOKEN)
