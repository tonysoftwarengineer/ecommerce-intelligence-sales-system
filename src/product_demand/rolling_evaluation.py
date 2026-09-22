"""Leakage-safe rolling-origin evaluation for product-demand baselines."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.product_demand.baselines import (
    BASELINE_DEFINITIONS,
    BaselineUnavailableError,
    forecast_baseline,
)
from src.product_demand.contracts import ProductDateStatus
from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    CandidateDefinition,
    EvaluationAvailability,
    EvaluationConfiguration,
    EvaluationSeries,
    EvaluationSeriesPoint,
    EvaluationUnavailableReason,
    FoldExclusionPhase,
    RollingOriginEvaluation,
    RollingOriginExclusion,
    RollingOriginFold,
    SkippedRollingOriginFold,
)


def evaluate_baseline_rolling_origin(
    series: EvaluationSeries,
    candidate: BaselineCandidate,
    configuration: EvaluationConfiguration,
) -> RollingOriginEvaluation:
    """Simulate repeated seven-day forecasts using only prior calendar dates."""
    definition = BASELINE_DEFINITIONS.get(candidate)
    if definition is None:
        return _unavailable(
            _deferred_definition(candidate),
            configuration,
            EvaluationUnavailableReason.CANDIDATE_HISTORY_REQUIREMENT,
        )

    first_origin = max(
        configuration.minimum_training_days,
        definition.minimum_history_days,
    )
    if len(series.points) < first_origin + configuration.horizon_days:
        return _unavailable(
            definition,
            configuration,
            EvaluationUnavailableReason.SHORT_HISTORY,
        )

    folds: list[RollingOriginFold] = []
    skipped: list[SkippedRollingOriginFold] = []
    last_origin = len(series.points) - configuration.horizon_days
    origins = range(first_origin, last_origin + 1, configuration.origin_step_days)
    for fold_number, origin in enumerate(origins, start=1):
        training_points = series.points[:origin]
        test_points = series.points[origin : origin + configuration.horizon_days]
        training = EvaluationSeries(
            product_key=series.product_key,
            unit_of_measure=series.unit_of_measure,
            points=training_points,
        )
        forecast_dates = tuple(point.date for point in test_points)
        test_exclusions = _exclusions(test_points, FoldExclusionPhase.TEST_WINDOW)
        if test_exclusions:
            skipped.append(
                _skipped_fold(
                    fold_number,
                    training,
                    forecast_dates,
                    _reason_for_exclusions(test_exclusions),
                    test_exclusions,
                    "The historical test week contains dates without eligible demand truth.",
                )
            )
            continue

        try:
            forecast = forecast_baseline(training, candidate)
        except BaselineUnavailableError as error:
            training_exclusions = _training_exclusions(training, error.affected_dates)
            skipped.append(
                _skipped_fold(
                    fold_number,
                    training,
                    forecast_dates,
                    error.reason,
                    training_exclusions,
                    str(error),
                )
            )
            continue

        if forecast.forecast_dates != forecast_dates:
            raise AssertionError("Baseline forecast dates do not match the historical test window")
        actuals = tuple(_included_target(point) for point in test_points)
        folds.append(
            RollingOriginFold(
                fold_number=fold_number,
                training_start=training.points[0].date,
                training_end=training.points[-1].date,
                forecast_dates=forecast_dates,
                actual_daily_units=actuals,
                predicted_daily_units=forecast.predicted_daily_units,
                predicted_total_units=forecast.predicted_total_units,
            )
        )

    if len(folds) >= configuration.minimum_folds:
        return RollingOriginEvaluation(
            candidate=definition,
            configuration=configuration,
            availability=EvaluationAvailability.EVALUATED,
            folds=tuple(folds),
            skipped_folds=tuple(skipped),
        )

    reasons = tuple(dict.fromkeys(fold.reason for fold in skipped))
    return RollingOriginEvaluation(
        candidate=definition,
        configuration=configuration,
        availability=EvaluationAvailability.UNAVAILABLE,
        folds=tuple(folds),
        skipped_folds=tuple(skipped),
        unavailable_reasons=(*reasons, EvaluationUnavailableReason.INSUFFICIENT_FOLDS),
    )


def _unavailable(
    definition: CandidateDefinition,
    configuration: EvaluationConfiguration,
    reason: EvaluationUnavailableReason,
) -> RollingOriginEvaluation:
    return RollingOriginEvaluation(
        candidate=definition,
        configuration=configuration,
        availability=EvaluationAvailability.UNAVAILABLE,
        unavailable_reasons=(reason,),
    )


def _deferred_definition(candidate: BaselineCandidate) -> CandidateDefinition:
    return CandidateDefinition(
        candidate=candidate,
        display_name=candidate.value.replace("_", " ").title(),
        granularity=BASELINE_DEFINITIONS[BaselineCandidate.LATEST_VALUE].granularity,
        minimum_history_days=1,
        complexity_rank=99,
    )


def _exclusions(
    points: tuple[EvaluationSeriesPoint, ...],
    phase: FoldExclusionPhase,
) -> tuple[RollingOriginExclusion, ...]:
    return tuple(
        RollingOriginExclusion(date=point.date, status=point.status, phase=phase)
        for point in points
        if not point.included
    )


def _training_exclusions(
    training: EvaluationSeries,
    affected_dates: tuple[date, ...],
) -> tuple[RollingOriginExclusion, ...]:
    affected = set(affected_dates)
    points = tuple(
        point
        for point in training.points
        if not point.included and (not affected or point.date in affected)
    )
    return _exclusions(points, FoldExclusionPhase.TRAINING_WINDOW)


def _reason_for_exclusions(
    exclusions: tuple[RollingOriginExclusion, ...],
) -> EvaluationUnavailableReason:
    statuses = {exclusion.status for exclusion in exclusions}
    if ProductDateStatus.MISSING_UNKNOWN in statuses:
        return EvaluationUnavailableReason.UNKNOWN_TARGET_GAP
    if ProductDateStatus.STOCKOUT_LIMITED in statuses:
        return EvaluationUnavailableReason.CENSORED_TARGET
    return EvaluationUnavailableReason.PRODUCT_ACTIVITY_UNCONFIRMED


def _skipped_fold(
    fold_number: int,
    training: EvaluationSeries,
    forecast_dates: tuple[date, ...],
    reason: EvaluationUnavailableReason,
    exclusions: tuple[RollingOriginExclusion, ...],
    message: str,
) -> SkippedRollingOriginFold:
    return SkippedRollingOriginFold(
        fold_number=fold_number,
        training_start=training.points[0].date,
        training_end=training.points[-1].date,
        forecast_dates=forecast_dates,
        reason=reason,
        exclusions=exclusions,
        message=message,
    )


def _included_target(point: EvaluationSeriesPoint) -> Decimal:
    if point.target_units is None:
        raise AssertionError("Included test point is missing target units")
    return point.target_units
