from collections.abc import Sequence

import pandas as pd

from src.generic_sales.forecasting import forecast_generic_revenue


def monthly(values: Sequence[float], start: str = "2025-01") -> pd.Series:
    return pd.Series(values, index=pd.period_range(start, periods=len(values), freq="M"))


def test_fewer_than_six_complete_months_is_unavailable() -> None:
    result = forecast_generic_revenue(monthly([10, 20, 30, 40, 50]), True)

    assert result["status"] == "unavailable"
    assert result["forecast"] == []


def test_six_month_forecast_is_experimental_and_selects_best_backtest_model() -> None:
    result = forecast_generic_revenue(monthly([10, 20, 30, 40, 50, 60]), True)

    assert result["status"] == "experimental"
    assert result["horizon"] == 1
    assert result["selected_model"] == "linear_trend"
    assert result["backtest_folds"] == 3
    assert result["trust_level"] == "limited"
    assert result["selection_reason"] == (
        "Chosen because it had the lowest mean error among 3 eligible methods across 3 "
        "rolling historical tests."
    )
    assert {evaluation["model"] for evaluation in result["model_evaluations"]} == {
        "latest_month",
        "linear_trend",
        "moving_average_3",
    }
    selected_models = [
        evaluation["model"] for evaluation in result["model_evaluations"] if evaluation["selected"]
    ]
    assert selected_models == ["linear_trend"]
    assert result["forecast"] == [{"month": "2025-07", "predicted_revenue": 70.0}]


def test_naive_baseline_wins_when_more_complex_models_do_not_improve_error() -> None:
    result = forecast_generic_revenue(monthly([100, 100, 100, 100, 100, 100]), True)

    assert result["selected_model"] == "latest_month"
    assert result["backtest_metrics"]["mae"] == 0


def test_twelve_months_allows_three_month_short_term_forecast() -> None:
    result = forecast_generic_revenue(monthly(list(range(10, 130, 10))), True)

    assert result["status"] == "available"
    assert result["horizon"] == 3
    assert result["trust_level"] == "moderate"
    assert len(result["forecast"]) == 3
    assert "Annual seasonality requires" in result["limitations"][0]


def test_repeated_annual_pattern_can_earn_strong_trust_and_select_seasonality() -> None:
    annual_pattern = [100, 120, 140, 160, 180, 200, 180, 160, 140, 120, 100, 80]
    result = forecast_generic_revenue(monthly(annual_pattern * 2), True)

    assert result["selected_model"] == "seasonal_naive_12"
    assert result["trust_level"] == "strong"
    assert result["backtest_metrics"]["wape_percent"] == 0
    assert len(result["model_evaluations"]) == 6


def test_missing_months_block_forecast_instead_of_becoming_zero_sales() -> None:
    series = monthly([10, 20, 30, 40, 50, 60])
    series = series.drop(series.index[2])

    result = forecast_generic_revenue(series, True)

    assert result["status"] == "unavailable"
    assert result["trust_level"] == "unavailable"
    assert result["model_evaluations"] == []
    assert "2025-03" in result["limitations"][0]


def test_incomplete_latest_period_is_excluded_before_eligibility() -> None:
    result = forecast_generic_revenue(monthly([10, 20, 30, 40, 50, 60]), False)

    assert result["status"] == "unavailable"
    assert result["history_periods"] == 5
    assert "latest period was excluded" in result["limitations"][0]
