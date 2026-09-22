from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.product_demand.baselines import (
    BASELINE_DEFINITIONS,
    CROSTON_SBA_ALPHA,
    CROSTON_SBA_BIAS_CORRECTION,
    BaselineUnavailableError,
    forecast_baseline,
)
from src.product_demand.contracts import ProductDateStatus
from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    EvaluationSeries,
    EvaluationSeriesPoint,
    EvaluationUnavailableReason,
    ForecastGranularity,
)


def _series(
    values: list[int | str | Decimal | None],
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
                target_units=Decimal(str(value)) if included and value is not None else None,
                included=included,
            )
        )
    return EvaluationSeries(
        product_key="id:A",
        unit_of_measure="piece",
        points=tuple(points),
    )


def test_baseline_registry_is_bounded_transparent_and_includes_weekly_sba_croston() -> None:
    assert tuple(BASELINE_DEFINITIONS) == (
        BaselineCandidate.ZERO,
        BaselineCandidate.LATEST_VALUE,
        BaselineCandidate.SEASONAL_NAIVE_7,
        BaselineCandidate.MOVING_AVERAGE_7,
        BaselineCandidate.MOVING_AVERAGE_28,
        BaselineCandidate.LAST_WEEK_TOTAL,
        BaselineCandidate.MEAN_4_WEEKLY_TOTALS,
        BaselineCandidate.SBA_CROSTON,
    )
    assert BASELINE_DEFINITIONS[BaselineCandidate.ZERO].benchmark_only is True
    croston = BASELINE_DEFINITIONS[BaselineCandidate.SBA_CROSTON]
    assert croston.granularity is ForecastGranularity.SEVEN_DAY_TOTAL
    assert croston.minimum_history_days == 28
    assert CROSTON_SBA_ALPHA == Decimal("0.1")
    assert CROSTON_SBA_BIAS_CORRECTION == Decimal("0.95")


@pytest.mark.parametrize(
    ("candidate", "values", "expected_daily", "expected_total"),
    [
        (
            BaselineCandidate.ZERO,
            [9],
            (Decimal("0"),) * 7,
            Decimal("0"),
        ),
        (
            BaselineCandidate.LATEST_VALUE,
            [2, 5],
            (Decimal("5"),) * 7,
            Decimal("35"),
        ),
        (
            BaselineCandidate.SEASONAL_NAIVE_7,
            [1, 2, 3, 4, 5, 6, 7],
            tuple(Decimal(value) for value in range(1, 8)),
            Decimal("28"),
        ),
        (
            BaselineCandidate.MOVING_AVERAGE_7,
            [1, 2, 3, 4, 5, 6, 7],
            (Decimal("4"),) * 7,
            Decimal("28"),
        ),
        (
            BaselineCandidate.MOVING_AVERAGE_28,
            list(range(1, 29)),
            (Decimal("14.5"),) * 7,
            Decimal("101.5"),
        ),
    ],
)
def test_daily_baselines_match_hand_calculated_predictions(
    candidate: BaselineCandidate,
    values: list[int],
    expected_daily: tuple[Decimal, ...],
    expected_total: Decimal,
) -> None:
    history = _series(values)

    forecast = forecast_baseline(history, candidate)

    assert forecast.granularity is ForecastGranularity.DAILY
    assert forecast.predicted_daily_units == expected_daily
    assert forecast.predicted_total_units == expected_total
    assert forecast.forecast_dates[0] == history.points[-1].date + timedelta(days=1)


@pytest.mark.parametrize(
    ("candidate", "values", "expected_total"),
    [
        (
            BaselineCandidate.LAST_WEEK_TOTAL,
            list(range(1, 15)),
            Decimal("77"),
        ),
        (
            BaselineCandidate.MEAN_4_WEEKLY_TOTALS,
            list(range(1, 29)),
            Decimal("101.5"),
        ),
        (
            BaselineCandidate.SBA_CROSTON,
            ([0] * 6 + [6]) * 4,
            Decimal("5.70"),
        ),
    ],
)
def test_seven_day_baselines_match_hand_calculated_totals(
    candidate: BaselineCandidate,
    values: list[int],
    expected_total: Decimal,
) -> None:
    forecast = forecast_baseline(_series(values), candidate)

    assert forecast.granularity is ForecastGranularity.SEVEN_DAY_TOTAL
    assert forecast.predicted_daily_units is None
    assert forecast.predicted_total_units == expected_total


@pytest.mark.parametrize(
    ("candidate", "history_days"),
    [
        (BaselineCandidate.LATEST_VALUE, 0),
        (BaselineCandidate.SEASONAL_NAIVE_7, 6),
        (BaselineCandidate.MOVING_AVERAGE_7, 6),
        (BaselineCandidate.MOVING_AVERAGE_28, 27),
        (BaselineCandidate.LAST_WEEK_TOTAL, 6),
        (BaselineCandidate.MEAN_4_WEEKLY_TOTALS, 27),
        (BaselineCandidate.SBA_CROSTON, 27),
    ],
)
def test_baselines_fail_explicitly_when_natural_history_is_too_short(
    candidate: BaselineCandidate,
    history_days: int,
) -> None:
    values = list(range(1, history_days + 1)) or [1]
    history = _series(values)
    if history_days == 0:
        history = _series(
            [None],
            statuses={0: ProductDateStatus.MISSING_UNKNOWN},
        )

    with pytest.raises(BaselineUnavailableError) as error:
        forecast_baseline(history, candidate)

    assert error.value.reason is EvaluationUnavailableReason.SHORT_HISTORY


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (
            ProductDateStatus.MISSING_UNKNOWN,
            EvaluationUnavailableReason.UNKNOWN_TARGET_GAP,
        ),
        (
            ProductDateStatus.STOCKOUT_LIMITED,
            EvaluationUnavailableReason.CENSORED_TARGET,
        ),
        (
            ProductDateStatus.BUSINESS_CLOSED,
            EvaluationUnavailableReason.PRODUCT_ACTIVITY_UNCONFIRMED,
        ),
    ],
)
def test_baselines_do_not_compress_excluded_dates_in_the_required_window(
    status: ProductDateStatus,
    reason: EvaluationUnavailableReason,
) -> None:
    history = _series(
        list(range(1, 9)),
        statuses={7: status},
    )

    with pytest.raises(BaselineUnavailableError) as error:
        forecast_baseline(history, BaselineCandidate.MOVING_AVERAGE_7)

    assert error.value.reason is reason
    assert history.points[-1].date in error.value.affected_dates


def test_exclusion_before_required_recent_window_does_not_block_baseline() -> None:
    history = _series(
        [None, 1, 2, 3, 4, 5, 6, 7],
        statuses={0: ProductDateStatus.MISSING_UNKNOWN},
    )

    forecast = forecast_baseline(history, BaselineCandidate.MOVING_AVERAGE_7)

    assert forecast.predicted_daily_units == (Decimal("4"),) * 7


def test_baselines_are_deterministic_nonnegative_and_do_not_mutate_history() -> None:
    history = _series([0] * 28)
    original = history

    first = forecast_baseline(history, BaselineCandidate.MOVING_AVERAGE_28)
    second = forecast_baseline(history, BaselineCandidate.MOVING_AVERAGE_28)

    assert first == second
    assert first.predicted_total_units == 0
    assert all(value >= 0 for value in first.predicted_daily_units or ())
    assert history == original


def test_sba_croston_returns_zero_for_complete_all_zero_history() -> None:
    forecast = forecast_baseline(_series([0] * 28), BaselineCandidate.SBA_CROSTON)

    assert forecast.predicted_total_units == 0
    assert forecast.predicted_daily_units is None


def test_sba_croston_rejects_unknown_dates_anywhere_in_interval_history() -> None:
    history = _series(
        ([6] + ([0] * 27)),
        statuses={10: ProductDateStatus.MISSING_UNKNOWN},
    )

    with pytest.raises(BaselineUnavailableError) as error:
        forecast_baseline(history, BaselineCandidate.SBA_CROSTON)

    assert error.value.reason is EvaluationUnavailableReason.UNKNOWN_TARGET_GAP
    assert history.points[10].date in error.value.affected_dates
    assert "intervals between demand events" in str(error.value)
