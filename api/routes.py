import re
import time
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from threading import RLock
from typing import Annotated, Optional

import pandas as pd
from fastapi import APIRouter, Form, HTTPException, Request, Response, UploadFile
from pandas.errors import EmptyDataError, ParserError

from api.analysis_observability import AnalysisObservability
from api.analysis_store import (
    AnalysisExpiredError,
    AnalysisNotFoundError,
    AnalysisSession,
    AnalysisSessionStore,
)
from api.cache import cache
from api.document_store import DocumentNotFoundError, TemporaryDocumentStore
from api.product_demand import (
    product_demand_analysis_to_response,
    product_demand_assumptions_from_request,
    product_demand_data_quality_unavailable_response,
)
from api.rag_answer_service import answer_provider
from api.rag_service import retrieval_service
from api.schemas import (
    AnalysisObservabilityResponse,
    CanonicalTransformRequest,
    CanonicalTransformResponse,
    CsvPreviewResponse,
    DataValidationResponse,
    DistinctValuesRequest,
    DistinctValuesResponse,
    ForecastResponse,
    GenericAnalysisRequest,
    GenericAnalysisResponse,
    HealthResponse,
    MappingSuggestionsRequest,
    MappingSuggestionsResponse,
    ProductDemandRequest,
    ProductDemandResponse,
    RagAnswerResponse,
    RagDocumentListResponse,
    RagDocumentMetadataResponse,
    RagRetrievalRequest,
    RagRetrievalResponse,
    ReportResponse,
    SalesDataRequest,
    SchemaMappingRequest,
    SchemaMappingValidationResponse,
    SegmentsResponse,
)
from api.serializers import (
    dataframe_sample_records,
    dataframe_to_csv_bytes,
    privacy_safe_preview_records,
    report_to_response_dict,
    segment_summary_records,
)
from api.upload_store import (
    TemporaryUploadStore,
    UploadExpiredError,
    UploadNotFoundError,
)
from config import (
    ANALYSIS_TTL_MINUTES,
    RAG_DOCUMENT_MAX_BYTES,
    RAG_DOCUMENT_TTL_MINUTES,
    UPLOAD_MAX_BYTES,
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
from src.rag.answers import generate_grounded_answer
from src.rag.contracts import RagDocumentMetadata, RagDocumentType
from src.rag.index import IndexUnavailableError
from src.schema_mapping import validate_schema_mapping

router = APIRouter(prefix="/api/v1")
CSV_PREVIEW_SAMPLE_ROWS = 5
DISTINCT_VALUE_LIMIT = 100
VALIDATION_ISSUE_SAMPLE_ROWS = 20
upload_store = TemporaryUploadStore(ttl=timedelta(minutes=UPLOAD_TTL_MINUTES))
analysis_store = AnalysisSessionStore(ttl=timedelta(minutes=ANALYSIS_TTL_MINUTES))
document_store = TemporaryDocumentStore(ttl=timedelta(minutes=RAG_DOCUMENT_TTL_MINUTES))
analysis_observability = AnalysisObservability()
APPROVED_RAG_SUFFIXES = {".md", ".txt"}
rag_transaction_lock = RLock()


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


def _owner_scope_id(request: Request) -> str:
    owner_scope_id = getattr(request.state, "guest_session_id", None)
    if not owner_scope_id:
        raise HTTPException(status_code=500, detail="Guest session was not initialized")
    return str(owner_scope_id)


def _get_temporary_upload(owner_scope_id: str, upload_id: str):
    try:
        return upload_store.get(owner_scope_id, upload_id)
    except UploadExpiredError as exc:
        raise HTTPException(status_code=410, detail="Temporary upload has expired") from exc
    except UploadNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Temporary upload not found") from exc


def _get_analysis_session(owner_scope_id: str, analysis_id: str) -> AnalysisSession:
    try:
        return analysis_store.get(owner_scope_id, analysis_id)
    except AnalysisExpiredError as exc:
        _delete_analysis_rag_scope(owner_scope_id, analysis_id)
        raise HTTPException(status_code=410, detail="Analysis session has expired") from exc
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Analysis session not found") from exc


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


def _rag_document_response(metadata: RagDocumentMetadata) -> dict:
    return {
        "document_id": metadata.document_id,
        "analysis_id": metadata.analysis_id,
        "filename": metadata.filename,
        "document_type": metadata.document_type,
        "content_hash": metadata.content_hash,
        "version": metadata.version,
        "byte_count": metadata.byte_count,
        "created_at": metadata.created_at,
        "expires_at": metadata.expires_at,
        "index_status": metadata.index_status,
        "active_for_retrieval": metadata.active_for_retrieval,
        "superseded_by_document_id": metadata.superseded_by_document_id,
    }


def _rag_evidence_response(item) -> dict:
    return {
        "chunk_id": item.chunk_id,
        "document_id": item.document_id,
        "document_version": item.document_version,
        "document_type": item.document_type,
        "filename": item.filename,
        "heading": item.heading,
        "excerpt": item.excerpt,
        "citation": item.citation,
        "rank": item.rank,
        "untrusted_data": True,
        "technical": {
            "retrieval_score": item.retrieval_score,
            "method_scores": dict(item.method_scores),
            "rerank_score": item.rerank_score,
        },
    }


def _validate_english_question(question: str) -> str:
    normalized = re.sub(r"\s+", " ", question).strip()
    if len(normalized) < 3:
        raise HTTPException(status_code=422, detail="Question must contain at least 3 characters")
    if any(ord(character) < 32 for character in normalized):
        raise HTTPException(
            status_code=422,
            detail="Question contains unsupported control characters",
        )
    letters = [character for character in normalized if character.isalpha()]
    ascii_letters = [character for character in letters if character.isascii()]
    if not ascii_letters or len(ascii_letters) / max(len(letters), 1) < 0.8:
        raise HTTPException(status_code=422, detail="RAG Phase 1 supports English questions only")
    return normalized


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        report_ready=cache.analysis is not None,
        forecast_ready=cache.forecast is not None,
        segments_ready=cache.segments is not None,
    )


@router.get("/observability/analysis-metrics", response_model=AnalysisObservabilityResponse)
def analysis_metrics():
    """Expose privacy-safe local evaluation metrics; production needs admin access."""
    return analysis_observability.snapshot()


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
def segments(include_customers: bool = False):
    if cache.segments is None:
        raise HTTPException(status_code=503, detail="Segments not available")
    return {
        "segment_counts": segment_summary_records(cache.segments),
        "segments": cache.segments if include_customers else [],
    }


@router.post("/uploads/preview", response_model=CsvPreviewResponse)
async def preview_upload(request: Request, file: UploadFile):
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a CSV")

    contents = await file.read(UPLOAD_MAX_BYTES + 1)
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded CSV is empty")
    if len(contents) > UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded CSV exceeds the size limit")

    try:
        df = pd.read_csv(BytesIO(contents))
    except EmptyDataError as exc:
        raise HTTPException(status_code=400, detail="Uploaded CSV is empty") from exc
    except (ParserError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Uploaded CSV could not be parsed") from exc

    if df.empty and len(df.columns) == 0:
        raise HTTPException(status_code=400, detail="Uploaded CSV is empty")

    raw_df = pd.read_csv(BytesIO(contents), dtype=str, keep_default_na=False)
    upload = upload_store.create(
        _owner_scope_id(request),
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
        _delete_analysis_rag_scope(owner_scope_id, analysis_id)
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


@router.post(
    "/analyses/{analysis_id}/rag/documents",
    response_model=RagDocumentMetadataResponse,
)
async def upload_rag_document(
    analysis_id: str,
    request: Request,
    file: UploadFile,
    document_type: Annotated[RagDocumentType, Form()],
):
    """Atomically store, chunk and index one approved UTF-8 source."""
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() not in APPROVED_RAG_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="RAG source documents must be UTF-8 .txt or .md files",
        )
    contents = await file.read(RAG_DOCUMENT_MAX_BYTES + 1)
    if not contents:
        raise HTTPException(status_code=400, detail="RAG source document is empty")
    if len(contents) > RAG_DOCUMENT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="RAG source document exceeds the size limit")
    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="RAG source document must be UTF-8") from exc
    if not text.strip():
        raise HTTPException(status_code=400, detail="RAG source document contains no text")

    owner_scope_id = _owner_scope_id(request)
    _get_analysis_session(owner_scope_id, analysis_id)
    with rag_transaction_lock:
        previous = tuple(
            document
            for document in document_store.active_documents(owner_scope_id, analysis_id)
            if document.metadata.filename == filename
        )
        document = document_store.create(
            owner_scope_id, analysis_id, filename, document_type, text
        )
        try:
            retrieval_service.index_document(document)
            for old_document in previous:
                retrieval_service.delete_document(
                    owner_scope_id, analysis_id, old_document.metadata.document_id
                )
            document_store.activate(owner_scope_id, analysis_id, document.metadata.document_id)
        except (IndexUnavailableError, ValueError) as exc:
            try:
                retrieval_service.delete_document(
                    owner_scope_id, analysis_id, document.metadata.document_id
                )
                for old_document in previous:
                    retrieval_service.index_document(old_document)
            except Exception:
                pass
            document_store.delete(owner_scope_id, analysis_id, document.metadata.document_id)
            raise HTTPException(
                status_code=503,
                detail="Document indexing failed; the previous searchable version was preserved",
            ) from exc
        indexed = document_store.get(owner_scope_id, analysis_id, document.metadata.document_id)
    return _rag_document_response(indexed.metadata)


@router.get(
    "/analyses/{analysis_id}/rag/documents",
    response_model=RagDocumentListResponse,
)
def list_rag_documents(analysis_id: str, request: Request):
    owner_scope_id = _owner_scope_id(request)
    _get_analysis_session(owner_scope_id, analysis_id)
    documents = document_store.list(owner_scope_id, analysis_id)
    return {
        "storage_scope": "anonymous_guest_analysis",
        "durable": False,
        "documents": [_rag_document_response(metadata) for metadata in documents],
    }


@router.delete(
    "/analyses/{analysis_id}/rag/documents/{document_id}",
    status_code=204,
)
def delete_rag_document(analysis_id: str, request: Request, document_id: str) -> Response:
    owner_scope_id = _owner_scope_id(request)
    _get_analysis_session(owner_scope_id, analysis_id)
    with rag_transaction_lock:
        try:
            document_store.get(owner_scope_id, analysis_id, document_id)
            retrieval_service.delete_document(owner_scope_id, analysis_id, document_id)
            document_store.delete(owner_scope_id, analysis_id, document_id)
            if not document_store.active_documents(owner_scope_id, analysis_id):
                retrieval_service.drop_scope(owner_scope_id, analysis_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail="RAG source document not found") from exc
        except IndexUnavailableError as exc:
            raise HTTPException(
                status_code=503,
                detail="Document could not be removed from the temporary evidence index",
            ) from exc
    return Response(status_code=204)


@router.post(
    "/analyses/{analysis_id}/rag/retrieve",
    response_model=RagRetrievalResponse,
)
def retrieve_analysis_evidence(
    analysis_id: str,
    payload: RagRetrievalRequest,
    request: Request,
):
    """Return source evidence only. Phase 1 intentionally generates no answer."""
    owner_scope_id = _owner_scope_id(request)
    _get_analysis_session(owner_scope_id, analysis_id)
    question = _validate_english_question(payload.question)
    with rag_transaction_lock:
        result = retrieval_service.retrieve(owner_scope_id, analysis_id, question)
    return {
        "status": result.status,
        "analysis_id": analysis_id,
        "search_scope": "active_latest_documents_in_anonymous_guest_analysis",
        "selected_method": result.selected_method,
        "searched_document_count": result.searched_document_count,
        "searched_chunk_count": result.searched_chunk_count,
        "latency_ms": result.latency_ms,
        "reason_codes": list(result.reason_codes),
        "evidence": [_rag_evidence_response(item) for item in result.evidence],
    }


@router.post(
    "/analyses/{analysis_id}/rag/answer",
    response_model=RagAnswerResponse,
)
def answer_from_analysis_documents(
    analysis_id: str,
    payload: RagRetrievalRequest,
    request: Request,
):
    """Return a verified, document-grounded answer or no generated claims."""
    owner_scope_id = _owner_scope_id(request)
    _get_analysis_session(owner_scope_id, analysis_id)
    question = _validate_english_question(payload.question)
    with rag_transaction_lock:
        retrieval = retrieval_service.retrieve(owner_scope_id, analysis_id, question)
    result = generate_grounded_answer(question, retrieval, answer_provider)
    return {
        "status": result.status,
        "analysis_id": analysis_id,
        "search_scope": "active_latest_documents_in_anonymous_guest_analysis",
        "provider": result.provider,
        "model": result.model,
        "latency_ms": result.latency_ms,
        "reason_codes": list(result.reason_codes),
        "claims": [
            {
                "text": claim.text,
                "chunk_id": claim.chunk_id,
                "supporting_quote": claim.supporting_quote,
                "citation": claim.citation,
            }
            for claim in result.claims
        ],
        "evidence": [
            _rag_evidence_response(item) for item in result.retrieval.evidence
        ],
        "technical": {
            "selected_method": result.retrieval.selected_method,
            "searched_document_count": result.retrieval.searched_document_count,
            "searched_chunk_count": result.retrieval.searched_chunk_count,
            "retrieval_latency_ms": result.retrieval.latency_ms,
        },
    }


def _delete_analysis_rag_scope(owner_scope_id: str, analysis_id: str) -> int:
    """Remove one analysis's temporary documents and its isolated retrieval collection."""
    with rag_transaction_lock:
        documents = document_store.pop_analysis(owner_scope_id, analysis_id)
        retrieval_service.drop_scope(owner_scope_id, analysis_id)
        return len(documents)


def delete_owner_rag_scopes(owner_scope_id: str) -> int:
    """Remove all temporary RAG state when an anonymous guest expires."""
    with rag_transaction_lock:
        documents = document_store.pop_owner(owner_scope_id)
        retrieval_service.drop_owner(owner_scope_id)
        return len(documents)
