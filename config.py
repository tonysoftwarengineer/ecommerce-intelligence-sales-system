import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

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
CORS_ORIGIN_REGEX = os.environ.get(
    "CORS_ORIGIN_REGEX", r"http://(localhost|127\.0\.0\.1):\d+"
)

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
