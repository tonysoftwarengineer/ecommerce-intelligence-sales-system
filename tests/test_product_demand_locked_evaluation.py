from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.product_demand.contracts import ProductDateStatus
from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    EvaluationSeries,
    EvaluationSeriesPoint,
)
from src.product_demand.locked_evaluation import (
    LockedEvaluationResult,
    LockedOriginOutcome,
    LockedOutcomeStatus,
    LockedSkippedProduct,
    evaluate_locked_holdout,
    locked_evaluation_to_dict,
)
from src.product_demand.public_data_evaluation import (
    PublicDatasetPreparation,
    PublicProductProfile,
)


def _preparation(values: list[int], *, stratum: str = "dense") -> PublicDatasetPreparation:
    start = date(2024, 1, 1)
    points = tuple(
        EvaluationSeriesPoint(
            date=start + timedelta(days=index),
            status=(ProductDateStatus.OBSERVED if value > 0 else ProductDateStatus.CONFIRMED_ZERO),
            target_units=Decimal(value),
            included=True,
        )
        for index, value in enumerate(values)
    )
    series = EvaluationSeries(
        product_key="m5:LOCKED",
        unit_of_measure="source_item",
        points=points,
    )
    nonzero = sum(value > 0 for value in values)
    profile = PublicProductProfile(
        product_key=series.product_key,
        source_id="LOCKED",
        stratum=stratum,
        first_date=start,
        calendar_days=len(values),
        nonzero_days=nonzero,
        zero_target_days=len(values) - nonzero,
        observed_days=nonzero,
        confirmed_zero_days=len(values) - nonzero,
    )
    return PublicDatasetPreparation(
        dataset_name="Synthetic locked test",
        evaluation_mode="test",
        source_row_count=1,
        source_product_count=1,
        selected_source_ids=("LOCKED",),
        series=(series,),
        profiles=(profile,),
    )


def test_constant_demand_passes_each_locked_week_without_future_leakage() -> None:
    result = evaluate_locked_holdout(_preparation([3] * 260), ("DEVELOPMENT",))

    assert len(result.outcomes) == 13
    assert all(outcome.status is LockedOutcomeStatus.PREVIEW_SHOWN for outcome in result.outcomes)
    assert all(outcome.predicted_total_units == 21 for outcome in result.outcomes)
    payload = locked_evaluation_to_dict(result)
    assert payload["overall"]["coverage_percent"] == 100.0
    assert payload["overall"]["metrics_on_shown_previews"]["skill_vs_zero"] == "1"
    assert payload["within_source_gate"]["status"] == "passed"
    assert payload["within_source_gate"]["supported_weekly_approved"] is False


def test_zero_heavy_product_abstains_when_zero_is_a_perfect_historical_benchmark() -> None:
    result = evaluate_locked_holdout(
        _preparation([1] + ([0] * 259), stratum="sparse"),
        ("DEVELOPMENT",),
    )

    assert len(result.outcomes) == 13
    assert all(outcome.status is LockedOutcomeStatus.ABSTAINED for outcome in result.outcomes)
    payload = locked_evaluation_to_dict(result)
    assert payload["overall"]["coverage_percent"] == 0.0
    assert payload["within_source_gate"]["status"] == "inconclusive"


def test_changing_later_holdout_values_cannot_change_the_first_locked_prediction() -> None:
    original = ([1, 2, 3, 4, 5, 6, 7] * 38)[:260]
    changed = [*original[:-7], *([100] * 7)]

    first = evaluate_locked_holdout(_preparation(original), ("DEVELOPMENT",)).outcomes[0]
    second = evaluate_locked_holdout(_preparation(changed), ("DEVELOPMENT",)).outcomes[0]

    assert first.training_end == second.training_end
    assert first.status is second.status
    assert first.selected_candidate is second.selected_candidate
    assert first.predicted_total_units == second.predicted_total_units


def test_locked_cohort_must_not_overlap_the_development_cohort() -> None:
    with pytest.raises(ValueError, match="overlaps"):
        evaluate_locked_holdout(_preparation([3] * 260), ("LOCKED",))


def test_negative_locked_skill_fails_without_changing_supported_use() -> None:
    start = date(2025, 1, 1)
    outcome = LockedOriginOutcome(
        product_key="m5:LOCKED",
        source_id="LOCKED",
        stratum="dense",
        holdout_week=1,
        training_end=start,
        forecast_dates=tuple(start + timedelta(days=offset) for offset in range(1, 8)),
        actual_total_units=Decimal("2"),
        status=LockedOutcomeStatus.PREVIEW_SHOWN,
        selected_candidate=BaselineCandidate.LAST_WEEK_TOTAL,
        predicted_total_units=Decimal("10"),
        historical_skill_vs_zero=Decimal("0.2"),
        policy_reasons=(),
    )
    result = LockedEvaluationResult(
        dataset_name="Synthetic locked test",
        development_source_ids=("DEVELOPMENT",),
        locked_source_ids=("LOCKED",),
        holdout_weeks=1,
        minimum_preview_folds=13,
        outcomes=(outcome,),
        skipped_products=(),
    )

    payload = locked_evaluation_to_dict(result)

    assert payload["within_source_gate"]["status"] == "failed"
    assert payload["within_source_gate"]["supported_weekly_approved"] is False
    metrics = payload["overall"]["metrics_on_shown_previews"]
    assert metrics["overforecast_units"] == "8"
    assert metrics["underforecast_units"] == "0"


def test_missing_stratum_evidence_does_not_erase_valid_overall_comparison() -> None:
    start = date(2025, 1, 1)
    outcome = LockedOriginOutcome(
        product_key="m5:DENSE",
        source_id="DENSE",
        stratum="dense",
        holdout_week=1,
        training_end=start,
        forecast_dates=tuple(start + timedelta(days=offset) for offset in range(1, 8)),
        actual_total_units=Decimal("10"),
        status=LockedOutcomeStatus.PREVIEW_SHOWN,
        selected_candidate=BaselineCandidate.LAST_WEEK_TOTAL,
        predicted_total_units=Decimal("9"),
        historical_skill_vs_zero=Decimal("0.2"),
        policy_reasons=(),
    )
    result = LockedEvaluationResult(
        dataset_name="Synthetic locked test",
        development_source_ids=("DEVELOPMENT",),
        locked_source_ids=("DENSE", "SPARSE"),
        holdout_weeks=1,
        minimum_preview_folds=13,
        outcomes=(outcome,),
        skipped_products=(
            LockedSkippedProduct(
                product_key="m5:SPARSE",
                source_id="SPARSE",
                stratum="sparse",
                reason="insufficient_history_before_locked_holdout",
            ),
        ),
    )

    gate = locked_evaluation_to_dict(result)["within_source_gate"]

    assert gate["status"] == "inconclusive"
    assert gate["reasons"] == ["No comparable shown forecasts were available in: sparse."]
