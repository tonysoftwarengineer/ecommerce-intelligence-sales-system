import numpy as np
import pandas as pd

DEFAULT_HORIZON = 3
EDGE_TRIM_THRESHOLD_RATIO = 0.2
PARTIAL_MONTH_THRESHOLD_RATIO = 0.01
# Chosen via evaluate_window_sizes() rolling-backtest sweep, not assumed:
# 6 months backtested at 14.2% MAPE vs 12 months at 26.0% MAPE (3-split
# rolling backtest, holdout=2). See src/models/forecast.py verification.
DEFAULT_WINDOW_MONTHS = 6


def partial_months(
    revenue_by_month: pd.Series, threshold_ratio: float = PARTIAL_MONTH_THRESHOLD_RATIO
) -> set:
    """
    Months containing essentially no data at all -- the dataset's boundary
    months (collection started/stopped mid-month) plus early-platform months
    like 2016-12, which holds a single R$10.90 order (2016-11 is missing from
    the data entirely).

    Deliberately a much stricter threshold than trim_edge_artifacts, and they
    answer different questions:
      - trim_edge_artifacts (20%): "would this endpoint distort my line fit?"
        A cautious criterion, only ever applied to the first/last point --
        punching holes mid-series would distort the x-spacing a trend fit
        depends on.
      - partial_months (1%): "does this month have real data to show at all?"
        Applied to every month, so it must not catch genuinely small-but-real
        months. At 20% it would wrongly flag 2016-10 (R$41,234) and 2017-01
        (R$114,197) -- both real months with real orders.

    1% is safe because the data has a ~198x natural gap: the three artifact
    months are all under R$210, the smallest real month is R$41,234.
    """
    threshold = threshold_ratio * revenue_by_month.median()
    return set(revenue_by_month.index[revenue_by_month < threshold])


def trim_edge_artifacts(
    revenue_by_month: pd.Series, threshold_ratio: float = EDGE_TRIM_THRESHOLD_RATIO
) -> pd.Series:
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


def backtest_last_n_months(
    revenue_by_month: pd.Series, holdout: int = 2, window_months: int = DEFAULT_WINDOW_MONTHS
) -> list:
    series = trim_edge_artifacts(revenue_by_month)
    if len(series) <= holdout:
        raise ValueError("Not enough data points for the requested holdout size")

    train = series.iloc[:-holdout]
    test = series.iloc[-holdout:]
    forecast = forecast_linear_trend(
        train, periods_ahead=holdout, trim_edges=False, window_months=window_months
    )

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


def rolling_backtest_error(
    revenue_by_month: pd.Series,
    window_months: int = DEFAULT_WINDOW_MONTHS,
    holdout: int = 2,
    n_splits: int = 3,
) -> dict:
    """
    Runs `n_splits` backtests, each shifted one month further back than the
    last, and pools all the resulting (predicted, actual) pairs into one
    error-metrics calculation. A single 2-month holdout rests on just 2 data
    points; this gives up to n_splits * holdout points instead, so a metric
    reflects more than one lucky/unlucky pair of months.
    """
    series = trim_edge_artifacts(revenue_by_month)
    pooled_results: list = []

    for split in range(n_splits):
        end_idx = len(series) - split
        sub_series = series.iloc[:end_idx]
        if len(sub_series) <= holdout:
            break
        train = sub_series.iloc[:-holdout]
        test = sub_series.iloc[-holdout:]
        forecast = forecast_linear_trend(
            train, periods_ahead=holdout, trim_edges=False, window_months=window_months
        )
        pooled_results.extend(
            {
                "month": str(period),
                "predicted_revenue": forecast[i]["predicted_revenue"],
                "actual_revenue": round(float(actual), 2),
            }
            for i, (period, actual) in enumerate(test.items())
        )

    if not pooled_results:
        raise ValueError("Not enough data points for the requested number of splits")

    metrics = backtest_error_metrics(pooled_results)
    metrics["n_points"] = len(pooled_results)
    return metrics


def evaluate_window_sizes(
    revenue_by_month: pd.Series,
    candidate_windows=(6, 9, 12, 15, None),
    holdout: int = 2,
    n_splits: int = 3,
) -> list:
    """
    Backtests each candidate window size with rolling_backtest_error and
    ranks by MAPE, so the window used in forecast_linear_trend is chosen
    from measured evidence, not assumed.
    """
    results = []
    for window in candidate_windows:
        metrics = rolling_backtest_error(
            revenue_by_month, window_months=window, holdout=holdout, n_splits=n_splits
        )
        results.append(
            {"window_months": window if window is not None else "full_history", **metrics}
        )
    return sorted(results, key=lambda r: r["mape_percent"])
