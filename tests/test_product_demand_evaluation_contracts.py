from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pandas.testing as pdt
import pytest

from src.product_demand.contracts import ProductDateStatus
from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    CandidateDefinition,
    CandidateEvaluation,
    DailyForecastMetrics,
    EvaluationAvailability,
    EvaluationConfiguration,
    EvaluationSeries,
    EvaluationSeriesPoint,
    EvaluationUnavailableReason,
    ForecastGranularity,
    ProductEvaluationReport,
    RollingOriginFold,
    SelectionLabel,
    SevenDayForecastMetrics,
)
from src.product_demand.evaluation_series import prepare_evaluation_series


def _dates(start: date = date(2025, 1, 1)) -> tuple[date, ...]:
    return tuple(start + timedelta(days=offset) for offset in range(7))


def _daily_candidate(*, benchmark_only: bool = False) -> CandidateDefinition:
    return CandidateDefinition(
        candidate=BaselineCandidate.LATEST_VALUE,
        display_name="Latest value",
        granularity=ForecastGranularity.DAILY,
        minimum_history_days=1,
        complexity_rank=1,
        benchmark_only=benchmark_only,
    )


def _daily_metrics() -> DailyForecastMetrics:
    return DailyForecastMetrics(
        mae=Decimal("1"),
        rmse=Decimal("1"),
        rmsse=Decimal("0.5"),
        total_overforecast_units=Decimal("2"),
        total_underforecast_units=Decimal("1"),
        signed_bias_units=Decimal("1"),
        mean_bias_units=Decimal("0.1428571428571428571428571429"),
        over_count=2,
        under_count=1,
        exact_count=4,
        evaluated_date_count=7,
        rmsse_scale_pair_count=6,
        rmsse_scale_mean_squared_error=Decimal("4"),
    )


def _weekly_metrics() -> SevenDayForecastMetrics:
    return SevenDayForecastMetrics(
        mean_absolute_total_error=Decimal("2"),
        root_mean_squared_total_error=Decimal("2"),
        total_overforecast_units=Decimal("2"),
        total_underforecast_units=Decimal("0"),
        signed_bias_units=Decimal("2"),
        mean_bias_units=Decimal("2"),
        over_count=1,
        under_count=0,
        exact_count=0,
        evaluated_fold_count=1,
    )


def test_evaluation_configuration_enforces_the_approved_seven_day_contract() -> None:
    configuration = EvaluationConfiguration(
        minimum_training_days=28,
        minimum_folds=3,
    )

    assert configuration.horizon_days == 7
    assert configuration.origin_step_days == 7

    with pytest.raises(ValueError, match="horizon_days must be 7"):
        EvaluationConfiguration(horizon_days=14)
    with pytest.raises(ValueError, match="minimum_training_days must be positive"):
        EvaluationConfiguration(minimum_training_days=0)


def test_candidate_definition_has_explicit_natural_history_and_identity() -> None:
    candidate = _daily_candidate()

    assert candidate.candidate is BaselineCandidate.LATEST_VALUE
    assert candidate.minimum_history_days == 1

    with pytest.raises(ValueError, match="display_name must not be blank"):
        CandidateDefinition(
            candidate=BaselineCandidate.LATEST_VALUE,
            display_name=" ",
            granularity=ForecastGranularity.DAILY,
            minimum_history_days=1,
            complexity_rank=1,
        )


def test_evaluation_series_rejects_negative_targets_and_duplicate_dates() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        EvaluationSeriesPoint(
            date=date(2025, 1, 1),
            status=ProductDateStatus.OBSERVED,
            target_units=Decimal("-1"),
            included=True,
        )

    point = EvaluationSeriesPoint(
        date=date(2025, 1, 1),
        status=ProductDateStatus.CONFIRMED_ZERO,
        target_units=Decimal("0"),
        included=True,
    )
    with pytest.raises(ValueError, match="dates must be unique"):
        EvaluationSeries(
            product_key="id:A",
            unit_of_measure="piece",
            points=(point, point),
        )

    separated = EvaluationSeriesPoint(
        date=date(2025, 1, 3),
        status=ProductDateStatus.OBSERVED,
        target_units=Decimal("1"),
        included=True,
    )
    with pytest.raises(ValueError, match="consecutive calendar dates"):
        EvaluationSeries(
            product_key="id:A",
            unit_of_measure="piece",
            points=(point, separated),
        )


def test_rolling_fold_requires_exact_future_dates_without_leakage() -> None:
    forecast_dates = _dates()
    fold = RollingOriginFold(
        fold_number=1,
        training_start=date(2024, 12, 1),
        training_end=date(2024, 12, 31),
        forecast_dates=forecast_dates,
        actual_daily_units=(Decimal("1"),) * 7,
        predicted_daily_units=(Decimal("2"),) * 7,
        predicted_total_units=Decimal("14"),
    )

    assert fold.forecast_dates[0] == fold.training_end + timedelta(days=1)

    with pytest.raises(ValueError, match="exactly 7 forecast dates"):
        RollingOriginFold(
            fold_number=1,
            training_start=date(2024, 12, 1),
            training_end=date(2024, 12, 31),
            forecast_dates=forecast_dates[:6],
            actual_daily_units=(Decimal("1"),) * 6,
            predicted_daily_units=(Decimal("2"),) * 6,
            predicted_total_units=Decimal("12"),
        )

    with pytest.raises(ValueError, match="must begin after training_end"):
        RollingOriginFold(
            fold_number=1,
            training_start=date(2024, 12, 1),
            training_end=date(2025, 1, 1),
            forecast_dates=forecast_dates,
            actual_daily_units=(Decimal("1"),) * 7,
            predicted_daily_units=(Decimal("2"),) * 7,
            predicted_total_units=Decimal("14"),
        )


def test_metric_contracts_preserve_directional_error_accounting() -> None:
    daily = _daily_metrics()
    weekly = _weekly_metrics()

    assert daily.total_overforecast_units - daily.total_underforecast_units == (
        daily.signed_bias_units
    )
    assert weekly.over_count + weekly.under_count + weekly.exact_count == 1

    with pytest.raises(ValueError, match="direction counts"):
        DailyForecastMetrics(
            mae=Decimal("0"),
            rmse=Decimal("0"),
            rmsse=None,
            total_overforecast_units=Decimal("0"),
            total_underforecast_units=Decimal("0"),
            signed_bias_units=Decimal("0"),
            mean_bias_units=Decimal("0"),
            over_count=0,
            under_count=0,
            exact_count=1,
            evaluated_date_count=7,
        )


def test_candidate_and_product_reports_are_typed_and_evaluation_only() -> None:
    candidate = _daily_candidate()
    fold = RollingOriginFold(
        fold_number=1,
        training_start=date(2024, 12, 1),
        training_end=date(2024, 12, 31),
        forecast_dates=_dates(),
        actual_daily_units=(Decimal("1"),) * 7,
        predicted_daily_units=(Decimal("2"),) * 7,
        predicted_total_units=Decimal("14"),
    )
    evaluation = CandidateEvaluation(
        candidate=candidate,
        availability=EvaluationAvailability.EVALUATED,
        folds=(fold,),
        daily_metrics=_daily_metrics(),
        seven_day_metrics=_weekly_metrics(),
    )
    report = ProductEvaluationReport(
        product_key="id:A",
        unit_of_measure="piece",
        candidate_evaluations=(evaluation,),
        daily_winner=BaselineCandidate.LATEST_VALUE,
    )

    assert report.selection_label is SelectionLabel.EVALUATION_ONLY

    with pytest.raises(ValueError, match="require at least one unavailable reason"):
        CandidateEvaluation(
            candidate=candidate,
            availability=EvaluationAvailability.UNAVAILABLE,
        )

    unavailable = CandidateEvaluation(
        candidate=candidate,
        availability=EvaluationAvailability.UNAVAILABLE,
        unavailable_reasons=(EvaluationUnavailableReason.SHORT_HISTORY,),
    )
    assert unavailable.folds == ()


def test_prepare_evaluation_series_preserves_calendar_dates_and_excludes_ambiguity() -> None:
    source = pd.DataFrame(
        [
            _calendar_row("2025-01-01", ProductDateStatus.OBSERVED, Decimal("3")),
            _calendar_row("2025-01-02", ProductDateStatus.CONFIRMED_ZERO, Decimal("0")),
            _calendar_row("2025-01-03", ProductDateStatus.MISSING_UNKNOWN, None),
            _calendar_row("2025-01-04", ProductDateStatus.STOCKOUT_LIMITED, Decimal("0")),
            _calendar_row("2025-01-05", ProductDateStatus.BUSINESS_CLOSED, Decimal("0")),
        ]
    )
    original = source.copy(deep=True)

    result = prepare_evaluation_series(source)

    assert len(result) == 1
    series = result[0]
    assert [point.date for point in series.points] == [date(2025, 1, day) for day in range(1, 6)]
    assert series.included_count == 2
    assert series.excluded_counts == {
        ProductDateStatus.BUSINESS_CLOSED: 1,
        ProductDateStatus.STOCKOUT_LIMITED: 1,
        ProductDateStatus.MISSING_UNKNOWN: 1,
    }
    assert series.points[2].target_units is None
    assert series.points[2].included is False
    pdt.assert_frame_equal(source, original)


def test_prepare_evaluation_series_is_deterministic_and_rejects_negative_target() -> None:
    source = pd.DataFrame(
        [
            _calendar_row("2025-01-02", ProductDateStatus.CONFIRMED_ZERO, Decimal("0")),
            _calendar_row("2025-01-01", ProductDateStatus.OBSERVED, Decimal("2")),
        ]
    )

    assert prepare_evaluation_series(source) == prepare_evaluation_series(source.sample(frac=1))

    invalid = source.copy(deep=True)
    invalid.loc[invalid["status"] == ProductDateStatus.OBSERVED.value, "fulfilled_units"] = Decimal(
        "-2"
    )
    with pytest.raises(ValueError, match="must not be negative"):
        prepare_evaluation_series(invalid)


def _calendar_row(
    value: str,
    status: ProductDateStatus,
    fulfilled_units: Decimal | None,
) -> dict[str, object]:
    return {
        "product_key": "id:A",
        "product_id": "A",
        "product_name": "Biscuit",
        "date": pd.Timestamp(value),
        "unit_of_measure": "piece",
        "status": status.value,
        "fulfilled_units": fulfilled_units,
        "returned_units": Decimal("0") if fulfilled_units is not None else None,
        "source_row_count": 1 if status is ProductDateStatus.OBSERVED else 0,
    }
