"""Transparent, dependency-light product-demand baseline forecasts."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal
from types import MappingProxyType

from src.product_demand.contracts import ProductDateStatus
from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    BaselineForecast,
    CandidateDefinition,
    EvaluationSeries,
    EvaluationSeriesPoint,
    EvaluationUnavailableReason,
    ForecastGranularity,
)


class BaselineUnavailableError(ValueError):
    """A baseline cannot run without silently changing its natural requirements."""

    def __init__(
        self,
        candidate: BaselineCandidate,
        reason: EvaluationUnavailableReason,
        message: str,
        *,
        affected_dates: tuple[date, ...] = (),
    ) -> None:
        super().__init__(message)
        self.candidate = candidate
        self.reason = reason
        self.affected_dates = affected_dates


CROSTON_SBA_ALPHA = Decimal("0.1")
CROSTON_SBA_BIAS_CORRECTION = Decimal("0.95")


BASELINE_DEFINITIONS: Mapping[BaselineCandidate, CandidateDefinition] = MappingProxyType(
    {
        BaselineCandidate.ZERO: CandidateDefinition(
            candidate=BaselineCandidate.ZERO,
            display_name="Zero benchmark",
            granularity=ForecastGranularity.DAILY,
            minimum_history_days=1,
            complexity_rank=0,
            benchmark_only=True,
        ),
        BaselineCandidate.LATEST_VALUE: CandidateDefinition(
            candidate=BaselineCandidate.LATEST_VALUE,
            display_name="Latest value",
            granularity=ForecastGranularity.DAILY,
            minimum_history_days=1,
            complexity_rank=1,
        ),
        BaselineCandidate.SEASONAL_NAIVE_7: CandidateDefinition(
            candidate=BaselineCandidate.SEASONAL_NAIVE_7,
            display_name="Seasonal naive 7",
            granularity=ForecastGranularity.DAILY,
            minimum_history_days=7,
            complexity_rank=2,
        ),
        BaselineCandidate.MOVING_AVERAGE_7: CandidateDefinition(
            candidate=BaselineCandidate.MOVING_AVERAGE_7,
            display_name="Moving average 7",
            granularity=ForecastGranularity.DAILY,
            minimum_history_days=7,
            complexity_rank=2,
        ),
        BaselineCandidate.MOVING_AVERAGE_28: CandidateDefinition(
            candidate=BaselineCandidate.MOVING_AVERAGE_28,
            display_name="Moving average 28",
            granularity=ForecastGranularity.DAILY,
            minimum_history_days=28,
            complexity_rank=3,
        ),
        BaselineCandidate.LAST_WEEK_TOTAL: CandidateDefinition(
            candidate=BaselineCandidate.LAST_WEEK_TOTAL,
            display_name="Last week total",
            granularity=ForecastGranularity.SEVEN_DAY_TOTAL,
            minimum_history_days=7,
            complexity_rank=1,
        ),
        BaselineCandidate.MEAN_4_WEEKLY_TOTALS: CandidateDefinition(
            candidate=BaselineCandidate.MEAN_4_WEEKLY_TOTALS,
            display_name="Mean of last 4 weekly totals",
            granularity=ForecastGranularity.SEVEN_DAY_TOTAL,
            minimum_history_days=28,
            complexity_rank=2,
        ),
        BaselineCandidate.SBA_CROSTON: CandidateDefinition(
            candidate=BaselineCandidate.SBA_CROSTON,
            display_name="SBA Croston expected rate",
            granularity=ForecastGranularity.SEVEN_DAY_TOTAL,
            minimum_history_days=28,
            complexity_rank=3,
        ),
    }
)


def forecast_baseline(
    history: EvaluationSeries,
    candidate: BaselineCandidate,
) -> BaselineForecast:
    """Forecast the next seven dates using one explicit baseline formula."""
    definition = BASELINE_DEFINITIONS.get(candidate)
    if definition is None:
        raise BaselineUnavailableError(
            candidate,
            EvaluationUnavailableReason.CANDIDATE_HISTORY_REQUIREMENT,
            f"Candidate {candidate.value!r} is deferred or not implemented in Milestone 11B-1.",
        )
    if len(history.points) < definition.minimum_history_days or history.included_count == 0:
        raise BaselineUnavailableError(
            candidate,
            EvaluationUnavailableReason.SHORT_HISTORY,
            (
                f"Candidate {candidate.value!r} requires at least "
                f"{definition.minimum_history_days} included calendar days."
            ),
        )

    training_end = history.points[-1].date
    forecast_dates = tuple(training_end + timedelta(days=offset) for offset in range(1, 8))

    if candidate is BaselineCandidate.ZERO:
        return _daily_forecast(definition, training_end, forecast_dates, (Decimal("0"),) * 7)

    if candidate is BaselineCandidate.SBA_CROSTON:
        complete_values = _required_complete_targets(history, definition)
        daily_rate = _sba_croston_daily_rate(complete_values)
        return _total_forecast(
            definition,
            training_end,
            forecast_dates,
            daily_rate * Decimal("7"),
        )

    recent_values = _required_recent_targets(history, definition)
    if candidate is BaselineCandidate.LATEST_VALUE:
        daily = (recent_values[-1],) * 7
        return _daily_forecast(definition, training_end, forecast_dates, daily)
    if candidate is BaselineCandidate.SEASONAL_NAIVE_7:
        return _daily_forecast(definition, training_end, forecast_dates, recent_values)
    if candidate is BaselineCandidate.MOVING_AVERAGE_7:
        average = _mean(recent_values)
        return _daily_forecast(definition, training_end, forecast_dates, (average,) * 7)
    if candidate is BaselineCandidate.MOVING_AVERAGE_28:
        average = _mean(recent_values)
        return _daily_forecast(definition, training_end, forecast_dates, (average,) * 7)
    if candidate is BaselineCandidate.LAST_WEEK_TOTAL:
        return _total_forecast(
            definition,
            training_end,
            forecast_dates,
            sum(recent_values, Decimal("0")),
        )
    if candidate is BaselineCandidate.MEAN_4_WEEKLY_TOTALS:
        return _total_forecast(
            definition,
            training_end,
            forecast_dates,
            sum(recent_values, Decimal("0")) / Decimal("4"),
        )
    raise AssertionError(f"Unhandled baseline candidate: {candidate.value}")


def _required_recent_targets(
    history: EvaluationSeries,
    definition: CandidateDefinition,
) -> tuple[Decimal, ...]:
    required_days = definition.minimum_history_days
    if len(history.points) < required_days:
        raise BaselineUnavailableError(
            definition.candidate,
            EvaluationUnavailableReason.SHORT_HISTORY,
            f"Candidate {definition.candidate.value!r} requires {required_days} calendar days.",
        )
    recent = history.points[-required_days:]
    excluded = tuple(point for point in recent if not point.included)
    if excluded:
        reason = _exclusion_reason(excluded)
        raise BaselineUnavailableError(
            definition.candidate,
            reason,
            (
                f"Candidate {definition.candidate.value!r} cannot compress excluded dates "
                "inside its required recent-history window."
            ),
            affected_dates=tuple(point.date for point in excluded),
        )
    return tuple(_included_target(point) for point in recent)


def _required_complete_targets(
    history: EvaluationSeries,
    definition: CandidateDefinition,
) -> tuple[Decimal, ...]:
    excluded = tuple(point for point in history.points if not point.included)
    if excluded:
        raise BaselineUnavailableError(
            definition.candidate,
            _exclusion_reason(excluded),
            (
                f"Candidate {definition.candidate.value!r} requires an unbroken calendar "
                "because missing dates change the estimated intervals between demand events."
            ),
            affected_dates=tuple(point.date for point in excluded),
        )
    return tuple(_included_target(point) for point in history.points)


def _sba_croston_daily_rate(values: tuple[Decimal, ...]) -> Decimal:
    positive = tuple((index, value) for index, value in enumerate(values) if value > 0)
    if not positive:
        return Decimal("0")

    demand_sizes = tuple(value for _, value in positive)
    occurrence_positions = tuple(index + 1 for index, _ in positive)
    intervals = (occurrence_positions[0],) + tuple(
        current - previous
        for previous, current in zip(occurrence_positions, occurrence_positions[1:])
    )
    smoothed_size = _simple_exponential_smoothing(demand_sizes, CROSTON_SBA_ALPHA)
    smoothed_interval = _simple_exponential_smoothing(
        tuple(Decimal(interval) for interval in intervals),
        CROSTON_SBA_ALPHA,
    )
    return CROSTON_SBA_BIAS_CORRECTION * smoothed_size / smoothed_interval


def _simple_exponential_smoothing(
    values: tuple[Decimal, ...],
    alpha: Decimal,
) -> Decimal:
    estimate = values[0]
    for value in values[1:]:
        estimate = alpha * value + (Decimal("1") - alpha) * estimate
    return estimate


def _exclusion_reason(
    points: tuple[EvaluationSeriesPoint, ...],
) -> EvaluationUnavailableReason:
    statuses = {point.status for point in points}
    if ProductDateStatus.MISSING_UNKNOWN in statuses:
        return EvaluationUnavailableReason.UNKNOWN_TARGET_GAP
    if ProductDateStatus.STOCKOUT_LIMITED in statuses:
        return EvaluationUnavailableReason.CENSORED_TARGET
    return EvaluationUnavailableReason.PRODUCT_ACTIVITY_UNCONFIRMED


def _included_target(point: EvaluationSeriesPoint) -> Decimal:
    if point.target_units is None:
        raise AssertionError("Included evaluation point is missing target units")
    return point.target_units


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))


def _daily_forecast(
    definition: CandidateDefinition,
    training_end: date,
    forecast_dates: tuple[date, ...],
    daily: tuple[Decimal, ...],
) -> BaselineForecast:
    return BaselineForecast(
        candidate=definition.candidate,
        granularity=definition.granularity,
        training_end=training_end,
        forecast_dates=forecast_dates,
        predicted_daily_units=daily,
        predicted_total_units=sum(daily, Decimal("0")),
    )


def _total_forecast(
    definition: CandidateDefinition,
    training_end: date,
    forecast_dates: tuple[date, ...],
    total: Decimal,
) -> BaselineForecast:
    return BaselineForecast(
        candidate=definition.candidate,
        granularity=definition.granularity,
        training_end=training_end,
        forecast_dates=forecast_dates,
        predicted_total_units=total,
    )
