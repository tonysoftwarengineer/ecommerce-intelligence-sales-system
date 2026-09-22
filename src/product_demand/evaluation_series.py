"""Prepare auditable product calendars for baseline evaluation."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd

from src.product_demand.contracts import ProductDateStatus
from src.product_demand.evaluation_contracts import EvaluationSeries, EvaluationSeriesPoint

REQUIRED_CALENDAR_COLUMNS = frozenset(
    {
        "product_key",
        "date",
        "unit_of_measure",
        "status",
        "fulfilled_units",
    }
)


def prepare_evaluation_series(calendar: pd.DataFrame) -> tuple[EvaluationSeries, ...]:
    """Convert a calendar DataFrame without filling or compressing excluded dates."""
    missing_columns = sorted(REQUIRED_CALENDAR_COLUMNS - set(calendar.columns))
    if missing_columns:
        raise ValueError(f"Product calendar is missing required columns: {missing_columns}")
    if calendar.empty:
        return ()

    source = calendar.copy(deep=True)
    source["_product_key"] = source["product_key"].map(_required_text)
    source["_date"] = source["date"].map(_calendar_date)
    source["_unit"] = source["unit_of_measure"].map(_required_text)
    source["_status"] = source["status"].map(_calendar_status)
    source = source.sort_values(["_product_key", "_date"], kind="stable")

    prepared: list[EvaluationSeries] = []
    for product_key, rows in source.groupby("_product_key", sort=True):
        units = tuple(dict.fromkeys(rows["_unit"].tolist()))
        if len(units) != 1:
            raise ValueError(f"Product {product_key!r} has conflicting units of measure")
        points = tuple(_prepare_point(row) for _, row in rows.iterrows())
        prepared.append(
            EvaluationSeries(
                product_key=str(product_key),
                unit_of_measure=units[0],
                points=points,
            )
        )
    return tuple(prepared)


def _prepare_point(row: pd.Series) -> EvaluationSeriesPoint:
    status = row["_status"]
    included = status in {
        ProductDateStatus.OBSERVED,
        ProductDateStatus.CONFIRMED_ZERO,
    }
    target = _target_units(row["fulfilled_units"]) if included else None
    return EvaluationSeriesPoint(
        date=row["_date"],
        status=status,
        target_units=target,
        included=included,
    )


def _required_text(value: object) -> str:
    if value is None or pd.isna(value):
        raise ValueError("Product key and unit of measure must not be blank")
    result = str(value).strip()
    if not result:
        raise ValueError("Product key and unit of measure must not be blank")
    return result


def _calendar_date(value: object) -> date:
    if value is None or pd.isna(value):
        raise ValueError("Product calendar dates must be valid")
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError("Product calendar dates must be valid")
    return parsed.date()


def _calendar_status(value: object) -> ProductDateStatus:
    try:
        return ProductDateStatus(str(value))
    except ValueError:
        raise ValueError(f"Unknown product calendar status: {value!r}") from None


def _target_units(value: object) -> Decimal:
    if value is None or isinstance(value, bool) or pd.isna(value):
        raise ValueError("Included product calendar targets must be numeric")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Included product calendar targets must be numeric") from None
    if not result.is_finite():
        raise ValueError("Included product calendar targets must be finite")
    if result < 0:
        raise ValueError("Included product calendar targets must not be negative")
    return result
