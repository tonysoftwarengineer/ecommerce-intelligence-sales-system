import hmac
import re
import time
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from pandas.errors import EmptyDataError, ParserError
from starlette.concurrency import run_in_threadpool

from api.analysis_observability import AnalysisObservability
from api.analysis_store import (
    AnalysisExpiredError,
    AnalysisNotFoundError,
    AnalysisSession,
    AnalysisSessionStore,
)
from api.product_demand import (
    product_demand_analysis_to_response,
    product_demand_assumptions_from_request,
    product_demand_data_quality_unavailable_response,
)
from api.rate_limit import RateLimiter
from api.schemas import (
    AnalysisObservabilityResponse,
    CanonicalTransformRequest,
    CanonicalTransformResponse,
    CsvPreviewResponse,
    DataValidationResponse,
    DistinctValuesRequest,
    DistinctValuesResponse,
    GenericAnalysisRequest,
    GenericAnalysisResponse,
    HealthResponse,
    MappingSuggestionsRequest,
    MappingSuggestionsResponse,
    ProductDemandRequest,
    ProductDemandResponse,
    SalesDataRequest,
    SchemaMappingRequest,
    SchemaMappingValidationResponse,
)
from api.serializers import (
    dataframe_sample_records,
    dataframe_to_csv_bytes,
    privacy_safe_preview_records,
)
from api.upload_store import (
    TemporaryUploadStore,
    UploadExpiredError,
    UploadNotFoundError,
)
from config import (
    ANALYSIS_TTL_MINUTES,
    DEVELOPMENT_OBSERVABILITY_ENABLED,
    DEVELOPMENT_OBSERVABILITY_TOKEN,
    UPLOAD_MAX_BYTES,
    UPLOAD_RATE_LIMIT_PER_MINUTE,
    UPLOAD_TTL_MINUTES,
)
from src.generic_sales.contracts import RevenueMode, SalesProcessingConfig
from src.generic_sales.data_quality import assess_data_quality, data_quality_report_to_dict
from src.generic_sales.reporting import build_generic_sales_reports
from src.generic_sales.transformation import (
    QuarantineConfirmationRequired,
    TransformationBlockedError,
    TransformationInputError,
    transform_sales_data,
)
from src.generic_sales.validation import validate_sales_data
from src.mapping_suggestions import suggest_schema_mapping
from src.product_demand.service import analyze_product_demand
from src.schema_mapping import validate_schema_mapping

router = APIRouter(prefix="/api/v1")
CSV_PREVIEW_SAMPLE_ROWS = 5
DISTINCT_VALUE_LIMIT = 100
VALIDATION_ISSUE_SAMPLE_ROWS = 20
upload_store = TemporaryUploadStore(ttl=timedelta(minutes=UPLOAD_TTL_MINUTES))
analysis_store = AnalysisSessionStore(ttl=timedelta(minutes=ANALYSIS_TTL_MINUTES))
analysis_observability = AnalysisObservability()
upload_rate_limiter = RateLimiter(UPLOAD_RATE_LIMIT_PER_MINUTE)


def _preview_dataframe(
    upload_id: str,
    expires_at: datetime,
    filename: str,
    df: pd.DataFrame,
    raw_df: pd.DataFrame,
) -> dict:
    return {
        "upload_id": upload_id,
        "expires_at": expires_at,
        "filename": filename,
        "row_count": len(df),
        "column_count": len(df.columns),
        "columns": [str(column) for column in df.columns],
        "dtypes": {str(column): str(dtype) for column, dtype in df.dtypes.items()},
        "sample_rows": privacy_safe_preview_records(raw_df, CSV_PREVIEW_SAMPLE_ROWS),
    }


def _require_observability_access(request: Request) -> None:
    # 404 rather than 401/403 so an unauthenticated caller cannot tell the
    # endpoint exists, matching how cross-scope document access fails.
    token = DEVELOPMENT_OBSERVABILITY_TOKEN
    if not DEVELOPMENT_OBSERVABILITY_ENABLED or not token:
        raise HTTPException(status_code=404, detail="Not found")
    scheme, _, presented = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        presented.strip().encode(), token.encode()
    ):
        raise HTTPException(status_code=404, detail="Not found")


def _owner_scope_id(request: Request) -> str:
    owner_scope_id = getattr(request.state, "guest_session_id", None)
    if not owner_scope_id:
        raise HTTPException(status_code=500, detail="Guest session was not initialized")
    return str(owner_scope_id)


def _consume_upload_rate_limit(request: Request) -> str:
    """Rate-limit a file-accepting upload endpoint; returns the caller's owner scope."""
    owner_scope_id = _owner_scope_id(request)
    decision = upload_rate_limiter.consume(owner_scope_id)
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                "Too many upload requests. Please try again in "
                f"{decision.retry_after_seconds} seconds."
            ),
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    return owner_scope_id


def _get_temporary_upload(owner_scope_id: str, upload_id: str):
    try:
        return upload_store.get(owner_scope_id, upload_id)
    except UploadExpiredError as exc:
        raise HTTPException(
            status_code=410, detail="Your upload expired. Upload the CSV again to continue."
        ) from exc
    except UploadNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="This upload is no longer available. Upload the CSV again."
        ) from exc


def _get_analysis_session(owner_scope_id: str, analysis_id: str) -> AnalysisSession:
    try:
        return analysis_store.get(owner_scope_id, analysis_id)
    except AnalysisExpiredError as exc:
        raise HTTPException(
            status_code=410,
            detail="This sales analysis expired. Upload your CSV again to start a new one.",
        ) from exc
    except AnalysisNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="This sales analysis is not available in your current session."
        ) from exc


def _processing_config(request: SalesDataRequest) -> SalesProcessingConfig:
    try:
        return SalesProcessingConfig(
            revenue_mode=request.revenue_mode,
            negative_revenue_policy=request.negative_revenue_policy,
            date_format=request.date_format,
            currency=request.currency,
            status_mapping=request.status_mapping,
            payment_status_mapping=request.payment_status_mapping,
            assume_all_completed=request.assume_all_completed,
            discount_type=request.discount_type,
            discount_scope=request.discount_scope,
            order_discount_allocation=request.order_discount_allocation,
            revenue_mismatch_policy=request.revenue_mismatch_policy,
            mismatch_tolerance=Decimal(str(request.mismatch_tolerance)),
            refund_tax_treatment=request.refund_tax_treatment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _read_temporary_csv(contents: bytes) -> pd.DataFrame:
    # The bytes were parsed successfully at upload time. Re-reading preserves
    # identifiers such as "001". Only mapped dates and numbers are converted
    # later, when their business meaning is known.
    return pd.read_csv(BytesIO(contents), dtype=str, keep_default_na=False)


def _read_canonical_csv(contents: bytes) -> pd.DataFrame:
    """Restore canonical rows without losing identifiers such as product code 0007."""
    return pd.read_csv(BytesIO(contents), dtype=str, keep_default_na=False)


def _ensure_valid_mapping(columns, mapping, revenue_mode) -> None:
    mapping_result = validate_schema_mapping(columns, mapping, revenue_mode)
    if not mapping_result["valid"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Schema mapping is invalid",
                "errors": mapping_result["errors"],
                "warnings": mapping_result["warnings"],
            },
        )


def _analysis_response(
    session: AnalysisSession,
    currency: Optional[str] = None,
) -> dict:
    reports = session.report["currency_reports"]
    available = sorted(reports)
    selected = currency or available[0]
    if selected not in reports:
        raise HTTPException(
            status_code=404,
            detail=f"Currency '{selected}' is not available in this analysis",
        )
    metadata = {key: value for key, value in session.report.items() if key != "currency_reports"}
    return {
        "analysis_id": session.analysis_id,
        "expires_at": session.expires_at,
        **metadata,
        **reports[selected],
        "available_currencies": available,
        "downloads": {
            "canonical_csv": f"/api/v1/analyses/{session.analysis_id}/canonical.csv",
            "quarantine_csv": f"/api/v1/analyses/{session.analysis_id}/quarantine.csv",
        },
    }


def _safe_download_name(filename: str, suffix: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "sales"
    return f"{safe_stem}_{suffix}.csv"


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")


@router.get("/observability/analysis-metrics", response_model=AnalysisObservabilityResponse)
def analysis_metrics(request: Request):
    """Expose privacy-safe evaluation metrics to a caller holding the admin token."""
    _require_observability_access(request)
    return analysis_observability.snapshot()


@router.post("/uploads/preview", response_model=CsvPreviewResponse)
async def preview_upload(request: Request, file: UploadFile):
    owner_scope_id = _consume_upload_rate_limit(request)
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Choose a CSV (.csv) file and try again.")

    contents = await file.read(UPLOAD_MAX_BYTES + 1)
    if not contents:
        raise HTTPException(
            status_code=400, detail="This CSV is empty. Export your sales rows and try again."
        )
    if len(contents) > UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail="This CSV is too large. Export a smaller file and try again.",
        )

    # Parsing is CPU-bound; on the event loop it would stall every other request.
    return await run_in_threadpool(_store_csv_preview, owner_scope_id, filename, contents)


def _store_csv_preview(owner_scope_id: str, filename: str, contents: bytes) -> dict:
    try:
        df = pd.read_csv(BytesIO(contents))
    except EmptyDataError as exc:
        raise HTTPException(
            status_code=400, detail="This CSV is empty. Export your sales rows and try again."
        ) from exc
    except (ParserError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=400,
            detail="We could not read this CSV. Check its format and export it again.",
        ) from exc

    if df.empty and len(df.columns) == 0:
        raise HTTPException(
            status_code=400, detail="This CSV is empty. Export your sales rows and try again."
        )

    raw_df = pd.read_csv(BytesIO(contents), dtype=str, keep_default_na=False)
    upload = upload_store.create(
        owner_scope_id,
        filename,
        contents,
        [str(column) for column in df.columns],
    )
    return _preview_dataframe(upload.upload_id, upload.expires_at, filename, df, raw_df)


@router.post("/uploads/distinct-values", response_model=DistinctValuesResponse)
def distinct_upload_values(payload: DistinctValuesRequest, request: Request):
    upload = _get_temporary_upload(_owner_scope_id(request), payload.upload_id)
    unknown = sorted(set(payload.columns) - set(upload.columns))
    if unknown:
        raise HTTPException(
            status_code=400,
            detail="Columns not found in uploaded CSV: " + ", ".join(unknown),
        )

    df = _read_temporary_csv(upload.contents)
    result = {}
    for column in payload.columns:
        normalized = df[column].map(lambda value: str(value).strip())
        blank_count = int(normalized.eq("").sum())
        values = sorted(value for value in normalized.unique() if value)
        result[column] = {
            "values": values[:DISTINCT_VALUE_LIMIT],
            "unique_count": len(values),
            "blank_count": blank_count,
            "truncated": len(values) > DISTINCT_VALUE_LIMIT,
        }
    return {"columns": result}


@router.post("/uploads/mapping-suggestions", response_model=MappingSuggestionsResponse)
def upload_mapping_suggestions(payload: MappingSuggestionsRequest, request: Request):
    upload = _get_temporary_upload(_owner_scope_id(request), payload.upload_id)
    return suggest_schema_mapping(upload.columns, payload.revenue_mode)


@router.post(
    "/uploads/validate-mapping",
    response_model=SchemaMappingValidationResponse,
)
def validate_upload_mapping(payload: SchemaMappingRequest, request: Request):
    upload = _get_temporary_upload(_owner_scope_id(request), payload.upload_id)

    return validate_schema_mapping(upload.columns, payload.mapping, payload.revenue_mode)


@router.post("/uploads/validate-data", response_model=DataValidationResponse)
def validate_upload_data(payload: SalesDataRequest, request: Request):
    upload = _get_temporary_upload(_owner_scope_id(request), payload.upload_id)
    _ensure_valid_mapping(upload.columns, payload.mapping, payload.revenue_mode)

    validation = validate_sales_data(
        _read_temporary_csv(upload.contents),
        payload.mapping,
        _processing_config(payload),
    )
    data_quality = assess_data_quality(validation, payload.mapping, payload.date_format)
    issue_counts = Counter(issue.code for issue in validation.issues)
    return {
        "can_transform": validation.can_transform,
        "requires_confirmation": validation.requires_confirmation,
        "total_rows": validation.total_rows,
        "valid_rows": validation.valid_rows,
        "invalid_rows": validation.invalid_rows,
        "issue_counts": dict(sorted(issue_counts.items())),
        "sample_issues": list(validation.issues[:VALIDATION_ISSUE_SAMPLE_ROWS]),
        "warnings": list(validation.warnings),
        "blocking_errors": list(validation.blocking_errors),
        "data_quality": data_quality_report_to_dict(data_quality),
    }


@router.post("/uploads/transform", response_model=CanonicalTransformResponse)
def transform_upload_data(payload: CanonicalTransformRequest, request: Request):
    upload = _get_temporary_upload(_owner_scope_id(request), payload.upload_id)
    _ensure_valid_mapping(upload.columns, payload.mapping, payload.revenue_mode)
    df = _read_temporary_csv(upload.contents)
    config = _processing_config(payload)
    validation = validate_sales_data(df, payload.mapping, config)

    try:
        transformed = transform_sales_data(
            df,
            payload.mapping,
            config,
            validation,
            payload.confirm_quarantine,
        )
    except QuarantineConfirmationRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (TransformationBlockedError, TransformationInputError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "filename": upload.filename,
        "revenue_mode": payload.revenue_mode,
        "currency": payload.currency,
        "source_rows": len(df),
        "canonical_rows": len(transformed.canonical_data),
        "quarantined_rows": len(transformed.quarantine),
        "canonical_columns": list(transformed.canonical_data.columns),
        "sample_rows": dataframe_sample_records(transformed.canonical_data),
        "quarantine_sample": dataframe_sample_records(transformed.quarantine),
        "warnings": list(transformed.warnings),
    }


@router.post("/uploads/analyze", response_model=GenericAnalysisResponse)
def analyze_upload_data(payload: GenericAnalysisRequest, request: Request):
    started = time.perf_counter()
    owner_scope_id = _owner_scope_id(request)
    upload = _get_temporary_upload(owner_scope_id, payload.upload_id)
    _ensure_valid_mapping(upload.columns, payload.mapping, payload.revenue_mode)
    df = _read_temporary_csv(upload.contents)
    config = _processing_config(payload)
    validation = validate_sales_data(df, payload.mapping, config)
    data_quality = assess_data_quality(validation, payload.mapping, payload.date_format)

    try:
        transformed = transform_sales_data(
            df,
            payload.mapping,
            config,
            validation,
            payload.confirm_quarantine,
        )
    except QuarantineConfirmationRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (TransformationBlockedError, TransformationInputError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    currency_reports = build_generic_sales_reports(
        transformed.canonical_data,
        payload.latest_period_complete,
        set(payload.mapping),
        decision_support_ready=data_quality.decision_ready,
        decision_support_reason=data_quality.message,
    )
    report = {
        "filename": upload.filename,
        "revenue_mode": payload.revenue_mode.value,
        "source_rows": len(df),
        "canonical_rows": len(transformed.canonical_data),
        "quarantined_rows": len(transformed.quarantine),
        "data_quality": data_quality_report_to_dict(data_quality),
        "currency_reports": currency_reports,
        "warnings": list(transformed.warnings),
    }
    session = analysis_store.create(
        owner_scope_id=owner_scope_id,
        filename=upload.filename,
        report=report,
        canonical_csv=dataframe_to_csv_bytes(transformed.canonical_data),
        quarantine_csv=dataframe_to_csv_bytes(transformed.quarantine),
    )
    response = _analysis_response(session)
    analysis_observability.record_completed(
        time.perf_counter() - started,
        currency_reports,
    )
    return response


@router.get("/analyses/{analysis_id}", response_model=GenericAnalysisResponse)
def get_analysis(request: Request, analysis_id: str, currency: Optional[str] = None):
    return _analysis_response(
        _get_analysis_session(_owner_scope_id(request), analysis_id), currency
    )


@router.post(
    "/analyses/{analysis_id}/product-demand",
    response_model=ProductDemandResponse,
)
def analyze_analysis_product_demand(
    analysis_id: str,
    payload: ProductDemandRequest,
    request: Request,
):
    """Run the opt-in product-demand preview over one cleaned analysis session."""
    session = _get_analysis_session(_owner_scope_id(request), analysis_id)
    data_quality = session.report.get("data_quality", {})
    if not data_quality.get("decision_ready", False):
        return product_demand_data_quality_unavailable_response(
            str(
                data_quality.get(
                    "message",
                    "Source data quality is not sufficient for product-demand forecasting.",
                )
            )
        )

    try:
        assumptions = product_demand_assumptions_from_request(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = analyze_product_demand(
        _read_canonical_csv(session.canonical_csv),
        RevenueMode(str(session.report["revenue_mode"])),
        assumptions,
    )
    return product_demand_analysis_to_response(result)


@router.get("/analyses/{analysis_id}/canonical.csv")
def download_canonical_data(request: Request, analysis_id: str) -> Response:
    session = _get_analysis_session(_owner_scope_id(request), analysis_id)
    return Response(
        content=session.canonical_csv,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{_safe_download_name(session.filename, "canonical")}"'
            )
        },
    )


@router.get("/analyses/{analysis_id}/quarantine.csv")
def download_quarantine_data(request: Request, analysis_id: str) -> Response:
    session = _get_analysis_session(_owner_scope_id(request), analysis_id)
    return Response(
        content=session.quarantine_csv,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{_safe_download_name(session.filename, "quarantine")}"'
            )
        },
    )


@router.delete("/analyses/{analysis_id}", status_code=204)
def delete_analysis(request: Request, analysis_id: str) -> Response:
    owner_scope_id = _owner_scope_id(request)
    try:
        analysis_store.get(owner_scope_id, analysis_id)
        analysis_store.delete(owner_scope_id, analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Analysis session not found") from exc
    return Response(status_code=204)


@router.delete("/uploads/{upload_id}", status_code=204)
def delete_upload(request: Request, upload_id: str) -> Response:
    try:
        upload_store.delete(_owner_scope_id(request), upload_id)
    except UploadNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Temporary upload not found") from exc
    return Response(status_code=204)
