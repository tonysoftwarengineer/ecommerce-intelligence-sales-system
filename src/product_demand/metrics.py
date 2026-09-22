"""Zero-safe metrics and evaluation-only product-demand leaderboards."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from src.product_demand.baselines import BASELINE_DEFINITIONS
from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    CandidateEvaluation,
    DailyForecastMetrics,
    EvaluationAvailability,
    EvaluationConfiguration,
    EvaluationLeaderboard,
    EvaluationSeries,
    ForecastGranularity,
    LeaderboardEntry,
    LeaderboardMetric,
    ProductEvaluationReport,
    RollingOriginEvaluation,
    RollingOriginFold,
    SelectionLabel,
    SevenDayForecastMetrics,
    SkippedRollingOriginFold,
)
from src.product_demand.rolling_evaluation import evaluate_baseline_rolling_origin


def calculate_daily_metrics(
    series: EvaluationSeries,
    rolling: RollingOriginEvaluation,
) -> DailyForecastMetrics:
    """Calculate daily errors and RMSSE from successful daily folds."""
    _require_evaluated(rolling)
    if rolling.candidate.granularity is not ForecastGranularity.DAILY:
        raise ValueError("Daily metrics require a daily candidate")

    return _daily_metrics_for_folds(
        series,
        rolling.folds,
        _first_training_end(rolling),
    )


def _daily_metrics_for_folds(
    series: EvaluationSeries,
    folds: tuple[RollingOriginFold, ...],
    scale_training_end: date,
) -> DailyForecastMetrics:
    errors: list[Decimal] = []
    for fold in folds:
        if fold.predicted_daily_units is None:
            raise ValueError("Daily fold is missing daily predictions")
        errors.extend(
            predicted - actual
            for predicted, actual in zip(
                fold.predicted_daily_units,
                fold.actual_daily_units,
            )
        )
    mean_squared_error = _mean(tuple(error * error for error in errors))
    scale_mean_squared_error, scale_pair_count = _rmsse_scale(
        series,
        scale_training_end,
    )
    rmsse = (
        None
        if scale_mean_squared_error is None or scale_mean_squared_error == 0
        else (mean_squared_error / scale_mean_squared_error).sqrt()
    )
    directional = _directional(tuple(errors))
    return DailyForecastMetrics(
        mae=_mean(tuple(abs(error) for error in errors)),
        rmse=mean_squared_error.sqrt(),
        rmsse=rmsse,
        total_overforecast_units=directional.over,
        total_underforecast_units=directional.under,
        signed_bias_units=directional.bias,
        mean_bias_units=directional.bias / Decimal(len(errors)),
        over_count=directional.over_count,
        under_count=directional.under_count,
        exact_count=directional.exact_count,
        evaluated_date_count=len(errors),
        rmsse_scale_pair_count=scale_pair_count,
        rmsse_scale_mean_squared_error=scale_mean_squared_error,
    )


def calculate_seven_day_metrics(
    rolling: RollingOriginEvaluation,
) -> SevenDayForecastMetrics:
    """Calculate one total error per successful seven-day fold."""
    _require_evaluated(rolling)
    return _seven_day_metrics_for_folds(rolling.folds)


def _seven_day_metrics_for_folds(
    folds: tuple[RollingOriginFold, ...],
) -> SevenDayForecastMetrics:
    errors = tuple(
        fold.predicted_total_units - sum(fold.actual_daily_units, Decimal("0")) for fold in folds
    )
    mean_squared_error = _mean(tuple(error * error for error in errors))
    directional = _directional(errors)
    return SevenDayForecastMetrics(
        mean_absolute_total_error=_mean(tuple(abs(error) for error in errors)),
        root_mean_squared_total_error=mean_squared_error.sqrt(),
        total_overforecast_units=directional.over,
        total_underforecast_units=directional.under,
        signed_bias_units=directional.bias,
        mean_bias_units=directional.bias / Decimal(len(errors)),
        over_count=directional.over_count,
        under_count=directional.under_count,
        exact_count=directional.exact_count,
        evaluated_fold_count=len(errors),
    )


def calculate_candidate_evaluation(
    series: EvaluationSeries,
    rolling: RollingOriginEvaluation,
) -> CandidateEvaluation:
    """Attach aggregate metrics when enough rolling folds are available."""
    if rolling.availability is EvaluationAvailability.UNAVAILABLE:
        return CandidateEvaluation(
            candidate=rolling.candidate,
            availability=rolling.availability,
            folds=rolling.folds,
            skipped_folds=rolling.skipped_folds,
            unavailable_reasons=rolling.unavailable_reasons,
        )
    daily_metrics = (
        calculate_daily_metrics(series, rolling)
        if rolling.candidate.granularity is ForecastGranularity.DAILY
        else None
    )
    return CandidateEvaluation(
        candidate=rolling.candidate,
        availability=rolling.availability,
        folds=rolling.folds,
        skipped_folds=rolling.skipped_folds,
        daily_metrics=daily_metrics,
        seven_day_metrics=calculate_seven_day_metrics(rolling),
    )


def evaluate_product_baselines(
    series: EvaluationSeries,
    configuration: EvaluationConfiguration,
    candidates: Iterable[BaselineCandidate] | None = None,
) -> ProductEvaluationReport:
    """Evaluate the bounded baseline registry and build separate leaderboards."""
    selected_candidates = (
        tuple(candidates) if candidates is not None else tuple(BASELINE_DEFINITIONS)
    )
    evaluations = tuple(
        calculate_candidate_evaluation(
            series,
            evaluate_baseline_rolling_origin(series, candidate, configuration),
        )
        for candidate in selected_candidates
    )
    daily = _daily_leaderboard(series, evaluations, configuration.minimum_folds)
    weekly = _weekly_leaderboard(evaluations, configuration.minimum_folds)
    candidate_unavailable_reasons = tuple(
        dict.fromkeys(
            reason
            for evaluation in evaluations
            if evaluation.availability is EvaluationAvailability.UNAVAILABLE
            for reason in evaluation.unavailable_reasons
        )
    )
    report_has_ranked_evidence = bool(daily.entries or weekly.entries)
    return ProductEvaluationReport(
        product_key=series.product_key,
        unit_of_measure=series.unit_of_measure,
        candidate_evaluations=evaluations,
        daily_leaderboard=daily,
        seven_day_leaderboard=weekly,
        daily_winner=daily.winner,
        seven_day_winner=weekly.winner,
        unavailable_reasons=(() if report_has_ranked_evidence else candidate_unavailable_reasons),
        selection_label=SelectionLabel.EVALUATION_ONLY,
    )


def _daily_leaderboard(
    series: EvaluationSeries,
    evaluations: tuple[CandidateEvaluation, ...],
    minimum_folds: int,
) -> EvaluationLeaderboard:
    eligible = tuple(
        evaluation
        for evaluation in evaluations
        if evaluation.availability is EvaluationAvailability.EVALUATED
        and evaluation.candidate.granularity is ForecastGranularity.DAILY
        and evaluation.daily_metrics is not None
    )
    common_folds = _common_folds(eligible)
    if len(common_folds) < minimum_folds:
        return EvaluationLeaderboard(
            granularity=ForecastGranularity.DAILY,
            metric=LeaderboardMetric.RMSSE,
            entries=(),
            winner=None,
            fallback_used=False,
            explanation=(
                "Daily candidates did not share the configured minimum number of identical "
                "historical test weeks, so no fair leaderboard was produced."
            ),
        )
    comparable_metrics = {
        evaluation.candidate.candidate: _daily_metrics_for_folds(
            series,
            _folds_for_dates(evaluation, common_folds),
            _folds_for_dates(evaluation, common_folds)[0].training_end,
        )
        for evaluation in eligible
    }
    rmsse_available = bool(eligible) and all(
        comparable_metrics[evaluation.candidate.candidate].rmsse is not None
        for evaluation in eligible
    )
    metric = LeaderboardMetric.RMSSE if rmsse_available else LeaderboardMetric.MAE
    values = []
    for evaluation in eligible:
        metrics = comparable_metrics[evaluation.candidate.candidate]
        primary = metrics.rmsse if rmsse_available else metrics.mae
        if primary is None:
            raise AssertionError("Daily leaderboard primary metric is undefined")
        values.append(
            (
                evaluation,
                primary,
                abs(metrics.mean_bias_units),
                len(common_folds),
            )
        )
    entries = _ranked_entries(values, metric)
    winner = _first_nonbenchmark(entries)
    fallback = bool(eligible) and not rmsse_available
    explanation = (
        "RMSSE ranked daily candidates using a common historical naive scale."
        if rmsse_available
        else (
            "RMSSE was undefined for at least one eligible daily candidate, so the entire "
            "daily leaderboard used MAE; undefined values were not replaced with zero."
            if eligible
            else "No daily candidate produced the configured minimum rolling folds."
        )
    )
    return EvaluationLeaderboard(
        granularity=ForecastGranularity.DAILY,
        metric=metric,
        entries=entries,
        winner=winner,
        fallback_used=fallback,
        explanation=explanation,
    )


def _weekly_leaderboard(
    evaluations: tuple[CandidateEvaluation, ...],
    minimum_folds: int,
) -> EvaluationLeaderboard:
    eligible = tuple(
        evaluation
        for evaluation in evaluations
        if evaluation.availability is EvaluationAvailability.EVALUATED
        and evaluation.candidate.granularity is ForecastGranularity.SEVEN_DAY_TOTAL
        and evaluation.seven_day_metrics is not None
    )
    common_folds = _common_folds(eligible)
    if len(common_folds) < minimum_folds:
        return EvaluationLeaderboard(
            granularity=ForecastGranularity.SEVEN_DAY_TOTAL,
            metric=LeaderboardMetric.MEAN_ABSOLUTE_TOTAL_ERROR,
            entries=(),
            winner=None,
            fallback_used=False,
            explanation=(
                "Weekly candidates did not share the configured minimum number of identical "
                "historical test weeks, so no fair leaderboard was produced."
            ),
        )
    values = []
    for evaluation in eligible:
        metrics = _seven_day_metrics_for_folds(_folds_for_dates(evaluation, common_folds))
        values.append(
            (
                evaluation,
                metrics.mean_absolute_total_error,
                abs(metrics.mean_bias_units),
                len(common_folds),
            )
        )
    entries = _ranked_entries(values, LeaderboardMetric.MEAN_ABSOLUTE_TOTAL_ERROR)
    winner = _first_nonbenchmark(entries)
    return EvaluationLeaderboard(
        granularity=ForecastGranularity.SEVEN_DAY_TOTAL,
        metric=LeaderboardMetric.MEAN_ABSOLUTE_TOTAL_ERROR,
        entries=entries,
        winner=winner,
        fallback_used=False,
        explanation=(
            "Mean absolute seven-day-total error ranked eligible weekly candidates."
            if eligible
            else "No seven-day-total candidate produced the configured minimum rolling folds."
        ),
    )


def _ranked_entries(
    values: list[tuple[CandidateEvaluation, Decimal, Decimal, int]],
    metric: LeaderboardMetric,
) -> tuple[LeaderboardEntry, ...]:
    ordered = sorted(
        values,
        key=lambda value: (
            value[1],
            value[2],
            value[0].candidate.complexity_rank,
            value[0].candidate.candidate.value,
        ),
    )
    return tuple(
        LeaderboardEntry(
            rank=rank,
            candidate=evaluation.candidate.candidate,
            metric=metric,
            primary_value=primary,
            absolute_mean_bias_units=absolute_mean_bias,
            compared_fold_count=compared_fold_count,
            complexity_rank=evaluation.candidate.complexity_rank,
            benchmark_only=evaluation.candidate.benchmark_only,
        )
        for rank, (evaluation, primary, absolute_mean_bias, compared_fold_count) in enumerate(
            ordered,
            start=1,
        )
    )


def _first_nonbenchmark(
    entries: tuple[LeaderboardEntry, ...],
) -> BaselineCandidate | None:
    return next(
        (entry.candidate for entry in entries if not entry.benchmark_only),
        None,
    )


def _rmsse_scale(
    series: EvaluationSeries,
    first_training_end: date,
) -> tuple[Decimal | None, int]:
    training = tuple(point for point in series.points if point.date <= first_training_end)
    squared_differences: list[Decimal] = []
    for previous, current in zip(training, training[1:]):
        if not previous.included or not current.included:
            continue
        if previous.target_units is None or current.target_units is None:
            raise AssertionError("Included RMSSE scale point is missing target units")
        difference = current.target_units - previous.target_units
        squared_differences.append(difference * difference)
    if not squared_differences:
        return None, 0
    values = tuple(squared_differences)
    return _mean(values), len(values)


def _first_training_end(rolling: RollingOriginEvaluation) -> date:
    attempts: tuple[RollingOriginFold | SkippedRollingOriginFold, ...] = (
        *rolling.folds,
        *rolling.skipped_folds,
    )
    if not attempts:
        raise ValueError("RMSSE requires at least one attempted rolling fold")
    return min(attempt.training_end for attempt in attempts)


def _common_folds(
    evaluations: tuple[CandidateEvaluation, ...],
) -> tuple[tuple[date, ...], ...]:
    if not evaluations:
        return ()
    date_sets = [
        {tuple(fold.forecast_dates) for fold in evaluation.folds} for evaluation in evaluations
    ]
    common = set.intersection(*date_sets)
    return tuple(sorted(common))


def _folds_for_dates(
    evaluation: CandidateEvaluation,
    forecast_dates: tuple[tuple[date, ...], ...],
) -> tuple[RollingOriginFold, ...]:
    wanted = set(forecast_dates)
    return tuple(fold for fold in evaluation.folds if tuple(fold.forecast_dates) in wanted)


class _Directional:
    def __init__(self, errors: tuple[Decimal, ...]) -> None:
        self.over = sum((error for error in errors if error > 0), Decimal("0"))
        self.under = sum((-error for error in errors if error < 0), Decimal("0"))
        self.bias = self.over - self.under
        self.over_count = sum(error > 0 for error in errors)
        self.under_count = sum(error < 0 for error in errors)
        self.exact_count = sum(error == 0 for error in errors)


def _directional(errors: tuple[Decimal, ...]) -> _Directional:
    if not errors:
        raise ValueError("Directional metrics require at least one error")
    return _Directional(errors)


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("Metric calculation requires at least one value")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _require_evaluated(rolling: RollingOriginEvaluation) -> None:
    if rolling.availability is not EvaluationAvailability.EVALUATED or not rolling.folds:
        raise ValueError("Metrics require an evaluated rolling result with completed folds")
