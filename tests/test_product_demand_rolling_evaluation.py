from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from src.product_demand.contracts import ProductDateStatus
from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    EvaluationAvailability,
    EvaluationConfiguration,
    EvaluationSeries,
    EvaluationSeriesPoint,
    EvaluationUnavailableReason,
    FoldExclusionPhase,
)
from src.product_demand.rolling_evaluation import evaluate_baseline_rolling_origin


def _series(
    values: list[int],
    *,
    statuses: dict[int, ProductDateStatus] | None = None,
) -> EvaluationSeries:
    statuses = statuses or {}
    start = date(2025, 1, 1)
    points: list[EvaluationSeriesPoint] = []
    for offset, value in enumerate(values):
        status = statuses.get(offset, ProductDateStatus.OBSERVED)
        included = status in {
            ProductDateStatus.OBSERVED,
            ProductDateStatus.CONFIRMED_ZERO,
        }
        points.append(
            EvaluationSeriesPoint(
                date=start + timedelta(days=offset),
                status=status,
                target_units=Decimal(value) if included else None,
                included=included,
            )
        )
    return EvaluationSeries("id:A", "piece", tuple(points))


def _configuration(
    *,
    minimum_training_days: int = 28,
    minimum_folds: int = 3,
) -> EvaluationConfiguration:
    return EvaluationConfiguration(
        minimum_training_days=minimum_training_days,
        minimum_folds=minimum_folds,
    )


def test_rolling_evaluation_builds_expanding_nonoverlapping_seven_day_folds() -> None:
    series = _series([5] * 49)

    result = evaluate_baseline_rolling_origin(
        series,
        BaselineCandidate.SEASONAL_NAIVE_7,
        _configuration(),
    )

    assert result.availability is EvaluationAvailability.EVALUATED
    assert len(result.folds) == 3
    assert result.skipped_folds == ()
    assert [fold.fold_number for fold in result.folds] == [1, 2, 3]
    assert [fold.training_end for fold in result.folds] == [
        date(2025, 1, 28),
        date(2025, 2, 4),
        date(2025, 2, 11),
    ]
    assert result.folds[0].forecast_dates == tuple(
        date(2025, 1, 29) + timedelta(days=offset) for offset in range(7)
    )
    assert result.folds[1].forecast_dates[0] == result.folds[0].forecast_dates[-1] + timedelta(
        days=1
    )
    assert result.folds[0].actual_daily_units == (Decimal("5"),) * 7
    assert result.folds[0].predicted_daily_units == (Decimal("5"),) * 7


def test_first_fold_cannot_see_values_from_its_future_test_window() -> None:
    series = _series(([1] * 28) + ([100] * 14))

    result = evaluate_baseline_rolling_origin(
        series,
        BaselineCandidate.LATEST_VALUE,
        _configuration(minimum_folds=2),
    )

    assert result.folds[0].predicted_daily_units == (Decimal("1"),) * 7
    assert result.folds[0].actual_daily_units == (Decimal("100"),) * 7
    assert result.folds[1].predicted_daily_units == (Decimal("100"),) * 7


def test_excluded_test_week_is_recorded_and_later_origins_continue() -> None:
    series = _series(
        [3] * 49,
        statuses={30: ProductDateStatus.MISSING_UNKNOWN},
    )

    result = evaluate_baseline_rolling_origin(
        series,
        BaselineCandidate.LATEST_VALUE,
        _configuration(minimum_folds=2),
    )

    assert result.availability is EvaluationAvailability.EVALUATED
    assert [fold.fold_number for fold in result.folds] == [2, 3]
    assert len(result.skipped_folds) == 1
    skipped = result.skipped_folds[0]
    assert skipped.fold_number == 1
    assert skipped.reason is EvaluationUnavailableReason.UNKNOWN_TARGET_GAP
    assert skipped.exclusions[0].phase is FoldExclusionPhase.TEST_WINDOW
    assert skipped.exclusions[0].date == date(2025, 1, 31)
    assert skipped.exclusions[0].status is ProductDateStatus.MISSING_UNKNOWN


def test_excluded_required_training_window_is_recorded_without_time_compression() -> None:
    series = _series(
        [3] * 49,
        statuses={27: ProductDateStatus.STOCKOUT_LIMITED},
    )

    result = evaluate_baseline_rolling_origin(
        series,
        BaselineCandidate.MOVING_AVERAGE_7,
        _configuration(minimum_folds=2),
    )

    assert result.availability is EvaluationAvailability.EVALUATED
    assert [fold.fold_number for fold in result.folds] == [2, 3]
    skipped = result.skipped_folds[0]
    assert skipped.reason is EvaluationUnavailableReason.CENSORED_TARGET
    assert skipped.exclusions[0].phase is FoldExclusionPhase.TRAINING_WINDOW
    assert skipped.exclusions[0].date == date(2025, 1, 28)


def test_short_history_returns_typed_unavailable_result() -> None:
    result = evaluate_baseline_rolling_origin(
        _series([2] * 34),
        BaselineCandidate.MOVING_AVERAGE_28,
        _configuration(),
    )

    assert result.availability is EvaluationAvailability.UNAVAILABLE
    assert result.folds == ()
    assert result.skipped_folds == ()
    assert result.unavailable_reasons == (EvaluationUnavailableReason.SHORT_HISTORY,)


def test_completed_folds_are_retained_when_minimum_fold_policy_is_not_met() -> None:
    result = evaluate_baseline_rolling_origin(
        _series([2] * 42),
        BaselineCandidate.LAST_WEEK_TOTAL,
        _configuration(minimum_folds=3),
    )

    assert result.availability is EvaluationAvailability.UNAVAILABLE
    assert len(result.folds) == 2
    assert result.unavailable_reasons == (EvaluationUnavailableReason.INSUFFICIENT_FOLDS,)


def test_candidate_natural_history_can_exceed_experimental_global_minimum() -> None:
    result = evaluate_baseline_rolling_origin(
        _series([2] * 42),
        BaselineCandidate.MOVING_AVERAGE_28,
        _configuration(minimum_training_days=7, minimum_folds=2),
    )

    assert len(result.folds) == 2
    assert result.folds[0].training_end == date(2025, 1, 28)


def test_sba_croston_runs_through_the_same_rolling_origin_boundary() -> None:
    result = evaluate_baseline_rolling_origin(
        _series([2] * 49),
        BaselineCandidate.SBA_CROSTON,
        _configuration(),
    )

    assert result.availability is EvaluationAvailability.EVALUATED
    assert len(result.folds) == 3
    assert result.folds[0].predicted_daily_units is None
    assert result.folds[0].predicted_total_units == Decimal("13.30")


def test_sba_croston_first_fold_cannot_see_future_demand() -> None:
    ordinary = evaluate_baseline_rolling_origin(
        _series([2] * 49),
        BaselineCandidate.SBA_CROSTON,
        _configuration(),
    )
    shocked = evaluate_baseline_rolling_origin(
        _series(([2] * 28) + ([100] * 7) + ([2] * 14)),
        BaselineCandidate.SBA_CROSTON,
        _configuration(),
    )

    assert ordinary.folds[0].forecast_dates == shocked.folds[0].forecast_dates
    assert ordinary.folds[0].predicted_total_units == shocked.folds[0].predicted_total_units


def test_rolling_evaluation_is_deterministic_and_does_not_mutate_series() -> None:
    series = _series(list(range(1, 50)))
    original = series

    first = evaluate_baseline_rolling_origin(
        series,
        BaselineCandidate.MEAN_4_WEEKLY_TOTALS,
        _configuration(),
    )
    second = evaluate_baseline_rolling_origin(
        series,
        BaselineCandidate.MEAN_4_WEEKLY_TOTALS,
        _configuration(),
    )

    assert first == second
    assert series == original
    assert first.folds[0].predicted_daily_units is None
    assert first.folds[0].predicted_total_units == Decimal("101.5")
