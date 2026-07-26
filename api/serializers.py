from collections import Counter

import pandas as pd

from src.models.forecast import partial_months
from src.stages.report import relabel_state_names, relabel_unknown_category


def month_series_to_records(series: pd.Series) -> list:
    # The "which months are unreliable" rule lives in src/models/forecast.py,
    # shared with the forecast's edge trimming -- not duplicated here.
    partial = partial_months(series)
    return [
        {"month": str(period), "revenue": float(value), "is_partial": period in partial}
        for period, value in series.items()
    ]


def category_series_to_records(series: pd.Series) -> list:
    labeled = relabel_unknown_category(series)
    return [{"category": str(category), "revenue": float(value)} for category, value in labeled.items()]


def customer_series_to_records(series: pd.Series) -> list:
    return [
        {"customer_unique_id": str(customer_id), "revenue": float(value)}
        for customer_id, value in series.items()
    ]


def state_series_to_records(series: pd.Series) -> list:
    named = relabel_state_names(series)
    return [
        {"state_code": code, "state_name": name, "revenue": float(value)}
        for code, name, value in zip(series.index, named.index, series.values)
    ]


def report_to_response_dict(analysis: dict) -> dict:
    return {
        "total_revenue": float(analysis["total_revenue"]),
        "average_order_value": float(analysis["average_order_value"]),
        "revenue_by_month": month_series_to_records(analysis["revenue_by_month"]),
        "top_categories_by_revenue": category_series_to_records(analysis["top_categories_by_revenue"]),
        "top_customers_by_spend": customer_series_to_records(analysis["top_customers_by_spend"]),
        "revenue_by_state": state_series_to_records(analysis["revenue_by_state"]),
    }


def segment_counts_to_records(segments: list) -> list:
    counts = Counter(s["segment_label"] for s in segments)
    return [{"segment_label": label, "customer_count": count} for label, count in counts.items()]
