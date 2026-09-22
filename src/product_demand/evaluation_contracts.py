"""Immutable contracts for product-demand baseline evaluation evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from types import MappingProxyType

from src.product_demand.contracts import ProductDateStatus


class ForecastGranularity(str, Enum):
    DAILY = "daily"
    SEVEN_DAY_TOTAL = "seven_day_total"


class BaselineCandidate(str, Enum):
    ZERO = "zero"
    LATEST_VALUE = "latest_value"
    SEASONAL_NAIVE_7 = "seasonal_naive_7"
    MOVING_AVERAGE_7 = "moving_average_7"
    MOVING_AVERAGE_28 = "moving_average_28"
    LAST_WEEK_TOTAL = "last_week_total"
    MEAN_4_WEEKLY_TOTALS = "mean_4_weekly_totals"
    SBA_CROSTON = "sba_croston"


class EvaluationAvailability(str, Enum):
    EVALUATED = "evaluated"
    UNAVAILABLE = "unavailable"


class EvaluationUnavailableReason(str, Enum):
    SHORT_HISTORY = "short_history"
    INSUFFICIENT_FOLDS = "insufficient_folds"
    NO_EVALUABLE_DATES = "no_evaluable_dates"
    UNKNOWN_TARGET_GAP = "unknown_target_gap"
    CENSORED_TARGET = "censored_target"
    PRODUCT_ACTIVITY_UNCONFIRMED = "product_activity_unconfirmed"
    CANDIDATE_HISTORY_REQUIREMENT = "candidate_history_requirement"
    INVALID_TARGET = "invalid_target"


class FoldExclusionPhase(str, Enum):
    TRAINING_WINDOW = "training_window"
    TEST_WINDOW = "test_window"


class LeaderboardMetric(str, Enum):
    RMSSE = "rmsse"
    MAE = "mae"
    MEAN_ABSOLUTE_TOTAL_ERROR = "mean_absolute_total_error"


class SelectionLabel(str, Enum):
    EVALUATION_ONLY = "evaluation_only"


@dataclass(frozen=True)
class EvaluationConfiguration:
    """Experimental evaluation policy, never a production trust policy."""

    horizon_days: int = 7
    origin_step_days: int = 7
    minimum_training_days: int = 28
    minimum_folds: int = 3

    def __post_init__(self) -> None:
        if self.horizon_days != 7:
            raise ValueError("horizon_days must be 7 for Milestone 11B")
        if self.origin_step_days != 7:
            raise ValueError("origin_step_days must be 7 for non-overlapping 11B folds")
        _require_positive_integer("minimum_training_days", self.minimum_training_days)
        _require_positive_integer("minimum_folds", self.minimum_folds)


@dataclass(frozen=True)
class CandidateDefinition:
    """Identity and natural eligibility requirements for one baseline method."""

    candidate: BaselineCandidate
    display_name: str
    granularity: ForecastGranularity
    minimum_history_days: int
    complexity_rank: int
    benchmark_only: bool = False

    def __post_init__(self) -> None:
        _require_text("display_name", self.display_name)
        _require_positive_integer("minimum_history_days", self.minimum_history_days)
        _require_nonnegative_integer("complexity_rank", self.complexity_rank)


@dataclass(frozen=True)
class EvaluationSeriesPoint:
    """One preserved calendar date at the evaluation preparation boundary."""

    date: date
    status: ProductDateStatus
    target_units: Decimal | None
    included: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "date", _normalized_date(self.date))
        eligible = self.status in {
            ProductDateStatus.OBSERVED,
            ProductDateStatus.CONFIRMED_ZERO,
        }
        if self.included is not eligible:
            raise ValueError("included must be true only for observed and confirmed-zero dates")
        if eligible:
            target = _decimal("target_units", self.target_units)
            if target < 0:
                raise ValueError("target_units must not be negative")
            if self.status is ProductDateStatus.CONFIRMED_ZERO and target != 0:
                raise ValueError("confirmed-zero target_units must equal zero")
            object.__setattr__(self, "target_units", target)
        elif self.target_units is not None:
            raise ValueError("excluded calendar dates must not carry evaluation target_units")


@dataclass(frozen=True)
class EvaluationSeries:
    """A complete, ordered product calendar with explicit evaluation exclusions."""

    product_key: str
    unit_of_measure: str
    points: tuple[EvaluationSeriesPoint, ...]

    def __post_init__(self) -> None:
        _require_text("product_key", self.product_key)
        _require_text("unit_of_measure", self.unit_of_measure)
        points = tuple(sorted(self.points, key=lambda point: point.date))
        if not points:
            raise ValueError("Evaluation series requires at least one calendar point")
        dates = [point.date for point in points]
        if len(dates) != len(set(dates)):
            raise ValueError("Evaluation series dates must be unique")
        expected_dates = [dates[0] + timedelta(days=offset) for offset in range(len(dates))]
        if dates != expected_dates:
            raise ValueError("Evaluation series must preserve consecutive calendar dates")
        object.__setattr__(self, "points", points)

    @property
    def included_count(self) -> int:
        return sum(point.included for point in self.points)

    @property
    def excluded_counts(self) -> Mapping[ProductDateStatus, int]:
        counts: dict[ProductDateStatus, int] = {}
        for point in self.points:
            if not point.included:
                counts[point.status] = counts.get(point.status, 0) + 1
        return MappingProxyType(counts)


@dataclass(frozen=True)
class BaselineForecast:
    """One pure baseline result before it is attached to a historical fold."""

    candidate: BaselineCandidate
    granularity: ForecastGranularity
    training_end: date
    forecast_dates: tuple[date, ...]
    predicted_total_units: Decimal
    predicted_daily_units: tuple[Decimal, ...] | None = None

    def __post_init__(self) -> None:
        training_end = _normalized_date(self.training_end)
        forecast_dates = tuple(_normalized_date(value) for value in self.forecast_dates)
        if len(forecast_dates) != 7:
            raise ValueError("Baseline forecast requires exactly 7 forecast dates")
        expected_dates = tuple(training_end + timedelta(days=offset) for offset in range(1, 8))
        if forecast_dates != expected_dates:
            raise ValueError("Baseline forecast dates must immediately follow training_end")
        predicted_total = _nonnegative_decimal("predicted_total_units", self.predicted_total_units)
        object.__setattr__(self, "training_end", training_end)
        object.__setattr__(self, "forecast_dates", forecast_dates)
        object.__setattr__(self, "predicted_total_units", predicted_total)

        if self.granularity is ForecastGranularity.DAILY:
            if self.predicted_daily_units is None:
                raise ValueError("Daily baseline forecasts require daily predictions")
            predictions = _nonnegative_decimal_tuple(
                "predicted_daily_units", self.predicted_daily_units, required_length=7
            )
            if sum(predictions, Decimal("0")) != predicted_total:
                raise ValueError(
                    "predicted_total_units must equal the sum of predicted_daily_units"
                )
            object.__setattr__(self, "predicted_daily_units", predictions)
        elif self.predicted_daily_units is not None:
            raise ValueError("Seven-day-total forecasts cannot contain daily predictions")


@dataclass(frozen=True)
class RollingOriginFold:
    """Auditable evidence for one seven-day historical forecast simulation."""

    fold_number: int
    training_start: date
    training_end: date
    forecast_dates: tuple[date, ...]
    actual_daily_units: tuple[Decimal, ...]
    predicted_total_units: Decimal
    predicted_daily_units: tuple[Decimal, ...] | None = None

    def __post_init__(self) -> None:
        _require_positive_integer("fold_number", self.fold_number)
        training_start = _normalized_date(self.training_start)
        training_end = _normalized_date(self.training_end)
        if training_start > training_end:
            raise ValueError("training_start must not be after training_end")
        object.__setattr__(self, "training_start", training_start)
        object.__setattr__(self, "training_end", training_end)

        forecast_dates = tuple(_normalized_date(value) for value in self.forecast_dates)
        if len(forecast_dates) != 7:
            raise ValueError("Rolling-origin fold requires exactly 7 forecast dates")
        if forecast_dates[0] <= training_end:
            raise ValueError("Forecast dates must begin after training_end")
        expected_dates = tuple(forecast_dates[0] + timedelta(days=offset) for offset in range(7))
        if forecast_dates != expected_dates:
            raise ValueError("Forecast dates must be consecutive calendar dates")
        object.__setattr__(self, "forecast_dates", forecast_dates)

        actuals = _nonnegative_decimal_tuple(
            "actual_daily_units", self.actual_daily_units, required_length=7
        )
        object.__setattr__(self, "actual_daily_units", actuals)
        predicted_total = _nonnegative_decimal("predicted_total_units", self.predicted_total_units)
        object.__setattr__(self, "predicted_total_units", predicted_total)

        if self.predicted_daily_units is not None:
            predictions = _nonnegative_decimal_tuple(
                "predicted_daily_units", self.predicted_daily_units, required_length=7
            )
            if sum(predictions, Decimal("0")) != predicted_total:
                raise ValueError(
                    "predicted_total_units must equal the sum of predicted_daily_units"
                )
            object.__setattr__(self, "predicted_daily_units", predictions)


@dataclass(frozen=True)
class RollingOriginExclusion:
    """One calendar date that prevents a historical fold from being evaluated."""

    date: date
    status: ProductDateStatus
    phase: FoldExclusionPhase

    def __post_init__(self) -> None:
        object.__setattr__(self, "date", _normalized_date(self.date))
        if self.status in {ProductDateStatus.OBSERVED, ProductDateStatus.CONFIRMED_ZERO}:
            raise ValueError("Rolling-origin exclusions require an excluded calendar status")


@dataclass(frozen=True)
class SkippedRollingOriginFold:
    """An attempted origin retained with the evidence explaining why it was skipped."""

    fold_number: int
    training_start: date
    training_end: date
    forecast_dates: tuple[date, ...]
    reason: EvaluationUnavailableReason
    exclusions: tuple[RollingOriginExclusion, ...]
    message: str

    def __post_init__(self) -> None:
        _require_positive_integer("fold_number", self.fold_number)
        training_start = _normalized_date(self.training_start)
        training_end = _normalized_date(self.training_end)
        if training_start > training_end:
            raise ValueError("training_start must not be after training_end")
        forecast_dates = tuple(_normalized_date(value) for value in self.forecast_dates)
        expected_dates = tuple(training_end + timedelta(days=offset) for offset in range(1, 8))
        if forecast_dates != expected_dates:
            raise ValueError("Skipped fold must retain the exact next seven forecast dates")
        exclusions = tuple(self.exclusions)
        if not exclusions:
            raise ValueError("Skipped folds require at least one exclusion")
        _require_text("message", self.message)
        object.__setattr__(self, "training_start", training_start)
        object.__setattr__(self, "training_end", training_end)
        object.__setattr__(self, "forecast_dates", forecast_dates)
        object.__setattr__(self, "exclusions", exclusions)


@dataclass(frozen=True)
class RollingOriginEvaluation:
    """Fold evidence for one candidate before aggregate metrics are calculated."""

    candidate: CandidateDefinition
    configuration: EvaluationConfiguration
    availability: EvaluationAvailability
    folds: tuple[RollingOriginFold, ...] = field(default_factory=tuple)
    skipped_folds: tuple[SkippedRollingOriginFold, ...] = field(default_factory=tuple)
    unavailable_reasons: tuple[EvaluationUnavailableReason, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        folds = tuple(self.folds)
        skipped = tuple(self.skipped_folds)
        reasons = tuple(dict.fromkeys(self.unavailable_reasons))
        fold_numbers = [fold.fold_number for fold in folds]
        skipped_numbers = [fold.fold_number for fold in skipped]
        all_numbers = fold_numbers + skipped_numbers
        if len(all_numbers) != len(set(all_numbers)):
            raise ValueError("Rolling-origin fold numbers must be unique")
        for fold in folds:
            has_daily = fold.predicted_daily_units is not None
            if self.candidate.granularity is ForecastGranularity.DAILY and not has_daily:
                raise ValueError("Daily candidates require daily fold predictions")
            if self.candidate.granularity is ForecastGranularity.SEVEN_DAY_TOTAL and has_daily:
                raise ValueError("Seven-day-total candidates cannot have daily fold predictions")
        if self.availability is EvaluationAvailability.EVALUATED:
            if len(folds) < self.configuration.minimum_folds:
                raise ValueError("Evaluated rolling results require the configured minimum folds")
            if reasons:
                raise ValueError("Evaluated rolling results cannot have unavailable reasons")
        elif not reasons:
            raise ValueError("Unavailable rolling results require at least one reason")
        object.__setattr__(self, "folds", folds)
        object.__setattr__(self, "skipped_folds", skipped)
        object.__setattr__(self, "unavailable_reasons", reasons)


@dataclass(frozen=True)
class DailyForecastMetrics:
    mae: Decimal
    rmse: Decimal
    rmsse: Decimal | None
    total_overforecast_units: Decimal
    total_underforecast_units: Decimal
    signed_bias_units: Decimal
    mean_bias_units: Decimal
    over_count: int
    under_count: int
    exact_count: int
    evaluated_date_count: int
    rmsse_scale_pair_count: int = 0
    rmsse_scale_mean_squared_error: Decimal | None = None

    def __post_init__(self) -> None:
        _validate_directional_metrics(
            self,
            count_name="evaluated_date_count",
            error_fields=("mae", "rmse", "rmsse"),
        )
        _require_nonnegative_integer("rmsse_scale_pair_count", self.rmsse_scale_pair_count)
        scale = self.rmsse_scale_mean_squared_error
        if scale is not None:
            scale = _nonnegative_decimal("rmsse_scale_mean_squared_error", scale)
            object.__setattr__(self, "rmsse_scale_mean_squared_error", scale)
            if self.rmsse_scale_pair_count == 0:
                raise ValueError("RMSSE scale evidence requires at least one adjacent pair")
        if self.rmsse is not None and (scale is None or scale == 0):
            raise ValueError("Defined RMSSE requires a positive historical scale")


@dataclass(frozen=True)
class SevenDayForecastMetrics:
    mean_absolute_total_error: Decimal
    root_mean_squared_total_error: Decimal
    total_overforecast_units: Decimal
    total_underforecast_units: Decimal
    signed_bias_units: Decimal
    mean_bias_units: Decimal
    over_count: int
    under_count: int
    exact_count: int
    evaluated_fold_count: int

    def __post_init__(self) -> None:
        _validate_directional_metrics(
            self,
            count_name="evaluated_fold_count",
            error_fields=("mean_absolute_total_error", "root_mean_squared_total_error"),
        )


@dataclass(frozen=True)
class CandidateEvaluation:
    candidate: CandidateDefinition
    availability: EvaluationAvailability
    folds: tuple[RollingOriginFold, ...] = field(default_factory=tuple)
    skipped_folds: tuple[SkippedRollingOriginFold, ...] = field(default_factory=tuple)
    daily_metrics: DailyForecastMetrics | None = None
    seven_day_metrics: SevenDayForecastMetrics | None = None
    unavailable_reasons: tuple[EvaluationUnavailableReason, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        folds = tuple(self.folds)
        skipped = tuple(self.skipped_folds)
        reasons = tuple(dict.fromkeys(self.unavailable_reasons))
        fold_numbers = [fold.fold_number for fold in folds]
        skipped_numbers = [fold.fold_number for fold in skipped]
        all_numbers = fold_numbers + skipped_numbers
        if len(all_numbers) != len(set(all_numbers)):
            raise ValueError("Candidate evaluation fold numbers must be unique")
        object.__setattr__(self, "folds", folds)
        object.__setattr__(self, "skipped_folds", skipped)
        object.__setattr__(self, "unavailable_reasons", reasons)

        if self.availability is EvaluationAvailability.EVALUATED:
            if not folds:
                raise ValueError("Evaluated candidates require at least one fold")
            if reasons:
                raise ValueError("Evaluated candidates cannot have unavailable reasons")
            if self.seven_day_metrics is None:
                raise ValueError("Evaluated candidates require seven-day metrics")
            if (
                self.candidate.granularity is ForecastGranularity.DAILY
                and self.daily_metrics is None
            ):
                raise ValueError("Evaluated daily candidates require daily metrics")
            if (
                self.candidate.granularity is ForecastGranularity.SEVEN_DAY_TOTAL
                and self.daily_metrics is not None
            ):
                raise ValueError("Seven-day-total candidates cannot have daily metrics")
        else:
            if not reasons:
                raise ValueError("Unavailable candidates require at least one unavailable reason")
            if self.daily_metrics is not None or self.seven_day_metrics is not None:
                raise ValueError("Unavailable candidates cannot have evaluation metrics")


@dataclass(frozen=True)
class LeaderboardEntry:
    rank: int
    candidate: BaselineCandidate
    metric: LeaderboardMetric
    primary_value: Decimal
    absolute_mean_bias_units: Decimal
    compared_fold_count: int
    complexity_rank: int
    benchmark_only: bool

    def __post_init__(self) -> None:
        _require_positive_integer("rank", self.rank)
        object.__setattr__(
            self,
            "primary_value",
            _nonnegative_decimal("primary_value", self.primary_value),
        )
        object.__setattr__(
            self,
            "absolute_mean_bias_units",
            _nonnegative_decimal("absolute_mean_bias_units", self.absolute_mean_bias_units),
        )
        _require_positive_integer("compared_fold_count", self.compared_fold_count)
        _require_nonnegative_integer("complexity_rank", self.complexity_rank)


@dataclass(frozen=True)
class EvaluationLeaderboard:
    granularity: ForecastGranularity
    metric: LeaderboardMetric
    entries: tuple[LeaderboardEntry, ...]
    winner: BaselineCandidate | None
    fallback_used: bool
    explanation: str
    selection_label: SelectionLabel = SelectionLabel.EVALUATION_ONLY

    def __post_init__(self) -> None:
        entries = tuple(self.entries)
        ranks = [entry.rank for entry in entries]
        if ranks != list(range(1, len(entries) + 1)):
            raise ValueError("Leaderboard ranks must be consecutive from 1")
        candidates = [entry.candidate for entry in entries]
        if len(candidates) != len(set(candidates)):
            raise ValueError("Leaderboard candidate ids must be unique")
        if any(entry.metric is not self.metric for entry in entries):
            raise ValueError("Leaderboard entries must use the leaderboard metric")
        _require_text("explanation", self.explanation)
        if self.winner is not None:
            matching = [entry for entry in entries if entry.candidate is self.winner]
            if not matching or matching[0].benchmark_only:
                raise ValueError("Leaderboard winner must be a non-benchmark entry")
        object.__setattr__(self, "entries", entries)


@dataclass(frozen=True)
class ProductEvaluationReport:
    product_key: str
    unit_of_measure: str
    candidate_evaluations: tuple[CandidateEvaluation, ...]
    daily_leaderboard: EvaluationLeaderboard | None = None
    seven_day_leaderboard: EvaluationLeaderboard | None = None
    daily_winner: BaselineCandidate | None = None
    seven_day_winner: BaselineCandidate | None = None
    unavailable_reasons: tuple[EvaluationUnavailableReason, ...] = field(default_factory=tuple)
    selection_label: SelectionLabel = SelectionLabel.EVALUATION_ONLY

    def __post_init__(self) -> None:
        _require_text("product_key", self.product_key)
        _require_text("unit_of_measure", self.unit_of_measure)
        evaluations = tuple(self.candidate_evaluations)
        identifiers = [evaluation.candidate.candidate for evaluation in evaluations]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Product evaluation candidate ids must be unique")
        object.__setattr__(self, "candidate_evaluations", evaluations)
        object.__setattr__(
            self,
            "unavailable_reasons",
            tuple(dict.fromkeys(self.unavailable_reasons)),
        )
        if self.daily_leaderboard is not None:
            if self.daily_leaderboard.granularity is not ForecastGranularity.DAILY:
                raise ValueError("Daily leaderboard must use daily granularity")
            if self.daily_winner is not self.daily_leaderboard.winner:
                raise ValueError("daily_winner must match the daily leaderboard")
        if self.seven_day_leaderboard is not None:
            if self.seven_day_leaderboard.granularity is not ForecastGranularity.SEVEN_DAY_TOTAL:
                raise ValueError("Seven-day leaderboard must use seven-day-total granularity")
            if self.seven_day_winner is not self.seven_day_leaderboard.winner:
                raise ValueError("seven_day_winner must match the seven-day leaderboard")
        self._validate_winner(self.daily_winner, ForecastGranularity.DAILY, evaluations)
        self._validate_winner(
            self.seven_day_winner,
            ForecastGranularity.SEVEN_DAY_TOTAL,
            evaluations,
        )

    @staticmethod
    def _validate_winner(
        winner: BaselineCandidate | None,
        granularity: ForecastGranularity,
        evaluations: tuple[CandidateEvaluation, ...],
    ) -> None:
        if winner is None:
            return
        matching = [
            evaluation for evaluation in evaluations if evaluation.candidate.candidate is winner
        ]
        if not matching:
            raise ValueError("Evaluation winner must reference an evaluated candidate")
        evaluation = matching[0]
        if evaluation.availability is not EvaluationAvailability.EVALUATED:
            raise ValueError("Evaluation winner must reference an evaluated candidate")
        if evaluation.candidate.granularity is not granularity:
            raise ValueError("Evaluation winner granularity does not match the leaderboard")
        if evaluation.candidate.benchmark_only:
            raise ValueError("Benchmark-only candidates cannot be evaluation winners")


def _validate_directional_metrics(
    metrics: DailyForecastMetrics | SevenDayForecastMetrics,
    *,
    count_name: str,
    error_fields: tuple[str, ...],
) -> None:
    for name in error_fields:
        value = getattr(metrics, name)
        if value is not None:
            object.__setattr__(metrics, name, _nonnegative_decimal(name, value))
    over = _nonnegative_decimal("total_overforecast_units", metrics.total_overforecast_units)
    under = _nonnegative_decimal("total_underforecast_units", metrics.total_underforecast_units)
    bias = _decimal("signed_bias_units", metrics.signed_bias_units)
    mean_bias = _decimal("mean_bias_units", metrics.mean_bias_units)
    object.__setattr__(metrics, "total_overforecast_units", over)
    object.__setattr__(metrics, "total_underforecast_units", under)
    object.__setattr__(metrics, "signed_bias_units", bias)
    object.__setattr__(metrics, "mean_bias_units", mean_bias)

    counts = [
        metrics.over_count,
        metrics.under_count,
        metrics.exact_count,
    ]
    for name, value in zip(("over_count", "under_count", "exact_count"), counts):
        _require_nonnegative_integer(name, value)
    total_count = getattr(metrics, count_name)
    _require_positive_integer(count_name, total_count)
    if sum(counts) != total_count:
        raise ValueError(f"Forecast direction counts must equal {count_name}")
    if bias != over - under:
        raise ValueError("signed_bias_units must equal overforecast minus underforecast units")
    if mean_bias != bias / Decimal(total_count):
        raise ValueError(f"mean_bias_units must equal signed bias divided by {count_name}")


def _normalized_date(value: date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValueError("Date values must be datetime.date instances")


def _decimal(name: str, value: object) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} must be numeric") from None
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    return result


def _nonnegative_decimal(name: str, value: object) -> Decimal:
    result = _decimal(name, value)
    if result < 0:
        raise ValueError(f"{name} must not be negative")
    return result


def _nonnegative_decimal_tuple(
    name: str,
    values: tuple[Decimal, ...],
    *,
    required_length: int,
) -> tuple[Decimal, ...]:
    result = tuple(_nonnegative_decimal(name, value) for value in values)
    if len(result) != required_length:
        raise ValueError(f"{name} must contain exactly {required_length} values")
    return result


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")


def _require_positive_integer(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be positive")


def _require_nonnegative_integer(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must not be negative")
