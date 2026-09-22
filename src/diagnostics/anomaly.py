"""Conservative, explainable anomaly detection for monthly sales metrics."""

from __future__ import annotations

import pandas as pd

from src.diagnostics.comparison import (
    _complete_months,
    _percent_change,
    monthly_recognized_sales_metrics,
)
from src.diagnostics.contracts import (
    ComparisonPeriod,
    ConfidenceLevel,
    DiagnosticCategory,
    DiagnosticInsight,
    DiagnosticReport,
    DiagnosticStatus,
    EvidenceItem,
    Limitation,
    Priority,
)

MIN_BASELINE_PERIODS = 6
MAD_THRESHOLD = 3.5
MAD_SCALE = 1.4826
CONTRACT_VERSION = "1.0"


def build_monthly_anomaly_report(
    canonical_data: pd.DataFrame,
    latest_period_complete: bool,
) -> DiagnosticReport:
    """Flag unusual latest-period metrics using a rolling median/MAD baseline.

    Six prior complete, consecutive months are required for the baseline plus
    one current complete month. A missing month is a data-quality limitation,
    not zero sales. If no metric crosses the robust threshold, the report is
    explicitly marked as ``no_findings``.
    """
    _require_columns(canonical_data)
    currency = _single_currency(canonical_data)
    monthly = monthly_recognized_sales_metrics(canonical_data)
    periods, exclusions = _complete_months(monthly, latest_period_complete)
    unavailable = _history_unavailable_reason(periods)
    if unavailable is not None:
        return DiagnosticReport(
            contract_version=CONTRACT_VERSION,
            currency=currency,
            insights=(),
            unavailable_capabilities=exclusions
            + (Limitation(code=unavailable[0], message=unavailable[1]),),
            status=DiagnosticStatus.UNAVAILABLE,
        )

    current_period = periods[-1]
    baseline_periods = periods[-(MIN_BASELINE_PERIODS + 1) : -1]
    metrics = (
        ("recognized_sales", "recognized sales", currency, "canonical_sales.recognized_sales"),
        ("completed_orders", "completed orders", "orders", "canonical_sales.order_id"),
        (
            "average_order_value",
            "average order value",
            currency,
            "derived recognized_sales / orders",
        ),
    )
    insights = tuple(
        insight
        for metric, label, unit, provenance in metrics
        if (
            insight := _anomaly_insight(
                metric,
                label,
                unit,
                provenance,
                current_period,
                baseline_periods,
                _metric_series(monthly, metric),
            )
        )
    )
    return DiagnosticReport(
        contract_version=CONTRACT_VERSION,
        currency=currency,
        insights=insights,
        status=DiagnosticStatus.AVAILABLE if insights else DiagnosticStatus.NO_FINDINGS,
    )


def _metric_series(monthly: pd.DataFrame, metric: str) -> pd.Series:
    if metric != "average_order_value":
        return monthly[metric].astype(float)
    orders = monthly["completed_orders"].astype(float)
    return monthly["recognized_sales"].astype(float).div(orders.where(orders > 0))


def _anomaly_insight(
    metric: str,
    label: str,
    unit: str,
    provenance: str,
    current_period: pd.Period,
    baseline_periods: list[pd.Period],
    series: pd.Series,
) -> DiagnosticInsight | None:
    current_value = series.loc[current_period]
    history = series.loc[baseline_periods].dropna().astype(float)
    if len(history) < MIN_BASELINE_PERIODS or pd.isna(current_value):
        return None

    median = float(history.median())
    mad = float((history - median).abs().median())
    deviation = float(current_value) - median
    robust_scale = MAD_SCALE * mad
    if robust_scale == 0:
        is_anomaly = deviation != 0
        robust_score = float("inf") if is_anomaly else 0.0
    else:
        robust_score = abs(deviation) / robust_scale
        is_anomaly = robust_score >= MAD_THRESHOLD
    if not is_anomaly:
        return None

    direction = "high" if deviation > 0 else "low"
    score_text = (
        "outside the baseline"
        if robust_score == float("inf")
        else f"{robust_score:.1f} robust deviations"
    )
    comparison = ComparisonPeriod(
        current_label=str(current_period),
        baseline_label=f"rolling median of prior {MIN_BASELINE_PERIODS} complete months",
        basis="rolling_median_mad",
    )
    limitations = (
        Limitation(
            code="non_causal_finding",
            message="The anomaly identifies an unusual movement but does not establish its cause.",
        ),
    )
    return DiagnosticInsight(
        id=f"anomaly_{metric}",
        title=f"Unusually {direction} {label} detected",
        category=DiagnosticCategory.ANOMALY,
        observation=(
            f"{label.capitalize()} in {current_period} was {_format_value(current_value, unit)}; "
            f"the rolling median was {_format_value(median, unit)}. "
            f"The value is {score_text} across the six-month baseline."
        ),
        confidence=ConfidenceLevel.MEDIUM,
        priority=Priority.MEDIUM,
        evidence=(
            EvidenceItem(
                metric=metric,
                current_value=round(float(current_value), 2),
                baseline_value=round(median, 2),
                absolute_change=round(deviation, 2),
                percent_change=_round_optional(_percent_change(float(current_value), median)),
                unit=unit,
                provenance=provenance,
            ),
        ),
        comparison_period=comparison,
        limitations=limitations,
    )


def _history_unavailable_reason(periods: list[pd.Period]) -> tuple[str, str] | None:
    required = MIN_BASELINE_PERIODS + 1
    if len(periods) < required:
        return (
            "insufficient_anomaly_history",
            "Anomaly detection requires six prior complete months plus the current month; "
            f"{len(periods)} complete month(s) are available.",
        )
    expected = pd.period_range(periods[0], periods[-1], freq="M")
    if list(expected) != periods:
        return (
            "non_contiguous_anomaly_history",
            "Anomaly detection requires consecutive complete months; missing months are not "
            "assumed to be zero sales.",
        )
    return None


def _require_columns(canonical_data: pd.DataFrame) -> None:
    required = {"order_id", "order_date", "currency"}
    missing = sorted(required - set(canonical_data.columns))
    if missing:
        raise ValueError("Canonical data is missing required columns: " + ", ".join(missing))
    if canonical_data.empty:
        raise ValueError("Canonical data contains no rows")


def _single_currency(canonical_data: pd.DataFrame) -> str:
    currencies = sorted(str(value) for value in canonical_data["currency"].dropna().unique())
    if len(currencies) != 1:
        raise ValueError("Anomaly detection requires exactly one currency")
    return currencies[0]


def _format_value(value: float, unit: str) -> str:
    return f"{unit} {float(value):,.2f}" if unit != "orders" else f"{float(value):,.0f} orders"


def _round_optional(value: float | None) -> float | None:
    return None if value is None else round(value, 2)
