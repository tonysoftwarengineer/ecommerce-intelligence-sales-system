export interface MonthlyRevenue {
  month: string;
  revenue: number;
  /** True for dataset-boundary / near-empty months (see partial_months in
   *  src/models/forecast.py). Excluded from the trend chart. */
  is_partial: boolean;
}

export interface CategoryRevenue {
  category: string;
  revenue: number;
}

export interface CustomerSpend {
  customer_unique_id: string;
  revenue: number;
}

export interface StateRevenue {
  state_code: string;
  state_name: string;
  revenue: number;
}

export interface ReportResponse {
  total_revenue: number;
  average_order_value: number;
  revenue_by_month: MonthlyRevenue[];
  top_categories_by_revenue: CategoryRevenue[];
  top_customers_by_spend: CustomerSpend[];
  revenue_by_state: StateRevenue[];
}

export interface ForecastPoint {
  month: string;
  predicted_revenue: number;
}

export interface ForecastResponse {
  horizon_months: number;
  forecast: ForecastPoint[];
}

export interface CustomerSegment {
  customer_unique_id: string;
  segment_label: string;
  recency: number;
  frequency: number;
  monetary: number;
}

export interface SegmentSummary {
  segment_label: string;
  customer_count: number;
  avg_recency: number;
  avg_frequency: number;
  avg_monetary: number;
}

export interface SegmentsResponse {
  segment_counts: SegmentSummary[];
  /** Empty unless requested with ?include_customers=true — ~12MB otherwise. */
  segments: CustomerSegment[];
}

export type RevenueMode = "row_total" | "unit_price_times_quantity" | "order_total";
export type NegativeRevenuePolicy = "refunds" | "invalid";
export type StandardOrderStatus = "completed" | "pending" | "cancelled" | "returned";
export type StandardPaymentStatus =
  | "paid"
  | "refunded"
  | "pending"
  | "failed"
  | "voided"
  | "disputed"
  | "chargeback_won"
  | "chargeback_lost";
export type DiscountType = "none" | "fixed" | "percentage";
export type DiscountScope = "per_unit" | "per_line" | "entire_order";
export type OrderDiscountAllocation = "unallocated" | "proportional";
export type RevenueMismatchPolicy = "warn" | "quarantine";
export type RefundTaxTreatment = "excludes_tax" | "includes_tax";

export interface CsvPreviewResponse {
  upload_id: string;
  expires_at: string;
  filename: string;
  row_count: number;
  column_count: number;
  columns: string[];
  dtypes: Record<string, string>;
  sample_rows: Record<string, unknown>[];
}

export interface SchemaMappingResponse {
  valid: boolean;
  required_fields: string[];
  optional_fields: string[];
  mapped_fields: Record<string, string>;
  missing_required_fields: string[];
  unsupported_fields: string[];
  unknown_mapped_columns: string[];
  duplicate_mapped_columns: string[];
  unmapped_columns: string[];
  errors: string[];
  warnings: string[];
}

export interface DistinctValuesResponse {
  columns: Record<
    string,
    { values: string[]; unique_count: number; blank_count: number; truncated: boolean }
  >;
}

export interface MappingSuggestionsResponse {
  recommended_revenue_mode: RevenueMode;
  mapping: Record<string, string>;
  candidates: Array<{ field: string; column: string; confidence: number; reason: string }>;
  warnings: string[];
}

export interface ValidationIssue {
  row_number: number;
  field: string;
  code: string;
  message: string;
}

export type DataQualityStatus = "normal" | "caution" | "preview" | "blocked";

export interface DataCorrectionAction {
  field: string;
  source_column: string | null;
  issue_code: string;
  affected_rows: number;
  sample_row_numbers: number[];
  problem: string;
  instruction: string;
}

export interface DataQualityReport {
  status: DataQualityStatus;
  invalid_row_percentage: number;
  decision_ready: boolean;
  preview_only: boolean;
  restricted_outputs: string[];
  message: string;
  correction_actions: DataCorrectionAction[];
}

export interface DataValidationResponse {
  can_transform: boolean;
  requires_confirmation: boolean;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  issue_counts: Record<string, number>;
  sample_issues: ValidationIssue[];
  warnings: string[];
  blocking_errors: string[];
  data_quality: DataQualityReport;
}

export interface SalesConfiguration {
  upload_id: string;
  mapping: Record<string, string>;
  revenue_mode: RevenueMode;
  negative_revenue_policy: NegativeRevenuePolicy;
  date_format: string;
  currency: string;
  assume_all_completed: boolean;
  status_mapping: Record<string, StandardOrderStatus>;
  payment_status_mapping: Record<string, StandardPaymentStatus>;
  discount_type: DiscountType;
  discount_scope: DiscountScope;
  order_discount_allocation: OrderDiscountAllocation;
  revenue_mismatch_policy: RevenueMismatchPolicy;
  mismatch_tolerance: number;
  refund_tax_treatment: RefundTaxTreatment | null;
}

export interface GenericForecastMetrics {
  mae: number;
  rmse: number;
  wape_percent: number | null;
}

export interface GenericForecastModelEvaluation {
  model: string;
  selected: boolean;
  backtest_folds: number;
  metrics: GenericForecastMetrics;
}

export interface GenericForecast {
  status: "unavailable" | "experimental" | "available";
  history_periods: number;
  frequency: string;
  horizon: number;
  selected_model: string | null;
  baseline_model: string;
  backtest_folds: number;
  backtest_metrics: GenericForecastMetrics | null;
  model_evaluations: GenericForecastModelEvaluation[];
  selection_reason: string | null;
  trust_level: "unavailable" | "limited" | "exploratory" | "moderate" | "strong";
  trust_message: string;
  forecast: ForecastPoint[];
  limitations: string[];
}

export interface DiagnosticLimitation {
  code: string;
  message: string;
}

export interface DiagnosticEvidence {
  metric: string;
  current_value: number;
  baseline_value: number | null;
  absolute_change: number | null;
  percent_change: number | null;
  unit: string;
  provenance: string;
}

export interface DiagnosticRecommendation {
  id: string;
  title: string;
  description: string;
  priority: "critical" | "high" | "medium" | "low";
  requires_human_review: boolean;
  estimated_impact: number | null;
  impact_unit: string | null;
  score: { impact: number; urgency: number; confidence: number; total: number } | null;
}

export interface DiagnosticInsight {
  id: string;
  title: string;
  category: string;
  observation: string;
  confidence: "high" | "medium" | "low" | "unavailable";
  priority: "critical" | "high" | "medium" | "low";
  comparison_period: {
    current_label: string;
    baseline_label: string;
    basis: string;
  } | null;
  evidence: DiagnosticEvidence[];
  contributors: Array<{
    factor: string;
    contribution_value: number;
    unit: string;
    explanation: string;
    share_of_change_percent: number | null;
  }>;
  limitations: DiagnosticLimitation[];
  recommended_action: DiagnosticRecommendation | null;
}

export interface DiagnosticReport {
  status: "available" | "no_findings" | "unavailable";
  insights: DiagnosticInsight[];
  unavailable_capabilities: DiagnosticLimitation[];
}

export interface GenericAnalysisResponse {
  analysis_id: string;
  expires_at: string;
  filename: string;
  currency: string;
  available_currencies: string[];
  revenue_mode: RevenueMode;
  source_rows: number;
  canonical_rows: number;
  quarantined_rows: number;
  data_quality: DataQualityReport;
  capabilities: {
    category_analysis: boolean;
    regional_analysis: boolean;
    quantity_analysis: boolean;
    refund_analysis: boolean;
    payment_analysis: boolean;
    forecasting: boolean;
  };
  kpis: {
    gross_revenue: number;
    discount_amount: number;
    refund_amount: number;
    net_revenue: number;
    pending_value: number;
    tax_collected: number;
    shipping_charged: number;
    chargeback_amount: number;
    disputed_value: number;
    net_collected: number | null;
    average_order_value: number;
    order_count: number;
    customer_count: number;
    units_sold: number | null;
    units_returned: number | null;
  };
  revenue_by_month: Array<{ month: string; revenue: number }>;
  top_customers: Array<{ customer_id: string; revenue: number }>;
  top_categories: CategoryRevenue[];
  revenue_by_region: Array<{ region: string; revenue: number }>;
  forecast: GenericForecast;
  diagnostics: {
    comparison: DiagnosticReport;
    anomalies: DiagnosticReport;
  };
  warnings: string[];
  downloads: {
    canonical_csv: string;
    quarantine_csv: string;
  };
}

export type ProductIdentitySource = "product_id" | "product_name";
export type ProductDemandTrustState =
  | "unavailable"
  | "limited_preview"
  | "supported_weekly";

export interface ProductStockoutDatesInput {
  identity_source: ProductIdentitySource;
  identity_value: string;
  dates: string[];
}

export interface ProductDemandRequest {
  default_unit_of_measure?: string;
  confirm_product_names_unique: boolean;
  confirm_product_categories: boolean;
  export_covers_all_open_days: boolean;
  stockout_tracking_complete: boolean;
  business_closed_dates: string[];
  stockout_dates: ProductStockoutDatesInput[];
}

export interface ProductDemandEvidence {
  shared_test_weeks: number;
  minimum_required_test_weeks: number;
  benchmark: "zero";
  benchmark_passed: boolean;
  selected_mean_absolute_error_units: number | null;
  zero_mean_absolute_error_units: number | null;
  skill_vs_zero_percent: number | null;
}

export interface ProductDemandForecast {
  total_units: number;
  average_daily_planning_rate: number;
  forecast_dates: string[];
  daily_predictions_provided: false;
}

export interface ProductDemandProduct {
  product_key: string;
  product_id: string | null;
  product_name: string | null;
  identity_source: ProductIdentitySource;
  unit_of_measure: string | null;
  trust_state: ProductDemandTrustState;
  numeric_forecast_allowed: boolean;
  selected_method: string | null;
  selected_method_name: string | null;
  selection_reason: string | null;
  evidence: ProductDemandEvidence;
  forecast: ProductDemandForecast | null;
  policy_reason_codes: string[];
  data_reason_codes: string[];
  explanations: string[];
  warning: string;
}

export interface ProductDemandCategory {
  category_key: string;
  category_name: string;
  product_count: number;
  unit_of_measure: string | null;
  trust_state: ProductDemandTrustState;
  numeric_forecast_allowed: boolean;
  selected_method: string | null;
  selected_method_name: string | null;
  selection_reason: string | null;
  evidence: ProductDemandEvidence;
  forecast: ProductDemandForecast | null;
  policy_reason_codes: string[];
  category_reason_codes: string[];
  explanations: string[];
  warning: string;
}

export interface ProductDemandResponse {
  status: "unavailable" | "partial_preview" | "preview_available";
  target: "fulfilled_units";
  target_definition: string;
  horizon_days: 7;
  supported_use_approved: false;
  preview_product_count: number;
  unavailable_product_count: number;
  preview_category_count: number;
  unavailable_category_count: number;
  unresolved_row_count: number;
  minimum_preview_test_weeks: number;
  products: ProductDemandProduct[];
  categories: ProductDemandCategory[];
  dataset_reason_codes: string[];
  dataset_explanations: string[];
  category_dataset_reason_codes: string[];
  category_dataset_explanations: string[];
  warning: string;
}

export type RagDocumentType =
  | "policy"
  | "supplier_notice"
  | "product_catalog"
  | "operating_calendar"
  | "other_approved";

export interface RagDocumentMetadata {
  document_id: string;
  analysis_id: string;
  filename: string;
  document_type: RagDocumentType;
  content_hash: string;
  version: number;
  byte_count: number;
  created_at: string;
  expires_at: string;
  index_status: "pending" | "ready" | "superseded";
  active_for_retrieval: boolean;
  superseded_by_document_id: string | null;
}

export interface RagDocumentListResponse {
  storage_scope: "anonymous_guest_analysis";
  durable: false;
  documents: RagDocumentMetadata[];
}

export interface RagEvidence {
  chunk_id: string;
  document_id: string;
  document_version: number;
  document_type: RagDocumentType;
  filename: string;
  heading: string | null;
  excerpt: string;
  citation: string;
  rank: number;
  untrusted_data: true;
  technical: {
    retrieval_score: number;
    method_scores: Record<string, number>;
    rerank_score: number | null;
  };
}

export interface RagRetrievalResponse {
  status: "evidence_available" | "insufficient_evidence" | "unavailable";
  analysis_id: string;
  search_scope: string;
  selected_method: string;
  searched_document_count: number;
  searched_chunk_count: number;
  latency_ms: number;
  reason_codes: string[];
  evidence: RagEvidence[];
}

export interface RagGroundedClaim {
  text: string;
  chunk_id: string;
  supporting_quote: string;
  citation: string;
}

export interface RagAnswerResponse {
  status: "grounded_answer" | "insufficient_evidence" | "unavailable";
  analysis_id: string;
  search_scope: string;
  provider: string;
  model: string;
  latency_ms: number;
  reason_codes: string[];
  claims: RagGroundedClaim[];
  evidence: RagEvidence[];
  technical: {
    selected_method: string;
    searched_document_count: number;
    searched_chunk_count: number;
    retrieval_latency_ms: number;
  };
}
