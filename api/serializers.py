import json
import re
from collections import defaultdict

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
    return [
        {"category": str(category), "revenue": float(value)} for category, value in labeled.items()
    ]


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
        "top_categories_by_revenue": category_series_to_records(
            analysis["top_categories_by_revenue"]
        ),
        "top_customers_by_spend": customer_series_to_records(analysis["top_customers_by_spend"]),
        "revenue_by_state": state_series_to_records(analysis["revenue_by_state"]),
    }


def segment_summary_records(segments: list) -> list:
    """
    Per-segment counts plus mean RFM -- the centroid profile that makes the
    labels interpretable (e.g. High Value is the only segment whose customers
    order more than once). Summarising server-side keeps /api/segments at a
    few hundred bytes instead of ~12MB of per-customer rows the dashboard
    never reads.
    """
    grouped = defaultdict(list)
    for segment in segments:
        grouped[segment["segment_label"]].append(segment)

    return [
        {
            "segment_label": label,
            "customer_count": len(rows),
            "avg_recency": round(sum(r["recency"] for r in rows) / len(rows), 1),
            "avg_frequency": round(sum(r["frequency"] for r in rows) / len(rows), 2),
            "avg_monetary": round(sum(r["monetary"] for r in rows) / len(rows), 2),
        }
        for label, rows in grouped.items()
    ]


def dataframe_sample_records(df: pd.DataFrame, limit: int = 5) -> list[dict]:
    """Return JSON-safe records without leaking more rows than requested."""
    return json.loads(df.head(limit).to_json(orient="records", date_format="iso"))


def privacy_safe_preview_records(df: pd.DataFrame, limit: int = 5) -> list[dict]:
    """Mask direct identifiers in the browser preview; source bytes stay private in memory."""
    records = dataframe_sample_records(df, limit)
    for record in records:
        for column, value in record.items():
            if value is None or not _is_direct_identifier_column(column):
                continue
            record[column] = _mask_preview_value(str(value), column)
    return records


def _is_direct_identifier_column(column: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", column.casefold())
    return (
        "email" in normalized
        or "phone" in normalized
        or "mobile" in normalized
        or normalized in {"customername", "clientname", "fullname", "contactname"}
    )


def _mask_preview_value(value: str, column: str) -> str:
    normalized = re.sub(r"[^a-z0-9]", "", column.casefold())
    if "email" in normalized and "@" in value:
        local, domain = value.split("@", 1)
        return f"{local[:1]}***@{domain}"
    if "name" in normalized:
        return " ".join(f"{part[:1]}***" for part in value.split() if part) or "***"
    return f"{value[:2]}***"


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a dataframe for download, encoding collection cells as JSON."""
    export = df.copy()
    for column in export.columns:
        if export[column].map(lambda value: isinstance(value, (list, tuple))).any():
            export[column] = export[column].map(
                lambda value: json.dumps(value) if isinstance(value, (list, tuple)) else value
            )
    return export.to_csv(index=False).encode("utf-8")
