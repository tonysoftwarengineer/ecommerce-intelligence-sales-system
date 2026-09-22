"""Research-only DataCo adapter for the frozen product-demand holdout."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from decimal import Decimal

import pandas as pd

from src.product_demand.contracts import ProductDateStatus
from src.product_demand.evaluation_contracts import EvaluationSeries, EvaluationSeriesPoint
from src.product_demand.public_data_evaluation import (
    PublicDatasetPreparation,
    PublicProductProfile,
)

SOURCE_COLUMNS = (
    "order_date_(DateOrders)",
    "Order_Id",
    "Order_Customer_Id",
    "Order_Item_Id",
    "Product_Card_Id",
    "Order_Item_Quantity",
    "Order_Status",
)
HOLDOUT_DAYS = 13 * 7


def prepare_dataco_public_holdout(source: pd.DataFrame) -> PublicDatasetPreparation:
    """Forecast the documented COMPLETE-label quantity, never inferred demand.

    Absent days are zero only in this explicitly research-only view. The source
    does not establish complete open-day exports or stockout tracking.
    """
    missing = sorted(set(SOURCE_COLUMNS) - set(source.columns))
    if missing:
        raise ValueError(f"DataCo source is missing required columns: {missing}")
    rows = source.loc[:, list(SOURCE_COLUMNS)].copy(deep=True)
    for column in SOURCE_COLUMNS:
        rows[column] = rows[column].fillna("").astype(str).str.strip()
    dates = pd.to_datetime(rows["order_date_(DateOrders)"], format="mixed", errors="coerce")
    quantities = pd.to_numeric(rows["Order_Item_Quantity"], errors="coerce")
    completed = rows["Order_Status"].eq("COMPLETE")
    invalid_completed = completed & (
        dates.isna()
        | rows["Product_Card_Id"].eq("")
        | quantities.isna()
        | quantities.le(0)
        | quantities.mod(1).ne(0)
        | rows["Order_Item_Id"].eq("")
    )
    if invalid_completed.any():
        raise ValueError("Completed-label rows contain unsafe dates, IDs, or quantities")
    completed_items = rows.loc[completed].copy()
    if completed_items["Order_Item_Id"].duplicated().any():
        raise ValueError("Completed-label order item IDs are not unique")
    if completed_items.empty or dates.isna().all():
        raise ValueError("No safe completed-label rows are available")

    completed_items["_date"] = dates.loc[completed].dt.date
    completed_items["_quantity"] = quantities.loc[completed].astype("int64")
    last_date = dates.max().date()
    holdout_start = last_date - timedelta(days=HOLDOUT_DAYS - 1)
    daily = completed_items.groupby(["Product_Card_Id", "_date"], sort=True)["_quantity"].sum()
    series: list[EvaluationSeries] = []
    profiles: list[PublicProductProfile] = []
    strict_unknown_days = 0
    strata: Counter[str] = Counter()

    for product_id, product_days in daily.groupby(level=0, sort=True):
        source_id = str(product_id)
        by_date = product_days.droplevel(0)
        first_date = by_date.index.min()
        dates_for_product = pd.date_range(first_date, last_date, freq="D").date
        training_dates = [day for day in dates_for_product if day < holdout_start]
        training_nonzero = sum(bool(by_date.get(day, 0) > 0) for day in training_dates)
        ratio = (
            Decimal(training_nonzero) / Decimal(len(training_dates))
            if training_dates
            else Decimal("0")
        )
        stratum = (
            "new_in_holdout"
            if not training_dates
            else "sparse"
            if ratio <= Decimal("0.1")
            else "intermittent"
            if ratio <= Decimal("0.5")
            else "dense"
        )
        strata[stratum] += 1
        points = tuple(
            EvaluationSeriesPoint(
                date=day,
                status=(
                    ProductDateStatus.OBSERVED
                    if by_date.get(day, 0) > 0
                    else ProductDateStatus.CONFIRMED_ZERO
                ),
                target_units=Decimal(int(by_date.get(day, 0))),
                included=True,
            )
            for day in dates_for_product
        )
        nonzero_days = sum(
            point.target_units is not None and point.target_units > 0 for point in points
        )
        strict_unknown_days += len(points) - nonzero_days
        key = f"dataco:{source_id}"
        series.append(EvaluationSeries(key, "source_item", points))
        profiles.append(
            PublicProductProfile(
                product_key=key,
                source_id=source_id,
                stratum=stratum,
                first_date=first_date,
                calendar_days=len(points),
                nonzero_days=nonzero_days,
                zero_target_days=len(points) - nonzero_days,
                observed_days=nonzero_days,
                confirmed_zero_days=len(points) - nonzero_days,
            )
        )

    evidence = {
        "all_source_rows": len(rows),
        "completed_label_rows": int(completed.sum()),
        "other_status_rows": int((~completed).sum()),
        "invalid_date_rows": int(dates.isna().sum()),
        "missing_customer_id_rows": int(rows["Order_Customer_Id"].eq("").sum()),
        "strict_missing_unknown_product_days": strict_unknown_days,
        **{f"products_{name}": count for name, count in sorted(strata.items())},
    }
    return PublicDatasetPreparation(
        dataset_name="DataCo SMART Supply Chain",
        evaluation_mode="research_only_completed_label_complete_ledger_assumption",
        source_row_count=len(rows),
        source_product_count=int(rows["Product_Card_Id"].replace("", pd.NA).nunique()),
        selected_source_ids=tuple(profile.source_id for profile in profiles),
        series=tuple(series),
        profiles=tuple(profiles),
        evidence_counts=evidence,
        assumptions=(
            "Only rows marked COMPLETE count toward the target; other status meanings "
            "are not inferred.",
            "Absent completed-label product-days are zero only in the research view.",
            "Order item quantity is measured in source items, not a confirmed stocking unit.",
        ),
        limitations=(
            "Open-day completeness, stockouts, and the meaning of other final-looking "
            "statuses are unverified.",
            "This is a global supply-chain source, not an independent small online retailer.",
            "The public mirror's byte identity with the publisher's original file has "
            "not been established.",
        ),
    )
