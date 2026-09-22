from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from src.product_demand.baselines import BASELINE_DEFINITIONS
from src.product_demand.contracts import ProductDateStatus
from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    EvaluationAvailability,
    EvaluationConfiguration,
    EvaluationSeries,
    EvaluationSeriesPoint,
    EvaluationUnavailableReason,
    LeaderboardMetric,
    RollingOriginEvaluation,
    RollingOriginFold,
    SelectionLabel,
)
from src.product_demand.metrics import (
    calculate_candidate_evaluation,
    calculate_daily_metrics,
    calculate_seven_day_metrics,
    evaluate_product_baselines,
)
from src.product_demand.rolling_evaluation import evaluate_baseline_rolling_origin


def _series(values: list[int]) -> EvaluationSeries:
    start = date(2025, 1, 1)
    return EvaluationSeries(
        product_key="id:A",
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


def _rolling_result(
    series: EvaluationSeries,
    *,
    actuals: tuple[Decimal, ...],
    predictions: tuple[Decimal, ...],
) -> RollingOriginEvaluation:
    configuration = EvaluationConfiguration(minimum_training_days=28, minimum_folds=1)
    fold = RollingOriginFold(
        fold_number=1,
        training_start=series.points[0].date,
        training_end=series.points[27].date,
        forecast_dates=tuple(point.date for point in series.points[28:35]),
        actual_daily_units=actuals,
        predicted_daily_units=predictions,
        predicted_total_units=sum(predictions, Decimal("0")),
    )
    return RollingOriginEvaluation(
        candidate=BASELINE_DEFINITIONS[BaselineCandidate.LATEST_VALUE],
        configuration=configuration,
        availability=EvaluationAvailability.EVALUATED,
        folds=(fold,),
    )


def test_daily_metrics_match_hand_calculated_errors_and_rmsse_scale() -> None:
    actuals = tuple(Decimal(value) for value in range(1, 8))
    predictions = (Decimal("4"),) * 7
    series = _series(list(range(1, 29)) + list(range(1, 8)))
    rolling = _rolling_result(series, actuals=actuals, predictions=predictions)

    metrics = calculate_daily_metrics(series, rolling)

    assert metrics.mae == Decimal("12") / Decimal("7")
    assert metrics.rmse == Decimal("2")
    assert metrics.rmsse == Decimal("2")
    assert metrics.rmsse_scale_pair_count == 27
    assert metrics.rmsse_scale_mean_squared_error == Decimal("1")
    assert metrics.total_overforecast_units == Decimal("6")
    assert metrics.total_underforecast_units == Decimal("6")
    assert metrics.signed_bias_units == Decimal("0")
    assert metrics.over_count == 3
    assert metrics.under_count == 3
    assert metrics.exact_count == 1


def test_seven_day_metrics_measure_total_error_and_direction_separately() -> None:
    actuals = (Decimal("4"),) * 7
    predictions = (Decimal("5"),) * 7
    series = _series(([1] * 28) + ([4] * 7))
    rolling = _rolling_result(series, actuals=actuals, predictions=predictions)

    metrics = calculate_seven_day_metrics(rolling)

    assert metrics.mean_absolute_total_error == Decimal("7")
    assert metrics.root_mean_squared_total_error == Decimal("7")
    assert metrics.total_overforecast_units == Decimal("7")
    assert metrics.total_underforecast_units == Decimal("0")
    assert metrics.signed_bias_units == Decimal("7")
    assert metrics.mean_bias_units == Decimal("7")
    assert (metrics.over_count, metrics.under_count, metrics.exact_count) == (1, 0, 0)


def test_rmsse_remains_undefined_when_naive_training_scale_is_zero() -> None:
    series = _series([5] * 35)
    rolling = _rolling_result(
        series,
        actuals=(Decimal("5"),) * 7,
        predictions=(Decimal("5"),) * 7,
    )

    metrics = calculate_daily_metrics(series, rolling)

    assert metrics.rmsse is None
    assert metrics.rmsse_scale_pair_count == 27
    assert metrics.rmsse_scale_mean_squared_error == Decimal("0")


def test_unavailable_rolling_result_retains_evidence_without_fake_metrics() -> None:
    series = _series([2] * 34)
    rolling = evaluate_baseline_rolling_origin(
        series,
        BaselineCandidate.MOVING_AVERAGE_28,
        EvaluationConfiguration(),
    )

    evaluation = calculate_candidate_evaluation(series, rolling)

    assert evaluation.availability is EvaluationAvailability.UNAVAILABLE
    assert evaluation.daily_metrics is None
    assert evaluation.seven_day_metrics is None
    assert evaluation.unavailable_reasons == (EvaluationUnavailableReason.SHORT_HISTORY,)


def test_product_evaluation_builds_separate_daily_and_weekly_leaderboards() -> None:
    report = evaluate_product_baselines(
        _series([5] * 49),
        EvaluationConfiguration(),
    )

    assert report.selection_label is SelectionLabel.EVALUATION_ONLY
    assert len(report.candidate_evaluations) == 8
    assert report.daily_leaderboard is not None
    assert report.daily_leaderboard.metric is LeaderboardMetric.MAE
    assert report.daily_leaderboard.fallback_used is True
    assert report.daily_winner is BaselineCandidate.LATEST_VALUE
    assert report.seven_day_leaderboard is not None
    assert report.seven_day_leaderboard.metric is LeaderboardMetric.MEAN_ABSOLUTE_TOTAL_ERROR
    assert report.seven_day_winner is BaselineCandidate.LAST_WEEK_TOTAL


def test_zero_benchmark_is_reported_but_cannot_be_selected_as_winner() -> None:
    report = evaluate_product_baselines(
        _series([0] * 49),
        EvaluationConfiguration(),
    )

    assert report.daily_leaderboard is not None
    assert report.daily_leaderboard.entries[0].candidate is BaselineCandidate.ZERO
    assert report.daily_winner is BaselineCandidate.LATEST_VALUE
    assert report.daily_leaderboard.winner is BaselineCandidate.LATEST_VALUE


def test_leaderboard_compares_candidates_only_on_shared_historical_weeks() -> None:
    start = date(2025, 1, 1)
    series = EvaluationSeries(
        product_key="id:A",
        unit_of_measure="piece",
        points=tuple(
            EvaluationSeriesPoint(
                date=start + timedelta(days=offset),
                status=(
                    ProductDateStatus.MISSING_UNKNOWN
                    if offset == 23
                    else ProductDateStatus.OBSERVED
                ),
                target_units=None if offset == 23 else Decimal("3"),
                included=offset != 23,
            )
            for offset in range(70)
        ),
    )

    report = evaluate_product_baselines(
        series,
        EvaluationConfiguration(minimum_folds=2),
    )

    assert report.daily_leaderboard is not None
    assert report.daily_leaderboard.entries
    assert {entry.compared_fold_count for entry in report.daily_leaderboard.entries} == {2}
    evaluations = {
        evaluation.candidate.candidate: evaluation for evaluation in report.candidate_evaluations
    }
    assert len(evaluations[BaselineCandidate.LATEST_VALUE].folds) == 6
    assert len(evaluations[BaselineCandidate.MOVING_AVERAGE_28].folds) == 2


def test_insufficient_fold_candidates_are_not_ranked() -> None:
    report = evaluate_product_baselines(
        _series([2] * 42),
        EvaluationConfiguration(minimum_folds=3),
    )

    assert report.daily_leaderboard is not None
    assert report.daily_leaderboard.entries == ()
    assert report.daily_winner is None
    assert report.seven_day_leaderboard is not None
    assert report.seven_day_leaderboard.entries == ()
    assert report.seven_day_winner is None
    assert report.unavailable_reasons == (EvaluationUnavailableReason.INSUFFICIENT_FOLDS,)


def test_product_evaluation_is_deterministic_and_does_not_mutate_series() -> None:
    series = _series(list(range(1, 50)))
    original = series

    first = evaluate_product_baselines(series, EvaluationConfiguration())
    second = evaluate_product_baselines(series, EvaluationConfiguration())

    assert first == second
    assert series == original
