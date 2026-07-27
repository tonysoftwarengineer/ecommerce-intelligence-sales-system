import pandas as pd
import pytest

from src.models.forecast import (
    DEFAULT_WINDOW_MONTHS,
    backtest_error_metrics,
    forecast_linear_trend,
    rolling_backtest_error,
    trim_edge_artifacts,
)


def months(values, start="2017-01"):
    index = pd.period_range(start=start, periods=len(values), freq="M")
    return pd.Series(values, index=index, dtype="float64")


def test_trim_edge_artifacts_drops_tiny_boundary_months():
    # Olist's collection started and stopped mid-month, leaving near-empty
    # months at both ends. A degree-1 fit is highly sensitive to its endpoints,
    # so those must not reach polyfit.
    series = months([5.0, 1000.0, 1100.0, 1200.0, 3.0])
    trimmed = trim_edge_artifacts(series)

    assert len(trimmed) == 3
    assert trimmed.iloc[0] == 1000.0
    assert trimmed.iloc[-1] == 1200.0


def test_trim_edge_artifacts_keeps_normal_months():
    series = months([1000.0, 1100.0, 1200.0])
    assert len(trim_edge_artifacts(series)) == 3


def test_forecast_projects_a_rising_trend_upward():
    series = months([100.0, 200.0, 300.0, 400.0])
    result = forecast_linear_trend(series, periods_ahead=2, window_months=None)

    assert [r["month"] for r in result] == ["2017-05", "2017-06"]
    assert result[0]["predicted_revenue"] == pytest.approx(500.0, rel=1e-6)
    assert result[1]["predicted_revenue"] == pytest.approx(600.0, rel=1e-6)


def test_forecast_clips_negative_predictions_to_zero():
    # A steep decline extrapolates below zero; revenue cannot be negative.
    series = months([500.0, 400.0, 300.0, 200.0])
    result = forecast_linear_trend(series, periods_ahead=6, window_months=None)

    assert all(r["predicted_revenue"] >= 0 for r in result)
    assert result[-1]["predicted_revenue"] == 0.0


def test_forecast_window_uses_only_recent_months():
    # Steep early growth then a flat plateau. Fit on everything and the stale
    # growth drags the projection up; fit on the recent window and it stays
    # flat. This is the behaviour that took MAPE from 26% to 14%.
    series = months([0.0, 200.0, 400.0, 600.0, 600.0, 600.0, 600.0])

    windowed = forecast_linear_trend(series, periods_ahead=1, window_months=3, trim_edges=False)
    full = forecast_linear_trend(series, periods_ahead=1, window_months=None, trim_edges=False)

    assert windowed[0]["predicted_revenue"] == pytest.approx(600.0, rel=1e-6)
    assert full[0]["predicted_revenue"] > windowed[0]["predicted_revenue"]


def test_default_window_is_the_empirically_chosen_six_months():
    # Chosen by sweeping candidates against a rolling backtest (6mo = 14.2%
    # MAPE vs 12mo = 26.0%). Guards against silently reverting to a guess.
    assert DEFAULT_WINDOW_MONTHS == 6


def test_error_metrics_match_hand_computed_values():
    results = [
        {"month": "2018-01", "predicted_revenue": 110.0, "actual_revenue": 100.0},
        {"month": "2018-02", "predicted_revenue": 80.0, "actual_revenue": 100.0},
    ]
    metrics = backtest_error_metrics(results)

    # errors: +10, -20 -> MAE 15, MSE (100+400)/2 = 250, RMSE sqrt(250).
    # Metrics are rounded to 2dp for JSON output, hence abs= rather than rel=.
    assert metrics["mae"] == pytest.approx(15.0)
    assert metrics["mse"] == pytest.approx(250.0)
    assert metrics["rmse"] == pytest.approx(250.0**0.5, abs=0.01)
    assert metrics["mape_percent"] == pytest.approx(15.0)


def test_rolling_backtest_pools_more_points_than_a_single_split():
    # The whole point of the rolling backtest: a single 2-month holdout rests
    # on 2 data points, which is too thin to conclude anything from.
    series = months(list(range(100, 1300, 100)))
    metrics = rolling_backtest_error(series, window_months=None, holdout=2, n_splits=3)

    assert metrics["n_points"] == 6


def test_backtest_raises_when_holdout_exceeds_available_data():
    with pytest.raises(ValueError):
        rolling_backtest_error(months([100.0, 200.0]), holdout=5)
