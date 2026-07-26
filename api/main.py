from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.models.forecast import forecast_linear_trend
from src.models.segmentation import segment_customers_as_records
from src.pipeline import build_dataset
from src.stages.analyze import run_analysis

from api.cache import cache
from api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache.df = build_dataset()
    cache.analysis = run_analysis(cache.df)

    try:
        cache.forecast = forecast_linear_trend(cache.analysis["revenue_by_month"])
    except Exception:
        cache.forecast = None

    try:
        cache.segments = segment_customers_as_records(cache.df)
    except Exception:
        cache.segments = None

    yield


app = FastAPI(title="Ecommerce Sales Intelligence API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(router)
