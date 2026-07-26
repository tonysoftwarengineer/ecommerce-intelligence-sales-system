from fastapi import APIRouter, HTTPException

from api.cache import cache
from api.schemas import ForecastResponse, HealthResponse, ReportResponse, SegmentsResponse
from api.serializers import report_to_response_dict, segment_counts_to_records

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        report_ready=cache.analysis is not None,
        forecast_ready=cache.forecast is not None,
        segments_ready=cache.segments is not None,
    )


@router.get("/report", response_model=ReportResponse)
def report():
    if cache.analysis is None:
        raise HTTPException(status_code=503, detail="Report not ready")
    return report_to_response_dict(cache.analysis)


@router.get("/forecast", response_model=ForecastResponse)
def forecast():
    if cache.forecast is None:
        raise HTTPException(status_code=503, detail="Forecast not available")
    return {"horizon_months": len(cache.forecast), "forecast": cache.forecast}


@router.get("/segments", response_model=SegmentsResponse)
def segments():
    if cache.segments is None:
        raise HTTPException(status_code=503, detail="Segments not available")
    return {
        "segments": cache.segments,
        "segment_counts": segment_counts_to_records(cache.segments),
    }
