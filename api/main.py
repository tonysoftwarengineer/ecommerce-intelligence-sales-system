import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.cache import cache
from api.routes import router
from config import CORS_ORIGIN_REGEX, CORS_ORIGINS
from src.logging_config import setup_logging
from src.models.forecast import forecast_linear_trend
from src.models.segmentation import segment_customers_as_records
from src.pipeline import build_dataset
from src.stages.analyze import run_analysis

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Build the dataset and derived analytics once, before serving traffic.

    Forecasting and segmentation are optional: if either fails the rest of the
    API must still work, so each is isolated. The broad `except Exception` is
    deliberate -- an optional subsystem should never crash startup -- but it
    logs the full traceback, because a swallowed exception with no diagnostics
    is how a 503 becomes unfixable.
    """
    started = time.perf_counter()
    logger.info("Startup: building dataset (first run downloads ~43MB from Kaggle)")

    cache.df = build_dataset()
    logger.info(
        "Dataset ready: %s rows in %.1fs", f"{len(cache.df):,}", time.perf_counter() - started
    )

    cache.analysis = run_analysis(cache.df)
    logger.info("Analysis ready: total revenue R$%s", f"{cache.analysis['total_revenue']:,.2f}")

    try:
        cache.forecast = forecast_linear_trend(cache.analysis["revenue_by_month"])
        logger.info("Forecast ready: %d months", len(cache.forecast))
    except Exception:
        cache.forecast = None
        logger.exception("Forecast unavailable -- /api/forecast will return 503")

    try:
        cache.segments = segment_customers_as_records(cache.df)
        logger.info("Segments ready: %s customers", f"{len(cache.segments):,}")
    except Exception:
        cache.segments = None
        logger.exception("Segments unavailable -- /api/segments will return 503")

    logger.info("Startup complete in %.1fs", time.perf_counter() - started)
    yield


app = FastAPI(title="Ecommerce Sales Intelligence API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Explicit origins win when configured (production); otherwise fall back to
    # the localhost regex so any Vite dev port works.
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=None if CORS_ORIGINS else CORS_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(router)
