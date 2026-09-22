from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from src.product_demand.contracts import ProductDateStatus
from src.product_demand.daily_shape import (
    DailyShapeComparison,
    DailyShapeEvaluationStatus,
    DailyShapeUnavailableReason,
    daily_shape_evaluation_to_dict,
    daily_shape_portfolio_to_dict,
    evaluate_daily_shape,
    evaluate_daily_shape_portfolio,
)
from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    EvaluationConfiguration,
    EvaluationSeries,
    EvaluationSeriesPoint,
)
from src.product_demand.metrics import evaluate_product_baselines


def _series(values: list[int], product_key: str) -> EvaluationSeries:
    start = date(2025, 1, 1)
    return EvaluationSeries(
        product_key=product_key,
        unit_of_measure="piece",
        points=tuple(
            EvaluationSeriesPoint(
                date=start + timedelta(days=offset),
                status=(
                    ProductDateStatus.CONFIRMED_ZERO if value == 0 else ProductDateStatus.OBSERVED
                ),
                target_units=Decimal(value),
                included=True,
            )
            for offset, value in enumerate(values)
        ),
    )


def test_weekday_shape_is_compared_while_weekly_total_is_held_constant() -> None:
    report = evaluate_product_baselines(
        _series([1, 2, 3, 4, 5, 6, 7] * 10, "id:SEASONAL"),
        EvaluationConfiguration(),
    )

    result = evaluate_daily_shape(report)

    assert result.status is DailyShapeEvaluationStatus.EVALUATED
    assert result.weekly_total_candidate is BaselineCandidate.LAST_WEEK_TOTAL
    assert result.lowest_error_candidate is BaselineCandidate.SEASONAL_NAIVE_7
    assert len(result.candidate_evidence) == 1
    evidence = result.candidate_evidence[0]
    assert evidence.compared_fold_count == 6
    assert evidence.varying_fold_count == 6
    assert evidence.flat_mean_absolute_daily_error == Decimal("12") / Decimal("7")
    assert evidence.shaped_mean_absolute_daily_error == 0
    assert evidence.skill_vs_flat == 1
    assert evidence.comparison is DailyShapeComparison.BETTER_THAN_FLAT
    assert evidence.first_half_skill_vs_flat == 1
    assert evidence.second_half_skill_vs_flat == 1
    assert evidence.positive_skill_in_both_halves is True


def test_flat_daily_methods_do_not_claim_date_specific_evidence() -> None:
    report = evaluate_product_baselines(
        _series([3] * 70, "id:STABLE"),
        EvaluationConfiguration(),
    )

    result = evaluate_daily_shape(report)

    assert result.status is DailyShapeEvaluationStatus.UNAVAILABLE
    assert result.unavailable_reason is DailyShapeUnavailableReason.NO_DATE_VARYING_CANDIDATE
    assert result.candidate_evidence == ()
    assert result.lowest_error_candidate is None


def test_daily_shape_is_unavailable_without_a_fair_weekly_winner() -> None:
    report = evaluate_product_baselines(
        _series([3] * 34, "id:SHORT"),
        EvaluationConfiguration(),
    )

    result = evaluate_daily_shape(report)

    assert result.status is DailyShapeEvaluationStatus.UNAVAILABLE
    assert result.unavailable_reason is DailyShapeUnavailableReason.NO_WEEKLY_WINNER
    assert result.weekly_total_candidate is None


def test_daily_shape_evaluation_is_deterministic_and_does_not_mutate_report() -> None:
    report = evaluate_product_baselines(
        _series([1, 2, 3, 4, 5, 6, 7] * 10, "id:SEASONAL"),
        EvaluationConfiguration(),
    )
    original = report

    first = evaluate_daily_shape(report)
    second = evaluate_daily_shape(report)

    assert first == second
    assert report == original


def test_daily_shape_payload_preserves_scope_and_product_level_failures() -> None:
    seasonal = evaluate_product_baselines(
        _series([1, 2, 3, 4, 5, 6, 7] * 10, "id:SEASONAL"),
        EvaluationConfiguration(),
    )
    stable = evaluate_product_baselines(
        _series([3] * 70, "id:STABLE"),
        EvaluationConfiguration(),
    )

    evaluations = evaluate_daily_shape_portfolio((stable, seasonal))
    payload = daily_shape_portfolio_to_dict(evaluations)
    seasonal_payload = daily_shape_evaluation_to_dict(evaluations[0])

    assert [item.product_key for item in evaluations] == ["id:SEASONAL", "id:STABLE"]
    assert payload["status_counts"] == {"evaluated": 1, "unavailable": 1}
    assert payload["lowest_error_comparison_counts"] == {"better_than_flat": 1}
    assert payload["lowest_error_positive_in_both_halves"] == 1
    assert seasonal_payload["lowest_error_candidate"] == "seasonal_naive_7"
    assert "does not approve" in str(seasonal_payload["scope"])
