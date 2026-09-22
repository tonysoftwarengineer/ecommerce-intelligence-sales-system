from decimal import Decimal
from typing import Any, Optional

import pandas as pd

CANONICAL_REQUIRED_COLUMNS = frozenset(
    {"order_id", "order_date", "customer_id", "revenue", "currency"}
)
TOP_N = 10


def analyze_canonical_sales(
    df: pd.DataFrame,
    mapped_fields: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Calculate grain-safe retail analytics for exactly one currency."""
    missing = sorted(CANONICAL_REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise ValueError("Canonical dataset is missing required columns: " + ", ".join(missing))
    if df.empty:
        raise ValueError("Canonical dataset contains no rows")
    currencies = sorted(str(value) for value in df["currency"].dropna().unique())
    if len(currencies) != 1:
        raise ValueError("Canonical analytics must contain exactly one currency")

    revenue = _money_series(df, "revenue")
    gross = _money_series(df, "gross_sales", positive_only_fallback=revenue)
    discounts = _money_series(df, "discount_amount")
    refunds = _money_series(df, "refund_amount", negative_fallback=revenue)
    recognized_sales = _money_series(df, "recognized_sales", fallback=gross - discounts)
    pending = _money_series(df, "pending_value")
    tax = _money_series(df, "tax_amount")
    shipping = _money_series(df, "shipping_amount")
    chargebacks = _money_series(df, "chargeback_amount")
    disputed = _money_series(df, "disputed_value")
    has_payment_evidence = "payment_amount" in (mapped_fields or set())
    net_collected = _money_series(df, "net_collected") if has_payment_evidence else None

    recognized_mask = (
        gross > 0 if "gross_sales" in df.columns else pd.Series([True] * len(df), index=df.index)
    )
    recognized = df.loc[recognized_mask].copy()
    order_revenue = revenue.loc[recognized_mask].groupby(recognized["order_id"], sort=False).sum()
    monthly, monthly_sales, monthly_refunds = _monthly_net_revenue(df, recognized_sales, refunds)
    trailing_adjustments = _trailing_adjustment_only_periods(monthly_sales, monthly_refunds)
    forecast_series = monthly_sales.drop(trailing_adjustments)

    available = set(df.columns) if mapped_fields is None else mapped_fields
    capabilities = {
        "category_analysis": "product_category" in available,
        "regional_analysis": "state_or_region" in available,
        "quantity_analysis": "quantity" in available,
        "refund_analysis": bool({"refund_amount", "returned_quantity"} & available),
        "payment_analysis": bool(
            {"payment_status", "payment_amount", "chargeback_amount"} & available
        ),
    }
    result: dict[str, Any] = {
        "currency": currencies[0],
        "kpis": {
            "gross_revenue": _rounded(gross.sum()),
            "discount_amount": _rounded(discounts.sum()),
            "refund_amount": _rounded(refunds.sum()),
            "net_revenue": _rounded(revenue.sum()),
            "pending_value": _rounded(pending.sum()),
            "tax_collected": _rounded(tax.sum()),
            "shipping_charged": _rounded(shipping.sum()),
            "chargeback_amount": _rounded(chargebacks.sum()),
            "disputed_value": _rounded(disputed.sum()),
            "net_collected": _rounded(net_collected.sum()) if net_collected is not None else None,
            "average_order_value": (
                _rounded(order_revenue.mean()) if not order_revenue.empty else 0.0
            ),
            "order_count": int(recognized["order_id"].nunique()),
            "customer_count": int(recognized["customer_id"].nunique()),
            "units_sold": None,
            "units_returned": None,
        },
        "capabilities": capabilities,
        "revenue_by_month": [
            {"month": str(month), "revenue": _rounded(value)} for month, value in monthly.items()
        ],
        "top_customers": _grouped_revenue_records(
            df.assign(_revenue=revenue), "customer_id", "customer_id"
        ),
        "top_categories": [],
        "revenue_by_region": [],
        "monthly_series": monthly.astype(float),
        "forecast_series": forecast_series.astype(float),
        "forecast_excluded_adjustment_periods": [str(period) for period in trailing_adjustments],
    }
    if capabilities["quantity_analysis"]:
        quantities = _decimal_series(df["quantity"])
        result["kpis"]["units_sold"] = _rounded(quantities.loc[recognized_mask].sum())
    if "returned_quantity" in df.columns:
        result["kpis"]["units_returned"] = _rounded(_decimal_series(df["returned_quantity"]).sum())

    if capabilities["category_analysis"]:
        category_values = _money_series(df, "category_revenue", fallback=revenue)
        result["top_categories"] = _grouped_revenue_records(
            df.assign(_revenue=category_values),
            "product_category",
            "category",
            missing_label="Uncategorized",
        )
    if capabilities["regional_analysis"]:
        result["revenue_by_region"] = _grouped_revenue_records(
            df.assign(_revenue=revenue),
            "state_or_region",
            "region",
            missing_label="Unspecified region",
        )
    return result


def _monthly_net_revenue(
    df: pd.DataFrame,
    recognized_sales: pd.Series,
    refunds: pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    recognition_dates = (
        df["recognition_date"] if "recognition_date" in df.columns else df["order_date"]
    )
    sales = recognized_sales.groupby(recognition_dates.dt.to_period("M")).sum()
    refund_dates = (
        df["refund_date"].where(df["refund_date"].notna(), recognition_dates)
        if "refund_date" in df.columns
        else recognition_dates
    )
    refund_events = refunds.groupby(refund_dates.dt.to_period("M")).sum()
    sales = sales.sort_index()
    refund_events = refund_events.sort_index()
    monthly = sales.subtract(refund_events, fill_value=Decimal("0")).sort_index()
    return (
        monthly,
        sales.reindex(monthly.index, fill_value=Decimal("0")),
        refund_events.reindex(monthly.index, fill_value=Decimal("0")),
    )


def _trailing_adjustment_only_periods(
    sales: pd.Series,
    refunds: pd.Series,
) -> list[pd.Period]:
    """Keep refund events in reporting, excluding post-sales adjustments from forecasting."""
    combined = sales.add(refunds, fill_value=Decimal("0")).sort_index()
    excluded: list[pd.Period] = []
    for period in reversed(combined.index.tolist()):
        if sales.get(period, Decimal("0")) == 0 and refunds.get(period, Decimal("0")) > 0:
            excluded.append(period)
            continue
        break
    return list(reversed(excluded))


def _money_series(
    df: pd.DataFrame,
    column: str,
    fallback: Optional[pd.Series] = None,
    positive_only_fallback: Optional[pd.Series] = None,
    negative_fallback: Optional[pd.Series] = None,
) -> pd.Series:
    if column in df.columns:
        return _decimal_series(df[column])
    if positive_only_fallback is not None:
        return positive_only_fallback.map(lambda value: max(value, Decimal("0")))
    if negative_fallback is not None:
        return negative_fallback.map(lambda value: abs(min(value, Decimal("0"))))
    if fallback is not None:
        return fallback
    return pd.Series([Decimal("0")] * len(df), index=df.index, dtype=object)


def _decimal_series(series: pd.Series) -> pd.Series:
    return series.map(lambda value: Decimal(str(value)) if pd.notna(value) else Decimal("0"))


def _rounded(value: Any) -> float:
    return round(float(value), 2)


def _grouped_revenue_records(
    df: pd.DataFrame,
    group_column: str,
    output_key: str,
    missing_label: Optional[str] = None,
) -> list[dict[str, Any]]:
    labels = df[group_column]
    if missing_label is not None:
        labels = labels.map(
            lambda value: (
                missing_label if pd.isna(value) or not str(value).strip() else str(value).strip()
            )
        )
    grouped = (
        df.assign(_group_label=labels)
        .groupby("_group_label", dropna=False)["_revenue"]
        .sum()
        .sort_values(ascending=False)
        .head(TOP_N)
    )
    return [
        {output_key: str(label), "revenue": _rounded(value)} for label, value in grouped.items()
    ]
