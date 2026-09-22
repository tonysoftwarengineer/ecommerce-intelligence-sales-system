from typing import Any, Optional

import pandas as pd

from src.diagnostics.reporting import build_diagnostic_sections, unavailable_diagnostic_sections
from src.generic_sales.analytics import analyze_canonical_sales
from src.generic_sales.forecasting import forecast_generic_revenue, unavailable_forecast


def build_generic_sales_report(
    canonical_data: pd.DataFrame,
    latest_period_complete: bool,
    mapped_fields: Optional[set[str]] = None,
    *,
    decision_support_ready: bool = True,
    decision_support_reason: Optional[str] = None,
) -> dict[str, Any]:
    """Combine descriptive analytics and an evidence-labeled forecast."""
    analytics = analyze_canonical_sales(canonical_data, mapped_fields)
    analytics.pop("monthly_series")
    forecast_series = analytics.pop("forecast_series")
    excluded_adjustments = analytics.pop("forecast_excluded_adjustment_periods")
    if decision_support_ready:
        forecast = forecast_generic_revenue(forecast_series, latest_period_complete)
        if excluded_adjustments:
            forecast["limitations"].append(
                "Refund-only period(s) were excluded from forecast history: "
                + ", ".join(excluded_adjustments)
                + ". Revenue reporting still includes them."
            )
        diagnostics = build_diagnostic_sections(canonical_data, latest_period_complete)
    else:
        reason = decision_support_reason or (
            "Data quality is insufficient for decision-support calculations."
        )
        limitation = (
            "Forecast was not calculated because this is a preview-only analysis. " + reason
        )
        forecast = unavailable_forecast(len(forecast_series), [limitation])
        forecast["trust_message"] = limitation
        diagnostics = unavailable_diagnostic_sections(
            "insufficient_data_quality",
            "Diagnostics and recommendations were not calculated because this is a "
            f"preview-only analysis. {reason}",
        )
    analytics["capabilities"]["forecasting"] = forecast["status"] != "unavailable"
    analytics["forecast"] = forecast
    analytics["diagnostics"] = diagnostics
    return analytics


def build_generic_sales_reports(
    canonical_data: pd.DataFrame,
    latest_period_complete: bool,
    mapped_fields: Optional[set[str]] = None,
    *,
    decision_support_ready: bool = True,
    decision_support_reason: Optional[str] = None,
) -> dict[str, dict[str, Any]]:
    """Build one independent report per currency; never sum unlike money."""
    reports = {}
    for currency, currency_data in canonical_data.groupby("currency", sort=True):
        reports[str(currency)] = build_generic_sales_report(
            currency_data.reset_index(drop=True),
            latest_period_complete,
            mapped_fields,
            decision_support_ready=decision_support_ready,
            decision_support_reason=decision_support_reason,
        )
    return reports
