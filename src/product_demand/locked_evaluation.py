"""Frozen-policy evaluation on disjoint products and temporally held-out weeks."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from src.product_demand.baselines import BaselineUnavailableError, forecast_baseline
from src.product_demand.contracts import (
    ProductDemandAvailability,
    ProductDemandProductReadiness,
    ProductIdentitySource,
)
from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    EvaluationConfiguration,
    EvaluationSeries,
)
from src.product_demand.metrics import evaluate_product_baselines
from src.product_demand.public_data_evaluation import PublicDatasetPreparation
from src.product_demand.trust_gate import assess_weekly_zero_skill
from src.product_demand.trust_policy import (
    MINIMUM_PREVIEW_FOLDS,
    assess_product_demand_trust,
)


class LockedOutcomeStatus(str, Enum):
    PREVIEW_SHOWN = "preview_shown"
    ABSTAINED = "abstained"


class LockedGateStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class LockedOriginOutcome:
    product_key: str
    source_id: str
    stratum: str
    holdout_week: int
    training_end: date
    forecast_dates: tuple[date, ...]
    actual_total_units: Decimal
    status: LockedOutcomeStatus
    selected_candidate: BaselineCandidate | None
    predicted_total_units: Decimal | None
    historical_skill_vs_zero: Decimal | None
    policy_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.product_key.strip() or not self.source_id.strip() or not self.stratum.strip():
            raise ValueError("Locked outcomes require product and stratum identity")
        if self.holdout_week <= 0 or len(self.forecast_dates) != 7:
            raise ValueError("Locked outcomes require one positive seven-day holdout week")
        if self.actual_total_units < 0:
            raise ValueError("Locked actual demand must not be negative")
        if self.status is LockedOutcomeStatus.PREVIEW_SHOWN:
            if self.selected_candidate is None or self.predicted_total_units is None:
                raise ValueError("Shown previews require a selected method and prediction")
            if self.predicted_total_units < 0 or self.policy_reasons:
                raise ValueError("Shown previews require a safe nonnegative prediction")
        elif self.predicted_total_units is not None or not self.policy_reasons:
            raise ValueError("Abstentions require policy reasons and no prediction")


@dataclass(frozen=True)
class LockedSkippedProduct:
    product_key: str
    source_id: str
    stratum: str
    reason: str


@dataclass(frozen=True)
class LockedEvaluationResult:
    dataset_name: str
    development_source_ids: tuple[str, ...]
    locked_source_ids: tuple[str, ...]
    holdout_weeks: int
    minimum_preview_folds: int
    outcomes: tuple[LockedOriginOutcome, ...]
    skipped_products: tuple[LockedSkippedProduct, ...]

    def __post_init__(self) -> None:
        if not self.dataset_name.strip():
            raise ValueError("Locked evaluation requires a dataset name")
        if self.holdout_weeks <= 0 or self.minimum_preview_folds <= 0:
            raise ValueError("Locked evaluation counts must be positive")
        development = tuple(self.development_source_ids)
        locked = tuple(self.locked_source_ids)
        if len(development) != len(set(development)) or len(locked) != len(set(locked)):
            raise ValueError("Locked and development source IDs must be unique")
        if set(development).intersection(locked):
            raise ValueError("Locked products must be disjoint from development products")
        if not locked:
            raise ValueError("Locked evaluation requires at least one locked product")


def evaluate_locked_holdout(
    preparation: PublicDatasetPreparation,
    development_source_ids: tuple[str, ...],
    *,
    holdout_weeks: int = 13,
    minimum_preview_folds: int = MINIMUM_PREVIEW_FOLDS,
) -> LockedEvaluationResult:
    """Simulate weekly use without exposing each next seven-day actual to the model."""
    if holdout_weeks <= 0 or minimum_preview_folds <= 0:
        raise ValueError("Locked evaluation counts must be positive")
    if set(development_source_ids).intersection(preparation.selected_source_ids):
        raise ValueError("Locked preparation overlaps the development cohort")

    profiles = {profile.product_key: profile for profile in preparation.profiles}
    outcomes: list[LockedOriginOutcome] = []
    skipped: list[LockedSkippedProduct] = []
    holdout_days = holdout_weeks * 7
    evaluation_configuration = EvaluationConfiguration()

    for series in preparation.series:
        profile = profiles[series.product_key]
        if len(series.points) <= holdout_days:
            skipped.append(
                LockedSkippedProduct(
                    product_key=series.product_key,
                    source_id=profile.source_id,
                    stratum=profile.stratum,
                    reason="insufficient_history_before_locked_holdout",
                )
            )
            continue
        holdout_start = len(series.points) - holdout_days
        if any(
            not point.included or point.target_units is None
            for point in series.points[holdout_start:]
        ):
            skipped.append(
                LockedSkippedProduct(
                    product_key=series.product_key,
                    source_id=profile.source_id,
                    stratum=profile.stratum,
                    reason="locked_holdout_contains_unknown_targets",
                )
            )
            continue

        readiness = ProductDemandProductReadiness(
            product_key=series.product_key,
            product_id=profile.source_id,
            product_name=None,
            identity_source=ProductIdentitySource.PRODUCT_ID,
            unit_of_measure=series.unit_of_measure,
            status=ProductDemandAvailability.READY,
            reason_codes=(),
            explanations=(),
        )
        initial_training = EvaluationSeries(
            product_key=series.product_key,
            unit_of_measure=series.unit_of_measure,
            points=series.points[:holdout_start],
        )
        evaluation = evaluate_product_baselines(initial_training, evaluation_configuration)
        zero_skill = assess_weekly_zero_skill(evaluation)
        trust = assess_product_demand_trust(
            readiness,
            evaluation,
            zero_skill,
            minimum_preview_folds,
        )
        selected_candidate = trust.selected_candidate if trust.numeric_forecast_allowed else None
        fixed_policy_reasons = tuple(reason.value for reason in trust.policy_reasons)

        for week_index in range(holdout_weeks):
            forecast_start = holdout_start + (week_index * 7)
            training = EvaluationSeries(
                product_key=series.product_key,
                unit_of_measure=series.unit_of_measure,
                points=series.points[:forecast_start],
            )
            actual_points = series.points[forecast_start : forecast_start + 7]
            actual_total = sum(
                (point.target_units for point in actual_points if point.target_units is not None),
                Decimal("0"),
            )
            forecast = None
            policy_reasons = fixed_policy_reasons
            if selected_candidate is not None:
                try:
                    forecast = forecast_baseline(training, selected_candidate)
                except BaselineUnavailableError:
                    policy_reasons = ("final_forecast_unavailable",)

            outcomes.append(
                LockedOriginOutcome(
                    product_key=series.product_key,
                    source_id=profile.source_id,
                    stratum=profile.stratum,
                    holdout_week=week_index + 1,
                    training_end=training.points[-1].date,
                    forecast_dates=tuple(point.date for point in actual_points),
                    actual_total_units=actual_total,
                    status=(
                        LockedOutcomeStatus.PREVIEW_SHOWN
                        if forecast is not None
                        else LockedOutcomeStatus.ABSTAINED
                    ),
                    selected_candidate=(forecast.candidate if forecast is not None else None),
                    predicted_total_units=(
                        forecast.predicted_total_units if forecast is not None else None
                    ),
                    historical_skill_vs_zero=trust.skill_vs_zero,
                    policy_reasons=policy_reasons,
                )
            )

    return LockedEvaluationResult(
        dataset_name=preparation.dataset_name,
        development_source_ids=tuple(sorted(development_source_ids)),
        locked_source_ids=tuple(sorted(preparation.selected_source_ids)),
        holdout_weeks=holdout_weeks,
        minimum_preview_folds=minimum_preview_folds,
        outcomes=tuple(outcomes),
        skipped_products=tuple(skipped),
    )


def locked_evaluation_to_dict(result: LockedEvaluationResult) -> dict[str, object]:
    """Serialize locked evidence without upgrading the preview release state."""
    strata = sorted(
        {
            *(outcome.stratum for outcome in result.outcomes),
            *(product.stratum for product in result.skipped_products),
        }
    )
    overall = _summarize_outcomes(result.outcomes)
    by_stratum = {
        stratum: _summarize_outcomes(
            tuple(outcome for outcome in result.outcomes if outcome.stratum == stratum)
        )
        for stratum in strata
    }
    gate_status, gate_reasons = _gate_status(overall, by_stratum)
    return {
        "scope": (
            "Locked within-source product and future-time holdout. This evaluates the frozen "
            "limited-preview policy; it does not approve supported weekly use."
        ),
        "dataset": result.dataset_name,
        "configuration": {
            "forecast_horizon_days": 7,
            "holdout_weeks_per_product": result.holdout_weeks,
            "minimum_preview_test_weeks": result.minimum_preview_folds,
            "benchmark": "zero",
        },
        "cohort": {
            "development_product_count": len(result.development_source_ids),
            "locked_product_count": len(result.locked_source_ids),
            "overlap_count": len(
                set(result.development_source_ids).intersection(result.locked_source_ids)
            ),
            "locked_source_ids": list(result.locked_source_ids),
            "skipped_products": [
                {
                    "source_id": product.source_id,
                    "stratum": product.stratum,
                    "reason": product.reason,
                }
                for product in result.skipped_products
            ],
        },
        "overall": overall,
        "by_stratum": by_stratum,
        "within_source_gate": {
            "status": gate_status.value,
            "reasons": gate_reasons,
            "supported_weekly_approved": False,
        },
    }


def _summarize_outcomes(outcomes: tuple[LockedOriginOutcome, ...]) -> dict[str, object]:
    previews = tuple(
        outcome for outcome in outcomes if outcome.status is LockedOutcomeStatus.PREVIEW_SHOWN
    )
    reason_counts = Counter(reason for outcome in outcomes for reason in outcome.policy_reasons)
    method_counts = Counter(
        outcome.selected_candidate.value
        for outcome in previews
        if outcome.selected_candidate is not None
    )
    summary: dict[str, object] = {
        "forecast_opportunities": len(outcomes),
        "previews_shown": len(previews),
        "abstentions": len(outcomes) - len(previews),
        "coverage_percent": _percent(len(previews), len(outcomes)),
        "selected_method_counts": dict(sorted(method_counts.items())),
        "abstention_reason_counts": dict(sorted(reason_counts.items())),
        "metrics_on_shown_previews": None,
    }
    if not previews:
        return summary

    absolute_errors = [
        abs(outcome.predicted_total_units - outcome.actual_total_units)
        for outcome in previews
        if outcome.predicted_total_units is not None
    ]
    actual_total = sum((outcome.actual_total_units for outcome in previews), Decimal("0"))
    model_mae = sum(absolute_errors, Decimal("0")) / Decimal(len(absolute_errors))
    zero_mae = sum((outcome.actual_total_units for outcome in previews), Decimal("0")) / Decimal(
        len(previews)
    )
    skill = None if zero_mae == 0 else (zero_mae - model_mae) / zero_mae
    overforecast_units = sum(
        (
            max(outcome.predicted_total_units - outcome.actual_total_units, Decimal("0"))
            for outcome in previews
            if outcome.predicted_total_units is not None
        ),
        Decimal("0"),
    )
    underforecast_units = sum(
        (
            max(outcome.actual_total_units - outcome.predicted_total_units, Decimal("0"))
            for outcome in previews
            if outcome.predicted_total_units is not None
        ),
        Decimal("0"),
    )
    summary["metrics_on_shown_previews"] = {
        "mean_absolute_error_units": str(model_mae),
        "zero_mean_absolute_error_units": str(zero_mae),
        "skill_vs_zero": str(skill) if skill is not None else None,
        "wape": (
            str(sum(absolute_errors, Decimal("0")) / actual_total) if actual_total > 0 else None
        ),
        "actual_total_units": str(actual_total),
        "overforecast_units": str(overforecast_units),
        "underforecast_units": str(underforecast_units),
        "overforecast_count": sum(
            outcome.predicted_total_units is not None
            and outcome.predicted_total_units > outcome.actual_total_units
            for outcome in previews
        ),
        "underforecast_count": sum(
            outcome.predicted_total_units is not None
            and outcome.predicted_total_units < outcome.actual_total_units
            for outcome in previews
        ),
        "exact_count": sum(
            outcome.predicted_total_units == outcome.actual_total_units for outcome in previews
        ),
    }
    return summary


def _gate_status(
    overall: dict[str, object],
    by_stratum: dict[str, dict[str, object]],
) -> tuple[LockedGateStatus, list[str]]:
    overall_skill = _summary_skill(overall)
    stratum_skills = {name: _summary_skill(summary) for name, summary in by_stratum.items()}
    if overall_skill is not None and overall_skill <= 0:
        return LockedGateStatus.FAILED, ["Shown forecasts did not beat zero overall."]
    failed_strata = sorted(
        name for name, skill in stratum_skills.items() if skill is not None and skill <= 0
    )
    if failed_strata:
        return LockedGateStatus.FAILED, [
            f"Shown forecasts did not beat zero in: {', '.join(failed_strata)}."
        ]
    inconclusive_strata = sorted(name for name, skill in stratum_skills.items() if skill is None)
    if overall_skill is None or inconclusive_strata:
        reasons = []
        if overall_skill is None:
            reasons.append("No shown forecasts were available for an overall comparison.")
        if inconclusive_strata:
            reasons.append(
                "No comparable shown forecasts were available in: "
                f"{', '.join(inconclusive_strata)}."
            )
        return LockedGateStatus.INCONCLUSIVE, reasons
    return LockedGateStatus.PASSED, [
        "Shown forecasts beat zero overall and in every stratum that was evaluated."
    ]


def _summary_skill(summary: dict[str, object]) -> Decimal | None:
    metrics = summary["metrics_on_shown_previews"]
    if not isinstance(metrics, dict):
        return None
    value = metrics["skill_vs_zero"]
    return Decimal(str(value)) if value is not None else None


def _percent(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 1) if denominator else 0.0
