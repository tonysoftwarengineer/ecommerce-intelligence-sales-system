"""Local-only evaluation of the frozen product-demand preview policy.

This module deliberately reuses the generic CSV validation/transformation path
and the existing product-demand domain service.  It adds future holdout scoring
and privacy-safe reporting; it does not introduce another forecasting model.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from src.generic_sales.contracts import (
    DiscountScope,
    DiscountType,
    NegativeRevenuePolicy,
    OrderDiscountAllocation,
    RefundTaxTreatment,
    RevenueMismatchPolicy,
    RevenueMode,
    SalesProcessingConfig,
    StandardOrderStatus,
    StandardPaymentStatus,
)
from src.generic_sales.data_quality import assess_data_quality
from src.generic_sales.transformation import (
    QuarantineConfirmationRequired,
    TransformationBlockedError,
    transform_sales_data,
)
from src.generic_sales.validation import validate_sales_data
from src.product_demand.baselines import BaselineUnavailableError, forecast_baseline
from src.product_demand.calendar import build_product_demand_calendar
from src.product_demand.category_fallback import prepare_category_fallback_candidates
from src.product_demand.contracts import ProductDemandAssumptions, ProductIdentitySource
from src.product_demand.evaluation_contracts import EvaluationSeries
from src.product_demand.evaluation_series import prepare_evaluation_series
from src.product_demand.service import analyze_product_demand
from src.product_demand.trust_policy import MINIMUM_PREVIEW_FOLDS, ProductDemandTrustDecision
from src.schema_mapping import validate_schema_mapping

HOLDOUT_WEEKS = 13
HOLDOUT_DAYS = HOLDOUT_WEEKS * 7


class IndependentEvaluationConfigError(ValueError):
    """A local evaluation configuration is incomplete or unsafe."""


@dataclass(frozen=True)
class IndependentEvaluationConfig:
    """Confirmed business semantics required for local external evaluation."""

    mapping: Mapping[str, str]
    processing: SalesProcessingConfig
    confirm_quarantine: bool
    product_demand: ProductDemandAssumptions


def load_independent_evaluation_config(path: Path) -> IndependentEvaluationConfig:
    """Load a local JSON configuration without reading or persisting source data."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise IndependentEvaluationConfigError(f"Could not read configuration: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise IndependentEvaluationConfigError(
            f"Configuration is not valid JSON: {exc.msg}"
        ) from exc
    if not isinstance(payload, dict):
        raise IndependentEvaluationConfigError("Configuration root must be a JSON object.")
    return independent_evaluation_config_from_dict(payload)


def independent_evaluation_config_from_dict(
    payload: Mapping[str, Any],
) -> IndependentEvaluationConfig:
    """Parse the documented local config into the same domain contracts as the API."""
    required = {
        "mapping",
        "revenue_mode",
        "negative_revenue_policy",
        "date_format",
        "currency",
        "assume_all_completed",
        "confirm_quarantine",
        "product_demand",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise IndependentEvaluationConfigError(
            "Configuration is missing required fields: " + ", ".join(missing)
        )

    mapping = _string_mapping(payload["mapping"], "mapping")
    try:
        processing = SalesProcessingConfig(
            revenue_mode=RevenueMode(_text(payload["revenue_mode"], "revenue_mode")),
            negative_revenue_policy=NegativeRevenuePolicy(
                _text(payload["negative_revenue_policy"], "negative_revenue_policy")
            ),
            date_format=_text(payload["date_format"], "date_format"),
            currency=_text(payload["currency"], "currency"),
            assume_all_completed=_bool(payload["assume_all_completed"], "assume_all_completed"),
            status_mapping={
                source: StandardOrderStatus(target)
                for source, target in _string_mapping(
                    payload.get("status_mapping", {}), "status_mapping"
                ).items()
            },
            payment_status_mapping={
                source: StandardPaymentStatus(target)
                for source, target in _string_mapping(
                    payload.get("payment_status_mapping", {}), "payment_status_mapping"
                ).items()
            },
            discount_type=DiscountType(
                _text(payload.get("discount_type", "none"), "discount_type")
            ),
            discount_scope=DiscountScope(
                _text(payload.get("discount_scope", "per_line"), "discount_scope")
            ),
            order_discount_allocation=OrderDiscountAllocation(
                _text(
                    payload.get("order_discount_allocation", "unallocated"),
                    "order_discount_allocation",
                )
            ),
            revenue_mismatch_policy=RevenueMismatchPolicy(
                _text(payload.get("revenue_mismatch_policy", "warn"), "revenue_mismatch_policy")
            ),
            mismatch_tolerance=Decimal(str(payload.get("mismatch_tolerance", "0.01"))),
            refund_tax_treatment=(
                RefundTaxTreatment(_text(payload["refund_tax_treatment"], "refund_tax_treatment"))
                if payload.get("refund_tax_treatment") is not None
                else None
            ),
        )
    except (ValueError, ArithmeticError) as exc:
        raise IndependentEvaluationConfigError(str(exc)) from exc

    return IndependentEvaluationConfig(
        mapping=mapping,
        processing=processing,
        confirm_quarantine=_bool(payload["confirm_quarantine"], "confirm_quarantine"),
        product_demand=_product_demand_assumptions(payload["product_demand"]),
    )


def run_independent_evaluation(
    source_data: pd.DataFrame,
    config: IndependentEvaluationConfig,
) -> dict[str, object]:
    """Evaluate frozen previews against the final unseen business history.

    The returned detailed report is local-only because it contains product keys
    and dates.  Use :func:`sanitize_independent_evaluation` before publishing.
    """
    mapping_check = validate_schema_mapping(
        list(source_data.columns), config.mapping, config.processing.revenue_mode
    )
    if not mapping_check["valid"]:
        raise IndependentEvaluationConfigError("; ".join(mapping_check["errors"]))

    validation = validate_sales_data(source_data, config.mapping, config.processing)
    quality = assess_data_quality(validation, config.mapping, config.processing.date_format)
    report: dict[str, object] = {
        "scope": (
            "Independent-business future-time holdout of the frozen limited-preview policy. "
            "It does not approve supported weekly use."
        ),
        "configuration": {
            "forecast_horizon_days": 7,
            "holdout_weeks": HOLDOUT_WEEKS,
            "minimum_preview_test_weeks": MINIMUM_PREVIEW_FOLDS,
            "benchmark": "zero",
            "supported_weekly_approved": False,
        },
        "input_quality": {
            "source_rows": validation.total_rows,
            "valid_rows": validation.valid_rows,
            "quarantined_rows": validation.invalid_rows,
            "blocking_errors": list(validation.blocking_errors),
            "warning_count": len(validation.warnings),
            "data_quality_status": quality.status.value,
            "decision_ready": quality.decision_ready,
        },
    }
    if not validation.can_transform:
        report["outcome"] = _inconclusive("Source data cannot be transformed safely.")
        report["products"] = _empty_scope_summary()
        report["categories"] = _empty_scope_summary()
        return report
    if validation.requires_confirmation and not config.confirm_quarantine:
        report["outcome"] = _inconclusive(
            "Invalid rows require explicit quarantine confirmation before evaluation."
        )
        report["products"] = _empty_scope_summary()
        report["categories"] = _empty_scope_summary()
        return report
    if not quality.decision_ready:
        report["outcome"] = _inconclusive(
            "Source data is preview-only or blocked, so product-demand evaluation is withheld."
        )
        report["products"] = _empty_scope_summary()
        report["categories"] = _empty_scope_summary()
        return report

    try:
        transformed = transform_sales_data(
            source_data,
            config.mapping,
            config.processing,
            validation,
            config.confirm_quarantine,
        )
    except (QuarantineConfirmationRequired, TransformationBlockedError) as exc:
        report["outcome"] = _inconclusive(str(exc))
        report["products"] = _empty_scope_summary()
        report["categories"] = _empty_scope_summary()
        return report

    canonical = transformed.canonical_data
    input_quality = _mapping(report["input_quality"], "input_quality")
    report["input_quality"] = {
        **input_quality,
        "canonical_rows": len(canonical),
        "transformation_warning_count": len(transformed.warnings),
    }
    if canonical.empty:
        report["outcome"] = _inconclusive("No canonical rows remain after transformation.")
        report["products"] = _empty_scope_summary()
        report["categories"] = _empty_scope_summary()
        return report

    evaluation = _evaluate_canonical(canonical, config)
    report.update(evaluation)
    return report


def sanitize_independent_evaluation(report: Mapping[str, object]) -> dict[str, object]:
    """Create a publishable aggregate report without business identifiers or dates."""
    input_quality = _mapping(report.get("input_quality"), "input_quality")
    products = _mapping(report.get("products"), "products")
    categories = _mapping(report.get("categories"), "categories")
    return {
        "scope": report.get("scope"),
        "privacy": {
            "raw_csv_retained": False,
            "product_identifiers_retained": False,
            "customer_identifiers_retained": False,
            "prices_retained": False,
            "calendar_dates_retained": False,
        },
        "configuration": report.get("configuration"),
        "input_quality": {
            key: input_quality[key]
            for key in (
                "source_rows",
                "valid_rows",
                "quarantined_rows",
                "warning_count",
                "data_quality_status",
                "decision_ready",
                "canonical_rows",
                "transformation_warning_count",
            )
            if key in input_quality
        },
        "outcome": report.get("outcome"),
        "products": _sanitized_scope_summary(products),
        "categories": _sanitized_scope_summary(categories),
    }


def render_independent_evaluation_markdown(report: Mapping[str, object]) -> str:
    """Render only the sanitized aggregate report for a repository document."""
    sanitized = sanitize_independent_evaluation(report)
    outcome = _mapping(sanitized.get("outcome"), "outcome")
    lines = [
        "# Independent-Business Product-Demand Evaluation",
        "",
        "## Result",
        "",
        f"- Classification: `{outcome.get('classification', 'inconclusive')}`",
        f"- Interpretation: {outcome.get('message', 'No evaluation result was produced.')}",
        "- Supported weekly use: **not approved**",
        "",
        "## Aggregate evidence",
        "",
    ]
    for title, key in (("Products", "products"), ("Category fallback", "categories")):
        summary = _mapping(sanitized.get(key), key)
        lines.extend(
            [
                f"### {title}",
                "",
                f"- Scopes assessed: {summary.get('assessed_scope_count', 0)}",
                f"- Scopes skipped: {summary.get('skipped_scope_count', 0)}",
                f"- Preview coverage: {summary.get('coverage_percent', 0.0)}%",
                f"- Forecast opportunities: {summary.get('forecast_opportunities', 0)}",
                f"- Previewed opportunities: {summary.get('previews_shown', 0)}",
                f"- Abstentions: {summary.get('abstentions', 0)}",
            ]
        )
        metrics = summary.get("metrics_on_shown_previews")
        if isinstance(metrics, Mapping):
            lines.extend(
                [
                    f"- Skill versus zero: {metrics.get('skill_vs_zero')}",
                    f"- WAPE: {metrics.get('wape')}",
                    f"- MAE: {metrics.get('mean_absolute_error_units')}",
                    f"- Overforecast units: {metrics.get('overforecast_units')}",
                    f"- Underforecast units: {metrics.get('underforecast_units')}",
                ]
            )
        lines.append("")
    lines.extend(
        [
            "## Privacy",
            "",
            "This document contains only aggregate counts and metrics. The raw business CSV, "
            "mapping configuration, product identifiers, prices, and calendar dates remain local.",
            "",
        ]
    )
    return "\n".join(lines)


def _evaluate_canonical(
    canonical: pd.DataFrame,
    config: IndependentEvaluationConfig,
) -> dict[str, object]:
    dates = pd.to_datetime(canonical["order_date"], errors="coerce")
    if dates.isna().any():
        return {
            "outcome": _inconclusive("Canonical order dates could not be prepared for holdout."),
            "products": _empty_scope_summary(),
            "categories": _empty_scope_summary(),
        }
    holdout_end = dates.max().date()
    holdout_start = holdout_end - timedelta(days=HOLDOUT_DAYS - 1)
    historical = canonical.loc[dates.dt.date < holdout_start].copy()
    if historical.empty:
        return {
            "outcome": _inconclusive(
                "The export has no history before the required 13-week holdout."
            ),
            "products": _empty_scope_summary(),
            "categories": _empty_scope_summary(),
        }

    initial = analyze_product_demand(
        historical,
        config.processing.revenue_mode,
        config.product_demand,
    )
    full_calendar = build_product_demand_calendar(
        canonical,
        config.processing.revenue_mode,
        config.product_demand,
    )
    series_by_key = {
        series.product_key: series for series in prepare_evaluation_series(full_calendar.calendar)
    }
    product_scopes = [
        _score_scope(
            scope_type="product",
            scope_key=item.readiness.product_key,
            series=series_by_key.get(item.readiness.product_key),
            trust=item.trust,
            holdout_start=holdout_start,
            holdout_end=holdout_end,
        )
        for item in initial.products
    ]

    preview_product_keys = frozenset(
        item.readiness.product_key
        for item in initial.products
        if item.trust.numeric_forecast_allowed
    )
    full_categories = prepare_category_fallback_candidates(
        canonical,
        full_calendar.calendar,
        full_calendar.readiness,
        frozenset(),
        config.product_demand,
    )
    category_series = {item.category_key: item.series for item in full_categories.candidates}
    category_scopes = [
        _score_scope(
            scope_type="category",
            scope_key=item.category_key,
            series=category_series.get(item.category_key),
            trust=item.trust,
            holdout_start=holdout_start,
            holdout_end=holdout_end,
            extra_reasons=item.reason_codes,
        )
        for item in initial.categories
    ]
    product_summary = _scope_summary(product_scopes)
    category_summary = _scope_summary(category_scopes)
    return {
        "holdout": {
            "start_date": holdout_start.isoformat(),
            "end_date": holdout_end.isoformat(),
            "weeks": HOLDOUT_WEEKS,
            "historical_canonical_rows": len(historical),
        },
        "products": product_summary,
        "categories": category_summary,
        "outcome": _outcome_for(product_summary, category_summary),
        "category_dataset_reason_codes": [
            reason.value for reason in full_categories.dataset_reason_codes
        ],
        "initial_preview_product_count": len(preview_product_keys),
    }


def _score_scope(
    *,
    scope_type: str,
    scope_key: str,
    series: EvaluationSeries | None,
    trust: ProductDemandTrustDecision | None,
    holdout_start: date,
    holdout_end: date,
    extra_reasons: tuple[object, ...] = (),
) -> dict[str, object]:
    reasons = [str(getattr(reason, "value", reason)) for reason in extra_reasons]
    if trust is None:
        return _skipped_scope(scope_type, scope_key, "scope_unavailable", reasons)
    reasons.extend(reason.value for reason in trust.policy_reasons)
    reasons.extend(reason.value for reason in trust.data_reason_codes)
    if series is None:
        return _skipped_scope(scope_type, scope_key, "full_holdout_series_unavailable", reasons)
    holdout = tuple(point for point in series.points if holdout_start <= point.date <= holdout_end)
    if len(holdout) != HOLDOUT_DAYS or any(not point.included for point in holdout):
        return _skipped_scope(scope_type, scope_key, "incomplete_or_unknown_holdout", reasons)
    history = tuple(point for point in series.points if point.date < holdout_start)
    if not history:
        return _skipped_scope(scope_type, scope_key, "insufficient_history_before_holdout", reasons)

    candidate = trust.selected_candidate if trust.numeric_forecast_allowed else None
    outcomes: list[dict[str, object]] = []
    for index in range(HOLDOUT_WEEKS):
        actual_points = holdout[index * 7 : (index + 1) * 7]
        actual_total = sum(
            (point.target_units or Decimal("0") for point in actual_points),
            Decimal("0"),
        )
        if candidate is None:
            outcomes.append(
                {
                    "week": index + 1,
                    "status": "abstained",
                    "actual_total_units": str(actual_total),
                    "reason_codes": sorted(set(reasons)) or ["preview_policy_not_met"],
                }
            )
            continue
        training = EvaluationSeries(
            product_key=series.product_key,
            unit_of_measure=series.unit_of_measure,
            points=(*history, *holdout[: index * 7]),
        )
        try:
            forecast = forecast_baseline(training, candidate)
        except BaselineUnavailableError as exc:
            outcomes.append(
                {
                    "week": index + 1,
                    "status": "abstained",
                    "actual_total_units": str(actual_total),
                    "reason_codes": [exc.reason.value],
                }
            )
            continue
        outcomes.append(
            {
                "week": index + 1,
                "status": "preview_shown",
                "actual_total_units": str(actual_total),
                "predicted_total_units": str(forecast.predicted_total_units),
                "selected_candidate": candidate.value,
                "forecast_dates": [item.isoformat() for item in forecast.forecast_dates],
            }
        )
    return {
        "scope_type": scope_type,
        "scope_key": scope_key,
        "status": "assessed",
        "initial_trust_state": trust.state.value,
        "selected_candidate": candidate.value if candidate is not None else None,
        "outcomes": outcomes,
    }


def _scope_summary(scopes: list[dict[str, object]]) -> dict[str, object]:
    assessed = [scope for scope in scopes if scope["status"] == "assessed"]
    skipped = [scope for scope in scopes if scope["status"] == "skipped"]
    outcomes = [
        outcome
        for scope in assessed
        for outcome in _list_of_mappings(scope.get("outcomes"), "outcomes")
    ]
    previews = [outcome for outcome in outcomes if outcome["status"] == "preview_shown"]
    abstention_reasons = Counter(
        str(reason)
        for outcome in outcomes
        if outcome["status"] == "abstained"
        for reason in _list(outcome.get("reason_codes"))
    )
    skipped_reasons = Counter(str(scope.get("skip_reason")) for scope in skipped)
    summary: dict[str, object] = {
        "scope_count": len(scopes),
        "assessed_scope_count": len(assessed),
        "skipped_scope_count": len(skipped),
        "skipped_reason_counts": dict(sorted(skipped_reasons.items())),
        "forecast_opportunities": len(outcomes),
        "previews_shown": len(previews),
        "abstentions": len(outcomes) - len(previews),
        "coverage_percent": _percent(len(previews), len(outcomes)),
        "abstention_reason_counts": dict(sorted(abstention_reasons.items())),
        "metrics_on_shown_previews": _preview_metrics(previews),
        "scopes": scopes,
    }
    return summary


def _preview_metrics(previews: list[Mapping[str, object]]) -> dict[str, object] | None:
    if not previews:
        return None
    actuals = [Decimal(str(item["actual_total_units"])) for item in previews]
    predictions = [Decimal(str(item["predicted_total_units"])) for item in previews]
    absolute_errors = [abs(prediction - actual) for prediction, actual in zip(predictions, actuals)]
    actual_total = sum(actuals, Decimal("0"))
    model_mae = sum(absolute_errors, Decimal("0")) / Decimal(len(absolute_errors))
    zero_mae = actual_total / Decimal(len(actuals))
    skill = None if zero_mae == 0 else (zero_mae - model_mae) / zero_mae
    bias = sum(
        (prediction - actual for prediction, actual in zip(predictions, actuals)), Decimal("0")
    )
    over = sum(
        (
            max(prediction - actual, Decimal("0"))
            for prediction, actual in zip(predictions, actuals)
        ),
        Decimal("0"),
    )
    under = sum(
        (
            max(actual - prediction, Decimal("0"))
            for prediction, actual in zip(predictions, actuals)
        ),
        Decimal("0"),
    )
    return {
        "mean_absolute_error_units": str(model_mae),
        "zero_mean_absolute_error_units": str(zero_mae),
        "skill_vs_zero": str(skill) if skill is not None else None,
        "wape": str(sum(absolute_errors, Decimal("0")) / actual_total) if actual_total else None,
        "mean_bias_units": str(bias / Decimal(len(actuals))),
        "actual_total_units": str(actual_total),
        "overforecast_units": str(over),
        "underforecast_units": str(under),
        "overforecast_count": sum(
            prediction > actual for prediction, actual in zip(predictions, actuals)
        ),
        "underforecast_count": sum(
            prediction < actual for prediction, actual in zip(predictions, actuals)
        ),
        "exact_count": sum(
            prediction == actual for prediction, actual in zip(predictions, actuals)
        ),
    }


def _outcome_for(
    products: Mapping[str, object], categories: Mapping[str, object]
) -> dict[str, str]:
    product_state = _evidence_state(products)
    category_state = _evidence_state(categories)
    if product_state == "consistent_external_evidence":
        message = (
            "Shown product previews beat zero on this independent business holdout. "
            "They remain preview-only."
        )
    elif product_state == "observed_limitation":
        message = (
            "Shown product previews did not beat zero on this independent business holdout. "
            "The existing policy remains unchanged and the limitation must be recorded."
        )
    else:
        message = "No comparable product previews were available; this checkpoint is inconclusive."
    return {
        "classification": product_state,
        "product_evidence_state": product_state,
        "category_evidence_state": category_state,
        "message": message,
        "supported_weekly_approved": "false",
    }


def _evidence_state(summary: Mapping[str, object]) -> str:
    metrics = summary.get("metrics_on_shown_previews")
    if not isinstance(metrics, Mapping) or metrics.get("skill_vs_zero") is None:
        return "inconclusive"
    return (
        "consistent_external_evidence"
        if Decimal(str(metrics["skill_vs_zero"])) > 0
        else "observed_limitation"
    )


def _sanitized_scope_summary(summary: Mapping[str, object]) -> dict[str, object]:
    return {
        key: summary[key]
        for key in (
            "scope_count",
            "assessed_scope_count",
            "skipped_scope_count",
            "skipped_reason_counts",
            "forecast_opportunities",
            "previews_shown",
            "abstentions",
            "coverage_percent",
            "abstention_reason_counts",
            "metrics_on_shown_previews",
        )
        if key in summary
    }


def _empty_scope_summary() -> dict[str, object]:
    return {
        "scope_count": 0,
        "assessed_scope_count": 0,
        "skipped_scope_count": 0,
        "skipped_reason_counts": {},
        "forecast_opportunities": 0,
        "previews_shown": 0,
        "abstentions": 0,
        "coverage_percent": 0.0,
        "abstention_reason_counts": {},
        "metrics_on_shown_previews": None,
        "scopes": [],
    }


def _inconclusive(message: str) -> dict[str, str]:
    return {
        "classification": "inconclusive",
        "product_evidence_state": "inconclusive",
        "category_evidence_state": "inconclusive",
        "message": message,
        "supported_weekly_approved": "false",
    }


def _skipped_scope(
    scope_type: str,
    scope_key: str,
    reason: str,
    reasons: list[str],
) -> dict[str, object]:
    return {
        "scope_type": scope_type,
        "scope_key": scope_key,
        "status": "skipped",
        "skip_reason": reason,
        "reason_codes": sorted(set(reasons)),
        "outcomes": [],
    }


def _product_demand_assumptions(value: object) -> ProductDemandAssumptions:
    payload = _mapping(value, "product_demand")
    stockout_dates: dict[str, frozenset[date]] = {}
    stockouts = payload.get("stockout_dates", [])
    if not isinstance(stockouts, list):
        raise IndependentEvaluationConfigError("product_demand.stockout_dates must be a list.")
    for position, stockout in enumerate(stockouts):
        item = _mapping(stockout, f"product_demand.stockout_dates[{position}]")
        source = ProductIdentitySource(
            _text(item.get("identity_source"), "stockout identity_source")
        )
        identity = _text(item.get("identity_value"), "stockout identity_value")
        prefix = "id" if source is ProductIdentitySource.PRODUCT_ID else "name"
        dates = _dates(item.get("dates"), "stockout dates")
        stockout_dates[f"{prefix}:{identity}"] = frozenset(dates)
    return ProductDemandAssumptions(
        default_unit_of_measure=_optional_text(
            payload.get("default_unit_of_measure"), "default_unit_of_measure"
        ),
        confirm_product_names_unique=_bool(
            payload.get("confirm_product_names_unique", False), "confirm_product_names_unique"
        ),
        confirm_product_categories=_bool(
            payload.get("confirm_product_categories", False), "confirm_product_categories"
        ),
        export_covers_all_open_days=_bool(
            payload.get("export_covers_all_open_days", False), "export_covers_all_open_days"
        ),
        stockout_tracking_complete=_bool(
            payload.get("stockout_tracking_complete", False), "stockout_tracking_complete"
        ),
        business_closed_dates=frozenset(
            _dates(payload.get("business_closed_dates", []), "business_closed_dates")
        ),
        stockout_dates=stockout_dates,
    )


def _string_mapping(value: object, field: str) -> dict[str, str]:
    mapping = _mapping(value, field)
    return {
        _text(key, f"{field} key"): _text(item, f"{field}[{key!r}]")
        for key, item in mapping.items()
    }


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise IndependentEvaluationConfigError(f"{field} must be an object.")
    return value


def _list_of_mappings(value: object, field: str) -> list[Mapping[str, object]]:
    return [_mapping(item, field) for item in _list(value)]


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _dates(value: object, field: str) -> tuple[date, ...]:
    if not isinstance(value, list):
        raise IndependentEvaluationConfigError(f"{field} must be a list of ISO dates.")
    parsed: list[date] = []
    for item in value:
        try:
            parsed.append(date.fromisoformat(_text(item, field)))
        except ValueError as exc:
            raise IndependentEvaluationConfigError(f"{field} must contain ISO dates.") from exc
    return tuple(parsed)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IndependentEvaluationConfigError(f"{field} must be a non-empty string.")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise IndependentEvaluationConfigError(f"{field} must be true or false.")
    return value


def _percent(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 1) if denominator else 0.0
