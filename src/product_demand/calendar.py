"""Build an auditable product-date calendar without imputing unknown demand."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

from src.generic_sales.contracts import RevenueMode
from src.product_demand.contracts import (
    ProductDateStatus,
    ProductDemandAssumptions,
    ProductDemandAvailability,
    ProductDemandReadinessReport,
)
from src.product_demand.readiness import (
    _decimal,
    assess_product_demand_readiness,
    resolve_product_rows,
)

CALENDAR_COLUMNS = (
    "product_key",
    "product_id",
    "product_name",
    "date",
    "unit_of_measure",
    "status",
    "fulfilled_units",
    "returned_units",
    "source_row_count",
)


@dataclass(frozen=True)
class ProductDemandCalendarResult:
    calendar: pd.DataFrame
    readiness: ProductDemandReadinessReport


def build_product_demand_calendar(
    canonical_data: pd.DataFrame,
    revenue_mode: RevenueMode,
    assumptions: ProductDemandAssumptions,
) -> ProductDemandCalendarResult:
    """Build one regular daily series per usable product's observed lifespan."""
    readiness = assess_product_demand_readiness(canonical_data, revenue_mode, assumptions)
    usable_products = {
        product.product_key: product
        for product in readiness.products
        if product.status is not ProductDemandAvailability.UNAVAILABLE
    }
    if not usable_products:
        return ProductDemandCalendarResult(_empty_calendar(), readiness)

    resolved = resolve_product_rows(canonical_data, assumptions)
    resolved = resolved.loc[resolved["_product_key"].isin(usable_products)].copy()
    date_field = "recognition_date" if "recognition_date" in resolved.columns else "order_date"
    resolved["_demand_date"] = pd.to_datetime(resolved[date_field], errors="coerce").dt.normalize()
    resolved = resolved.dropna(subset=["_demand_date"])

    calendar_rows: list[dict[str, object]] = []
    for product_key, product_rows in resolved.groupby("_product_key", sort=True):
        product = usable_products[str(product_key)]
        first_date = product_rows["_demand_date"].min()
        last_date = product_rows["_demand_date"].max()
        observations = {
            date: rows for date, rows in product_rows.groupby("_demand_date", sort=True)
        }
        for timestamp in pd.date_range(first_date, last_date, freq="D"):
            day = timestamp.date()
            rows = observations.get(timestamp)
            stockout = day in assumptions.stockout_dates.get(str(product_key), frozenset())
            if rows is not None:
                fulfilled, returned = _aggregate_observed_units(rows)
                status = (
                    ProductDateStatus.STOCKOUT_LIMITED if stockout else ProductDateStatus.OBSERVED
                )
                source_row_count = len(rows)
            elif day in assumptions.business_closed_dates:
                status = ProductDateStatus.BUSINESS_CLOSED
                fulfilled = Decimal("0")
                returned = Decimal("0")
                source_row_count = 0
            elif stockout:
                status = ProductDateStatus.STOCKOUT_LIMITED
                fulfilled = Decimal("0")
                returned = Decimal("0")
                source_row_count = 0
            elif assumptions.export_covers_all_open_days:
                status = ProductDateStatus.CONFIRMED_ZERO
                fulfilled = Decimal("0")
                returned = Decimal("0")
                source_row_count = 0
            else:
                status = ProductDateStatus.MISSING_UNKNOWN
                fulfilled = None
                returned = None
                source_row_count = 0

            calendar_rows.append(
                {
                    "product_key": product.product_key,
                    "product_id": product.product_id,
                    "product_name": product.product_name,
                    "date": timestamp,
                    "unit_of_measure": product.unit_of_measure,
                    "status": status.value,
                    "fulfilled_units": fulfilled,
                    "returned_units": returned,
                    "source_row_count": source_row_count,
                }
            )
    calendar = pd.DataFrame(calendar_rows, columns=CALENDAR_COLUMNS)
    return ProductDemandCalendarResult(calendar=calendar, readiness=readiness)


def _aggregate_observed_units(rows: pd.DataFrame) -> tuple[Decimal, Decimal]:
    fulfilled = Decimal("0")
    returned = Decimal("0")
    for _, row in rows.iterrows():
        quantity = _decimal(row.get("quantity")) or Decimal("0")
        returned_quantity = _decimal(row.get("returned_quantity"))
        status = str(row.get("order_status", "completed")).strip().casefold()
        if status == "completed":
            fulfilled += max(quantity, Decimal("0"))
        elif status == "returned":
            if quantity > 0:
                fulfilled += quantity
                returned += abs(returned_quantity if returned_quantity is not None else quantity)
            else:
                returned += abs(returned_quantity if returned_quantity is not None else quantity)
        # Pending and pre-fulfilment cancelled rows contribute zero fulfilled units.
    return fulfilled, returned


def _empty_calendar() -> pd.DataFrame:
    return pd.DataFrame(columns=CALENDAR_COLUMNS)
