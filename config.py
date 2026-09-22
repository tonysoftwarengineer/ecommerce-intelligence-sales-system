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
DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_ROOT / "data"))

KAGGLE_DATASET = os.environ.get("KAGGLE_DATASET", "olistbr/brazilian-ecommerce")

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

# RAG source documents are intentionally ephemeral in the portfolio release.
RAG_DOCUMENT_TTL_MINUTES = int(os.environ.get("RAG_DOCUMENT_TTL_MINUTES", "120"))
RAG_DOCUMENT_MAX_BYTES = int(os.environ.get("RAG_DOCUMENT_MAX_BYTES", str(2 * 1024 * 1024)))
RAG_RETRIEVAL_BACKEND = os.environ.get("RAG_RETRIEVAL_BACKEND", "chroma").strip().lower()
RAG_EMBEDDING_MODEL = os.environ.get("RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
RAG_CHUNK_MAX_TOKENS = int(os.environ.get("RAG_CHUNK_MAX_TOKENS", "224"))
RAG_CHUNK_OVERLAP_TOKENS = int(os.environ.get("RAG_CHUNK_OVERLAP_TOKENS", "32"))
RAG_RELEVANCE_THRESHOLD = float(os.environ.get("RAG_RELEVANCE_THRESHOLD", "0.40"))
RAG_LEXICAL_RERANKING = os.environ.get("RAG_LEXICAL_RERANKING", "false").lower() in {
    "1",
    "true",
    "yes",
}
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
RAG_ANSWER_MODEL = os.environ.get("RAG_ANSWER_MODEL", "gemini-3.8-flash").strip()
RAG_ANSWER_TIMEOUT_SECONDS = float(os.environ.get("RAG_ANSWER_TIMEOUT_SECONDS", "5.0"))
RAG_ANSWER_PROVIDER = os.environ.get("RAG_ANSWER_PROVIDER", "gemini").strip().lower()

TABLE_FILES = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}
