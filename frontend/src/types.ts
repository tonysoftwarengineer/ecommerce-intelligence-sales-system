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

export interface SegmentCount {
  segment_label: string;
  customer_count: number;
}

export interface SegmentsResponse {
  segments: CustomerSegment[];
  segment_counts: SegmentCount[];
}
