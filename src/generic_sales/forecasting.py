from collections.abc import Callable
from math import sqrt
from typing import Any, Optional

import numpy as np
import pandas as pd

MIN_EXPERIMENTAL_PERIODS = 6
MIN_STANDARD_PERIODS = 12
SEASONAL_ELIGIBLE_PERIODS = 24

Predictor = Callable[[pd.Series, int], list[float]]


def forecast_generic_revenue(
    monthly_revenue: pd.Series,
    latest_period_complete: bool,
) -> dict[str, Any]:
    """Select a transparent short-term model using rolling-origin backtests."""
    series = monthly_revenue.sort_index().astype(float).copy()
    limitations: list[str] = []

    if not latest_period_complete and not series.empty:
        series = series.iloc[:-1]
        limitations.append("The latest period was excluded because it is incomplete.")

    history_periods = len(series)
    missing_periods = _missing_months(series.index)
    if missing_periods:
        return unavailable_forecast(
            history_periods,
            limitations
            + [
                "Missing monthly periods must be identified as zero sales or missing data: "
                + ", ".join(missing_periods)
            ],
        )
    if history_periods < MIN_EXPERIMENTAL_PERIODS:
        return unavailable_forecast(
            history_periods,
            limitations
            + [f"At least {MIN_EXPERIMENTAL_PERIODS} complete monthly periods are required."],
        )

    experimental = history_periods < MIN_STANDARD_PERIODS
    horizon = 1 if experimental else 3
    min_train = 3 if experimental else 6
    candidate_models = _candidate_models(history_periods)
    evaluations = [
        _backtest_model(series, name, predictor, min_train) for name, predictor in candidate_models
    ]
    eligible = [evaluation for evaluation in evaluations if evaluation is not None]
    if not eligible:
        return unavailable_forecast(
            history_periods,
            limitations + ["Not enough rolling backtest folds were available."],
        )

    selected = min(eligible, key=lambda evaluation: evaluation["mae"])
    predictor = dict(candidate_models)[selected["model"]]
    predictions = predictor(series, horizon)
    last_month = series.index[-1]
    trust_level, trust_message = _trust_assessment(
        experimental=experimental,
        history_periods=history_periods,
        backtest_folds=selected["n_points"],
        wape_percent=selected["wape_percent"],
    )

    if experimental:
        limitations.extend(
            [
                "Limited history: forecast is experimental.",
                "Annual seasonality cannot be evaluated.",
            ]
        )
    elif history_periods < SEASONAL_ELIGIBLE_PERIODS:
        limitations.append("Annual seasonality requires at least 24 complete monthly periods.")

    return {
        "status": "experimental" if experimental else "available",
        "history_periods": history_periods,
        "frequency": "monthly",
        "horizon": horizon,
        "selected_model": selected["model"],
        "baseline_model": "latest_month",
        "backtest_folds": selected["n_points"],
        "backtest_metrics": {
            "mae": selected["mae"],
            "rmse": selected["rmse"],
            "wape_percent": selected["wape_percent"],
        },
        "model_evaluations": [
            _evaluation_response(evaluation, selected["model"]) for evaluation in eligible
        ],
        "selection_reason": (
            "Chosen because it had the lowest mean error among "
            f"{len(eligible)} eligible methods across {selected['n_points']} "
            "rolling historical tests."
        ),
        "trust_level": trust_level,
        "trust_message": trust_message,
        "forecast": [
            {
                "month": str(last_month + step),
                "predicted_revenue": round(max(float(prediction), 0.0), 2),
            }
            for step, prediction in enumerate(predictions, start=1)
        ],
        "limitations": limitations,
    }


def _candidate_models(history_periods: int) -> list[tuple[str, Predictor]]:
    models: list[tuple[str, Predictor]] = [
        ("latest_month", _predict_latest),
        ("linear_trend", _predict_linear),
        ("moving_average_3", lambda series, horizon: _predict_moving_average(series, horizon, 3)),
    ]
    if history_periods >= MIN_STANDARD_PERIODS:
        models.extend(
            [
                (
                    "moving_average_6",
                    lambda series, horizon: _predict_moving_average(series, horizon, 6),
                ),
                (
                    "linear_trend_recent_6",
                    lambda series, horizon: _predict_linear(series.tail(6), horizon),
                ),
            ]
        )
    if history_periods >= SEASONAL_ELIGIBLE_PERIODS:
        models.append(("seasonal_naive_12", _predict_seasonal_12))
    return models


def _backtest_model(
    series: pd.Series,
    model_name: str,
    predictor: Predictor,
    min_train: int,
) -> Optional[dict[str, Any]]:
    origins = list(range(min_train, len(series)))[-6:]
    if len(origins) < 3:
        return None

    errors: list[float] = []
    actuals: list[float] = []
    for origin in origins:
        train = series.iloc[:origin]
        try:
            prediction = predictor(train, 1)[0]
        except ValueError:
            return None
        actual = float(series.iloc[origin])
        errors.append(float(prediction) - actual)
        actuals.append(actual)

    mae = sum(abs(error) for error in errors) / len(errors)
    rmse = sqrt(sum(error**2 for error in errors) / len(errors))
    denominator = sum(abs(actual) for actual in actuals)
    wape = None if denominator == 0 else sum(abs(error) for error in errors) / denominator * 100
    return {
        "model": model_name,
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "wape_percent": None if wape is None else round(wape, 2),
        "n_points": len(errors),
    }


def _evaluation_response(evaluation: dict[str, Any], selected_model: str) -> dict[str, Any]:
    """Return only stable, user-facing model-comparison fields."""
    return {
        "model": evaluation["model"],
        "selected": evaluation["model"] == selected_model,
        "backtest_folds": evaluation["n_points"],
        "metrics": {
            "mae": evaluation["mae"],
            "rmse": evaluation["rmse"],
            "wape_percent": evaluation["wape_percent"],
        },
    }


def _trust_assessment(
    *,
    experimental: bool,
    history_periods: int,
    backtest_folds: int,
    wape_percent: Optional[float],
) -> tuple[str, str]:
    """Give a conservative, deterministic interpretation of forecast evidence."""
    if experimental:
        return (
            "limited",
            "Only 6 to 11 complete months are available. "
            "Use this forecast for exploration, not commitments.",
        )
    if wape_percent is None or backtest_folds < 6:
        return (
            "exploratory",
            "The model was tested, but there is not enough comparable historical "
            "evidence for a stronger trust level.",
        )
    if history_periods >= SEASONAL_ELIGIBLE_PERIODS and wape_percent <= 10:
        return (
            "strong",
            "Historical error was low and annual seasonality was eligible for testing. "
            "This is still an estimate; review known business changes before relying on it.",
        )
    if history_periods >= MIN_STANDARD_PERIODS and wape_percent <= 25:
        return (
            "moderate",
            "The forecast performed reasonably in rolling tests. Use it alongside "
            "business judgment and expected business changes.",
        )
    return (
        "exploratory",
        "The system selected the best tested method, but historical error is still high. "
        "Use this forecast to explore scenarios, not for firm commitments.",
    )


def _predict_latest(series: pd.Series, horizon: int) -> list[float]:
    return [float(series.iloc[-1])] * horizon


def _predict_moving_average(series: pd.Series, horizon: int, window: int) -> list[float]:
    if len(series) < window:
        raise ValueError("Not enough periods for moving average")
    return [float(series.tail(window).mean())] * horizon


def _predict_linear(series: pd.Series, horizon: int) -> list[float]:
    if len(series) < 3:
        raise ValueError("Not enough periods for linear trend")
    x = np.arange(len(series))
    slope, intercept = np.polyfit(x, series.to_numpy(dtype=float), 1)
    return [float(slope * (len(series) - 1 + step) + intercept) for step in range(1, horizon + 1)]


def _predict_seasonal_12(series: pd.Series, horizon: int) -> list[float]:
    if len(series) < 12:
        raise ValueError("Not enough periods for annual seasonal baseline")
    seasonal_values = series.iloc[-12:].tolist()
    return [float(seasonal_values[(step - 1) % 12]) for step in range(1, horizon + 1)]


def _missing_months(index: pd.Index) -> list[str]:
    if len(index) < 2:
        return []
    expected = pd.period_range(index[0], index[-1], freq="M")
    return [str(period) for period in expected.difference(index)]


def unavailable_forecast(history_periods: int, limitations: list[str]) -> dict[str, Any]:
    """Return the stable forecast contract when forecasting must not run."""
    return {
        "status": "unavailable",
        "history_periods": history_periods,
        "frequency": "monthly",
        "horizon": 0,
        "selected_model": None,
        "baseline_model": "latest_month",
        "backtest_folds": 0,
        "backtest_metrics": None,
        "model_evaluations": [],
        "selection_reason": None,
        "trust_level": "unavailable",
        "trust_message": (
            "Forecast unavailable. Review the listed data limitations before trying again."
        ),
        "forecast": [],
        "limitations": limitations,
    }
