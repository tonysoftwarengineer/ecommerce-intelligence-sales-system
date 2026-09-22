"""Complete-period revenue comparison and exact decomposition diagnostics."""

from __future__ import annotations

import pandas as pd

from src.diagnostics.contracts import (
    ComparisonPeriod,
    ConfidenceLevel,
    Contributor,
    DiagnosticCategory,
    DiagnosticInsight,
    DiagnosticReport,
    EvidenceItem,
    Limitation,
    Priority,
)

REQUIRED_COLUMNS = frozenset({"order_id", "order_date", "currency"})
CONTRACT_VERSION = "1.0"


def build_latest_complete_period_revenue_report(
    canonical_data: pd.DataFrame,
    latest_period_complete: bool,
) -> DiagnosticReport:
    """Compare the two latest complete months and decompose recognized sales.

    The decomposition uses the symmetric form of the identity R = orders × AOV:

    order contribution = (orders_current - orders_baseline) × mean(AOV)
    AOV contribution = (AOV_current - AOV_baseline) × mean(orders)

    The contributions add exactly to the recognized-sales change, avoiding an
    order-dependent attribution between order volume and average order value.
    Refund-only adjustments are intentionally excluded from this first sales
    decomposition and will be handled by a dedicated refund diagnostic.
    """
    _require_columns(canonical_data)
    currency = _single_currency(canonical_data)
    monthly = monthly_recognized_sales_metrics(canonical_data)
    complete_months, exclusions = _complete_months(monthly, latest_period_complete)

    unavailable = _comparison_unavailable_reason(complete_months)
    if unavailable is not None:
        return DiagnosticReport(
            contract_version=CONTRACT_VERSION,
            currency=currency,
            insights=(),
            unavailable_capabilities=exclusions
            + (Limitation(code=unavailable[0], message=unavailable[1]),),
        )

    baseline_period, current_period = complete_months[-2:]
    baseline = monthly.loc[baseline_period]
    current = monthly.loc[current_period]
    if baseline["completed_orders"] == 0 or current["completed_orders"] == 0:
        return DiagnosticReport(
            contract_version=CONTRACT_VERSION,
            currency=currency,
            insights=(),
            unavailable_capabilities=exclusions
            + (
                Limitation(
                    code="zero_completed_orders",
                    message=(
                        "Revenue decomposition requires at least one completed order in both "
                        "comparison periods."
                    ),
                ),
            ),
        )

    baseline_sales = float(baseline["recognized_sales"])
    current_sales = float(current["recognized_sales"])
    baseline_orders = int(baseline["completed_orders"])
    current_orders = int(current["completed_orders"])
    baseline_aov = baseline_sales / baseline_orders
    current_aov = current_sales / current_orders
    change = current_sales - baseline_sales
    percent_change = _percent_change(current_sales, baseline_sales)
    order_contribution = (current_orders - baseline_orders) * (baseline_aov + current_aov) / 2
    aov_contribution = (current_aov - baseline_aov) * (baseline_orders + current_orders) / 2

    limitations = list(exclusions)
    limitations.append(
        Limitation(
            code="two_period_comparison",
            message=(
                "This is a comparison of two complete months. It does not establish a trend, "
                "anomaly, or causal explanation."
            ),
        )
    )
    comparison = ComparisonPeriod(
        current_label=str(current_period),
        baseline_label=str(baseline_period),
        basis="previous_complete_month",
    )
    insight = DiagnosticInsight(
        id="recognized_sales_change",
        title=_change_title(change, percent_change),
        category=DiagnosticCategory.PERFORMANCE_CHANGE,
        observation=_observation(
            currency,
            current_period,
            baseline_period,
            current_sales,
            baseline_sales,
            change,
        ),
        confidence=ConfidenceLevel.MEDIUM,
        priority=Priority.MEDIUM,
        comparison_period=comparison,
        evidence=(
            EvidenceItem(
                metric="recognized_sales",
                current_value=_round(current_sales),
                baseline_value=_round(baseline_sales),
                absolute_change=_round(change),
                percent_change=_round_optional(percent_change),
                unit=currency,
                provenance="canonical_sales.recognized_sales grouped by recognition month",
            ),
            EvidenceItem(
                metric="completed_orders",
                current_value=float(current_orders),
                baseline_value=float(baseline_orders),
                absolute_change=float(current_orders - baseline_orders),
                percent_change=_round_optional(_percent_change(current_orders, baseline_orders)),
                unit="orders",
                provenance="canonical_sales.order_id with positive recognized sales",
            ),
            EvidenceItem(
                metric="average_order_value",
                current_value=_round(current_aov),
                baseline_value=_round(baseline_aov),
                absolute_change=_round(current_aov - baseline_aov),
                percent_change=_round_optional(_percent_change(current_aov, baseline_aov)),
                unit=currency,
                provenance="recognized sales divided by completed orders",
            ),
        ),
        contributors=(
            Contributor(
                factor="completed_orders",
                contribution_value=_round(order_contribution),
                unit=currency,
                explanation="Symmetric contribution of the completed-order change.",
                share_of_change_percent=_round_optional(
                    _share_of_change(order_contribution, change)
                ),
            ),
            Contributor(
                factor="average_order_value",
                contribution_value=_round(aov_contribution),
                unit=currency,
                explanation="Symmetric contribution of the average-order-value change.",
                share_of_change_percent=_round_optional(_share_of_change(aov_contribution, change)),
            ),
        ),
        limitations=tuple(limitations),
    )
    return DiagnosticReport(
        contract_version=CONTRACT_VERSION,
        currency=currency,
        insights=(insight,),
    )


def _require_columns(canonical_data: pd.DataFrame) -> None:
    missing = sorted(REQUIRED_COLUMNS - set(canonical_data.columns))
    if missing:
        raise ValueError("Canonical data is missing required columns: " + ", ".join(missing))
    if canonical_data.empty:
        raise ValueError("Canonical data contains no rows")


def _single_currency(canonical_data: pd.DataFrame) -> str:
    currencies = sorted(str(value) for value in canonical_data["currency"].dropna().unique())
    if len(currencies) != 1:
        raise ValueError("Diagnostic comparison requires exactly one currency")
    return currencies[0]


def monthly_recognized_sales_metrics(canonical_data: pd.DataFrame) -> pd.DataFrame:
    dates = canonical_data[
        "recognition_date" if "recognition_date" in canonical_data.columns else "order_date"
    ]
    periods = pd.to_datetime(dates, errors="raise").dt.to_period("M")
    sales = _recognized_sales(canonical_data)
    accepted = canonical_data.assign(_period=periods, _recognized_sales=sales).loc[sales > 0]
    if accepted.empty:
        return pd.DataFrame(columns=["recognized_sales", "completed_orders"])
    monthly = accepted.groupby("_period", sort=True).agg(
        recognized_sales=("_recognized_sales", "sum"),
        completed_orders=("order_id", "nunique"),
    )
    return monthly.astype({"recognized_sales": float, "completed_orders": int})


def _recognized_sales(canonical_data: pd.DataFrame) -> pd.Series:
    """Use explicit recognized sales when available; otherwise use positive revenue only."""
    source = (
        canonical_data["recognized_sales"]
        if "recognized_sales" in canonical_data.columns
        else canonical_data["revenue"]
    )
    values = pd.to_numeric(source, errors="raise").astype(float)
    return values.clip(lower=0)


def _complete_months(
    monthly: pd.DataFrame,
    latest_period_complete: bool,
) -> tuple[list[pd.Period], tuple[Limitation, ...]]:
    periods = list(monthly.index)
    limitations: tuple[Limitation, ...] = ()
    if not latest_period_complete and periods:
        excluded = periods.pop()
        limitations = (
            Limitation(
                code="latest_period_excluded",
                message=f"{excluded} was excluded because it is incomplete.",
            ),
        )
    return periods, limitations


def _comparison_unavailable_reason(periods: list[pd.Period]) -> tuple[str, str] | None:
    if len(periods) < 2:
        return (
            "insufficient_complete_periods",
            "Revenue comparison requires at least two complete months with completed orders.",
        )
    baseline, current = periods[-2:]
    if current != baseline + 1:
        return (
            "non_contiguous_periods",
            "Revenue comparison requires two consecutive complete months; missing months are not "
            "assumed to be zero sales.",
        )
    return None


def _percent_change(current: float, baseline: float) -> float | None:
    if baseline == 0:
        return None
    return (current - baseline) / abs(baseline) * 100


def _share_of_change(contribution: float, total_change: float) -> float | None:
    if total_change == 0:
        return None
    return contribution / total_change * 100


def _change_title(change: float, percent_change: float | None) -> str:
    if change == 0:
        return "Recognized sales were unchanged"
    direction = "increased" if change > 0 else "decreased"
    if percent_change is None:
        return f"Recognized sales {direction}"
    return f"Recognized sales {direction} by {abs(percent_change):.1f}%"


def _observation(
    currency: str,
    current_period: pd.Period,
    baseline_period: pd.Period,
    current_sales: float,
    baseline_sales: float,
    change: float,
) -> str:
    direction = "increased" if change > 0 else "decreased" if change < 0 else "were unchanged"
    if change == 0:
        return (
            f"Recognized sales were {currency} {_round(current_sales):,.2f} in both "
            f"{baseline_period} and {current_period}."
        )
    return (
        f"Recognized sales {direction} from {currency} {_round(baseline_sales):,.2f} in "
        f"{baseline_period} to {currency} {_round(current_sales):,.2f} in {current_period}."
    )


def _round(value: float) -> float:
    return round(value, 2)


def _round_optional(value: float | None) -> float | None:
    return None if value is None else _round(value)
