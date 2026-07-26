import numpy as np
import pandas as pd

DEFAULT_HORIZON = 3
EDGE_TRIM_THRESHOLD_RATIO = 0.2
DEFAULT_WINDOW_MONTHS = 12


def trim_edge_artifacts(revenue_by_month: pd.Series, threshold_ratio: float = EDGE_TRIM_THRESHOLD_RATIO) -> pd.Series:
    series = revenue_by_month.copy()
    threshold = threshold_ratio * series.median()

    if len(series) > 2 and series.iloc[0] < threshold:
        series = series.iloc[1:]
    if len(series) > 2 and series.iloc[-1] < threshold:
        series = series.iloc[:-1]

    return series


def forecast_linear_trend(
    revenue_by_month: pd.Series,
    periods_ahead: int = DEFAULT_HORIZON,
    trim_edges: bool = True,
    window_months: int = DEFAULT_WINDOW_MONTHS,
) -> list:
    series = trim_edge_artifacts(revenue_by_month) if trim_edges else revenue_by_month
    if window_months is not None:
        series = series.tail(window_months)

    x = np.arange(len(series))
    y = series.values.astype(float)
    slope, intercept = np.polyfit(x, y, 1)

    last_period = series.index[-1]
    forecast = []
    for step in range(1, periods_ahead + 1):
        predicted = max(slope * (len(series) - 1 + step) + intercept, 0.0)
        forecast.append(
            {"month": str(last_period + step), "predicted_revenue": round(float(predicted), 2)}
        )
    return forecast


def backtest_last_n_months(revenue_by_month: pd.Series, holdout: int = 2) -> list:
    series = trim_edge_artifacts(revenue_by_month)
    if len(series) <= holdout:
        raise ValueError("Not enough data points for the requested holdout size")

    train = series.iloc[:-holdout]
    test = series.iloc[-holdout:]
    forecast = forecast_linear_trend(train, periods_ahead=holdout, trim_edges=False)

    return [
        {
            "month": str(period),
            "predicted_revenue": forecast[i]["predicted_revenue"],
            "actual_revenue": round(float(actual), 2),
        }
        for i, (period, actual) in enumerate(test.items())
    ]


def backtest_error_metrics(backtest_results: list) -> dict:
    errors = [r["predicted_revenue"] - r["actual_revenue"] for r in backtest_results]
    actuals = [r["actual_revenue"] for r in backtest_results]

    mae = sum(abs(e) for e in errors) / len(errors)
    mse = sum(e**2 for e in errors) / len(errors)
    rmse = mse**0.5
    mape = sum(abs(e) / a for e, a in zip(errors, actuals)) / len(errors) * 100

    return {
        "mae": round(mae, 2),
        "mse": round(mse, 2),
        "rmse": round(rmse, 2),
        "mape_percent": round(mape, 2),
    }
