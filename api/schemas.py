from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from src.generic_sales.contracts import (
    DataQualityStatus,
    DiscountScope,
    DiscountType,
    NegativeRevenuePolicy,
    OrderDiscountAllocation,
    RefundTaxTreatment,
    RevenueMismatchPolicy,
    RevenueMode,
    StandardOrderStatus,
    StandardPaymentStatus,
)
from src.product_demand.contracts import ProductIdentitySource
from src.product_demand.service import ProductDemandAnalysisStatus
from src.product_demand.trust_policy import ProductDemandTrustState
from src.rag.answers import AnswerStatus
from src.rag.contracts import RagDocumentType, RagIndexStatus, RetrievalStatus


class MonthlyRevenue(BaseModel):
    month: str
    revenue: float
    is_partial: bool


class CategoryRevenue(BaseModel):
    category: str
    revenue: float


class CustomerSpend(BaseModel):
    customer_unique_id: str
    revenue: float


class StateRevenue(BaseModel):
    state_code: str
    state_name: str
    revenue: float


class ReportResponse(BaseModel):
    total_revenue: float
    average_order_value: float
    revenue_by_month: list[MonthlyRevenue]
    top_categories_by_revenue: list[CategoryRevenue]
    top_customers_by_spend: list[CustomerSpend]
    revenue_by_state: list[StateRevenue]


class ForecastPoint(BaseModel):
    month: str
    predicted_revenue: float


class ForecastResponse(BaseModel):
    horizon_months: int
    forecast: list[ForecastPoint]


class CustomerSegment(BaseModel):
    customer_unique_id: str
    segment_label: str
    recency: float
    frequency: float
    monetary: float


class SegmentSummary(BaseModel):
    segment_label: str
    customer_count: int
    avg_recency: float
    avg_frequency: float
    avg_monetary: float


class SegmentsResponse(BaseModel):
    segment_counts: list[SegmentSummary]
    # Per-customer rows are ~12MB and no current view reads them, so they're
    # opt-in via ?include_customers=true rather than shipped on every load.
    segments: list[CustomerSegment] = []


class HealthResponse(BaseModel):
    status: str
    report_ready: bool
    forecast_ready: bool
    segments_ready: bool


class AnalysisLatencyMetrics(BaseModel):
    sample_count: int
    average: Optional[float]
    p50: Optional[float]
    p95: Optional[float]
    maximum: Optional[float]


class DiagnosticAvailabilityMetrics(BaseModel):
    section_reports: int
    assessed_reports: int
    unavailable_reports: int
    assessed_percent: Optional[float]
    processing_error_count: int
    status_counts: dict[str, int]


class AnalysisObservabilityResponse(BaseModel):
    scope: str
    analysis_runs: int
    currency_reports: int
    latency_ms: AnalysisLatencyMetrics
    diagnostics: dict[str, DiagnosticAvailabilityMetrics]
    forecast_status_counts: dict[str, int]


class RagDocumentMetadataResponse(BaseModel):
    document_id: str
    analysis_id: str
    filename: str
    document_type: RagDocumentType
    content_hash: str
    version: int
    byte_count: int
    created_at: datetime
    expires_at: datetime
    index_status: RagIndexStatus
    active_for_retrieval: bool
    superseded_by_document_id: Optional[str]


class RagDocumentListResponse(BaseModel):
    storage_scope: str
    durable: bool
    documents: list[RagDocumentMetadataResponse]


class RagRetrievalRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class RagTechnicalEvidenceResponse(BaseModel):
    retrieval_score: float
    method_scores: dict[str, float]
    rerank_score: Optional[float]


class RagEvidenceResponse(BaseModel):
    chunk_id: str
    document_id: str
    document_version: int
    document_type: RagDocumentType
    filename: str
    heading: Optional[str]
    excerpt: str
    citation: str
    rank: int
    untrusted_data: bool
    technical: RagTechnicalEvidenceResponse


class RagRetrievalResponse(BaseModel):
    status: RetrievalStatus
    analysis_id: str
    search_scope: str
    selected_method: str
    searched_document_count: int
    searched_chunk_count: int
    latency_ms: float
    reason_codes: list[str]
    evidence: list[RagEvidenceResponse]


class RagAnswerClaimResponse(BaseModel):
    text: str
    chunk_id: str
    supporting_quote: str
    citation: str


class RagAnswerTechnicalResponse(BaseModel):
    selected_method: str
    searched_document_count: int
    searched_chunk_count: int
    retrieval_latency_ms: float


class RagAnswerResponse(BaseModel):
    status: AnswerStatus
    analysis_id: str
    search_scope: str
    provider: str
    model: str
    latency_ms: float
    reason_codes: list[str]
    claims: list[RagAnswerClaimResponse]
    evidence: list[RagEvidenceResponse]
    technical: RagAnswerTechnicalResponse


class CsvPreviewResponse(BaseModel):
    upload_id: str
    expires_at: datetime
    filename: str
    row_count: int
    column_count: int
    columns: list[str]
    dtypes: dict[str, str]
    sample_rows: list[dict]


class DistinctValuesRequest(BaseModel):
    upload_id: str
    columns: list[str] = Field(min_length=1, max_length=5)


class ColumnDistinctValues(BaseModel):
    values: list[str]
    unique_count: int
    blank_count: int
    truncated: bool


class DistinctValuesResponse(BaseModel):
    columns: dict[str, ColumnDistinctValues]


class MappingSuggestionsRequest(BaseModel):
    upload_id: str
    revenue_mode: RevenueMode = RevenueMode.ROW_TOTAL


class MappingSuggestion(BaseModel):
    field: str
    column: str
    confidence: float
    reason: str


class MappingSuggestionsResponse(BaseModel):
    recommended_revenue_mode: RevenueMode
    mapping: dict[str, str]
    candidates: list[MappingSuggestion]
    warnings: list[str]


class SchemaMappingRequest(BaseModel):
    upload_id: str
    mapping: dict[str, str]
    revenue_mode: RevenueMode = RevenueMode.ROW_TOTAL


class SchemaMappingValidationResponse(BaseModel):
    valid: bool
    required_fields: list[str]
    optional_fields: list[str]
    mapped_fields: dict[str, str]
    missing_required_fields: list[str]
    unsupported_fields: list[str]
    unknown_mapped_columns: list[str]
    duplicate_mapped_columns: list[str]
    unmapped_columns: list[str]
    errors: list[str]
    warnings: list[str]


class SalesDataRequest(BaseModel):
    upload_id: str
    mapping: dict[str, str]
    revenue_mode: RevenueMode
    negative_revenue_policy: NegativeRevenuePolicy
    date_format: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    assume_all_completed: bool
    status_mapping: dict[str, StandardOrderStatus] = Field(default_factory=dict)
    payment_status_mapping: dict[str, StandardPaymentStatus] = Field(default_factory=dict)
    discount_type: DiscountType = DiscountType.NONE
    discount_scope: DiscountScope = DiscountScope.PER_LINE
    order_discount_allocation: OrderDiscountAllocation = OrderDiscountAllocation.UNALLOCATED
    revenue_mismatch_policy: RevenueMismatchPolicy = RevenueMismatchPolicy.WARN
    mismatch_tolerance: float = Field(default=0.01, ge=0)
    refund_tax_treatment: Optional[RefundTaxTreatment] = None


class ValidationIssueResponse(BaseModel):
    row_number: int
    field: str
    code: str
    message: str


class DataCorrectionActionResponse(BaseModel):
    field: str
    source_column: Optional[str]
    issue_code: str
    affected_rows: int
    sample_row_numbers: list[int]
    problem: str
    instruction: str


class DataQualityResponse(BaseModel):
    status: DataQualityStatus
    invalid_row_percentage: float
    decision_ready: bool
    preview_only: bool
    restricted_outputs: list[str]
    message: str
    correction_actions: list[DataCorrectionActionResponse]


class DataValidationResponse(BaseModel):
    can_transform: bool
    requires_confirmation: bool
    total_rows: int
    valid_rows: int
    invalid_rows: int
    issue_counts: dict[str, int]
    sample_issues: list[ValidationIssueResponse]
    warnings: list[str]
    blocking_errors: list[str]
    data_quality: DataQualityResponse


class CanonicalTransformRequest(SalesDataRequest):
    confirm_quarantine: bool = False


class CanonicalTransformResponse(BaseModel):
    filename: str
    revenue_mode: RevenueMode
    currency: str
    source_rows: int
    canonical_rows: int
    quarantined_rows: int
    canonical_columns: list[str]
    sample_rows: list[dict]
    quarantine_sample: list[dict]
    warnings: list[str]


class GenericAnalysisRequest(CanonicalTransformRequest):
    latest_period_complete: bool


class GenericCapabilities(BaseModel):
    category_analysis: bool
    regional_analysis: bool
    quantity_analysis: bool
    refund_analysis: bool
    payment_analysis: bool
    forecasting: bool


class GenericKpis(BaseModel):
    gross_revenue: float
    discount_amount: float
    refund_amount: float
    net_revenue: float
    pending_value: float
    tax_collected: float
    shipping_charged: float
    chargeback_amount: float
    disputed_value: float
    net_collected: Optional[float]
    average_order_value: float
    order_count: int
    customer_count: int
    units_sold: Optional[float]
    units_returned: Optional[float]


class GenericMonthlyRevenue(BaseModel):
    month: str
    revenue: float


class GenericCustomerRevenue(BaseModel):
    customer_id: str
    revenue: float


class GenericCategoryRevenue(BaseModel):
    category: str
    revenue: float


class GenericRegionRevenue(BaseModel):
    region: str
    revenue: float


class GenericForecastMetrics(BaseModel):
    mae: float
    rmse: float
    wape_percent: Optional[float]


class GenericForecastPoint(BaseModel):
    month: str
    predicted_revenue: float


class GenericForecastModelEvaluation(BaseModel):
    model: str
    selected: bool
    backtest_folds: int
    metrics: GenericForecastMetrics


class GenericForecast(BaseModel):
    status: str
    history_periods: int
    frequency: str
    horizon: int
    selected_model: Optional[str]
    baseline_model: str
    backtest_folds: int
    backtest_metrics: Optional[GenericForecastMetrics]
    model_evaluations: list[GenericForecastModelEvaluation]
    selection_reason: Optional[str]
    trust_level: str
    trust_message: str
    forecast: list[GenericForecastPoint]
    limitations: list[str]


class GenericDownloads(BaseModel):
    canonical_csv: str
    quarantine_csv: str


class GenericDiagnosticPeriod(BaseModel):
    current_label: str
    baseline_label: str
    basis: str


class GenericDiagnosticEvidence(BaseModel):
    metric: str
    current_value: float
    baseline_value: Optional[float]
    absolute_change: Optional[float]
    percent_change: Optional[float]
    unit: str
    provenance: str


class GenericDiagnosticContributor(BaseModel):
    factor: str
    contribution_value: float
    unit: str
    explanation: str
    share_of_change_percent: Optional[float]


class GenericDiagnosticLimitation(BaseModel):
    code: str
    message: str


class GenericRecommendationScore(BaseModel):
    impact: int
    urgency: int
    confidence: int
    total: int


class GenericRecommendedAction(BaseModel):
    id: str
    title: str
    description: str
    priority: str
    requires_human_review: bool
    estimated_impact: Optional[float]
    impact_unit: Optional[str]
    score: Optional[GenericRecommendationScore]


class GenericDiagnosticInsight(BaseModel):
    id: str
    title: str
    category: str
    observation: str
    confidence: str
    priority: str
    comparison_period: Optional[GenericDiagnosticPeriod]
    evidence: list[GenericDiagnosticEvidence]
    contributors: list[GenericDiagnosticContributor]
    limitations: list[GenericDiagnosticLimitation]
    recommended_action: Optional[GenericRecommendedAction]


class GenericDiagnosticReport(BaseModel):
    status: str
    insights: list[GenericDiagnosticInsight]
    unavailable_capabilities: list[GenericDiagnosticLimitation]


class GenericDiagnostics(BaseModel):
    comparison: GenericDiagnosticReport
    anomalies: GenericDiagnosticReport


class GenericAnalysisResponse(BaseModel):
    analysis_id: str
    expires_at: datetime
    filename: str
    currency: str
    available_currencies: list[str]
    revenue_mode: RevenueMode
    source_rows: int
    canonical_rows: int
    quarantined_rows: int
    data_quality: DataQualityResponse
    capabilities: GenericCapabilities
    kpis: GenericKpis
    revenue_by_month: list[GenericMonthlyRevenue]
    top_customers: list[GenericCustomerRevenue]
    top_categories: list[GenericCategoryRevenue]
    revenue_by_region: list[GenericRegionRevenue]
    forecast: GenericForecast
    diagnostics: GenericDiagnostics
    warnings: list[str]
    downloads: GenericDownloads


class ProductStockoutDatesRequest(BaseModel):
    identity_source: ProductIdentitySource
    identity_value: str = Field(min_length=1, max_length=200)
    dates: list[date] = Field(min_length=1)


class ProductDemandRequest(BaseModel):
    default_unit_of_measure: Optional[str] = Field(default=None, min_length=1, max_length=50)
    confirm_product_names_unique: bool = False
    confirm_product_categories: bool = False
    export_covers_all_open_days: bool = False
    stockout_tracking_complete: bool = False
    business_closed_dates: list[date] = Field(default_factory=list)
    stockout_dates: list[ProductStockoutDatesRequest] = Field(default_factory=list)


class ProductDemandEvidenceResponse(BaseModel):
    shared_test_weeks: int
    minimum_required_test_weeks: int
    benchmark: str
    benchmark_passed: bool
    selected_mean_absolute_error_units: Optional[float]
    zero_mean_absolute_error_units: Optional[float]
    skill_vs_zero_percent: Optional[float]


class ProductDemandForecastResponse(BaseModel):
    total_units: float
    average_daily_planning_rate: float
    forecast_dates: list[date]
    daily_predictions_provided: bool


class ProductDemandProductResponse(BaseModel):
    product_key: str
    product_id: Optional[str]
    product_name: Optional[str]
    identity_source: ProductIdentitySource
    unit_of_measure: Optional[str]
    trust_state: ProductDemandTrustState
    numeric_forecast_allowed: bool
    selected_method: Optional[str]
    selected_method_name: Optional[str]
    selection_reason: Optional[str]
    evidence: ProductDemandEvidenceResponse
    forecast: Optional[ProductDemandForecastResponse]
    policy_reason_codes: list[str]
    data_reason_codes: list[str]
    explanations: list[str]
    warning: str


class ProductDemandCategoryResponse(BaseModel):
    category_key: str
    category_name: str
    product_count: int
    unit_of_measure: Optional[str]
    trust_state: ProductDemandTrustState
    numeric_forecast_allowed: bool
    selected_method: Optional[str]
    selected_method_name: Optional[str]
    selection_reason: Optional[str]
    evidence: ProductDemandEvidenceResponse
    forecast: Optional[ProductDemandForecastResponse]
    policy_reason_codes: list[str]
    category_reason_codes: list[str]
    explanations: list[str]
    warning: str


class ProductDemandResponse(BaseModel):
    status: ProductDemandAnalysisStatus
    target: str
    target_definition: str
    horizon_days: int
    supported_use_approved: bool
    preview_product_count: int
    unavailable_product_count: int
    preview_category_count: int
    unavailable_category_count: int
    unresolved_row_count: int
    minimum_preview_test_weeks: int
    products: list[ProductDemandProductResponse]
    categories: list[ProductDemandCategoryResponse]
    dataset_reason_codes: list[str]
    dataset_explanations: list[str]
    category_dataset_reason_codes: list[str]
    category_dataset_explanations: list[str]
    warning: str
