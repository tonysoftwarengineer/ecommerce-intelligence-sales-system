from pydantic import BaseModel


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


class SegmentCount(BaseModel):
    segment_label: str
    customer_count: int


class SegmentsResponse(BaseModel):
    segments: list[CustomerSegment]
    segment_counts: list[SegmentCount]


class HealthResponse(BaseModel):
    status: str
    report_ready: bool
    forecast_ready: bool
    segments_ready: bool
