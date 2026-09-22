"""Profile the Milestone 11A foundation against UCI Online Retail II.

The public workbook is intentionally not committed. Download it from the UCI
repository and pass its local path to this script. The source contains no unit
column, so ``source_item`` is an explicit evaluation-only default; it must not be
interpreted as a real stocking conversion.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import pandas as pd

from src.generic_sales.contracts import RevenueMode
from src.product_demand.calendar import build_product_demand_calendar
from src.product_demand.contracts import ProductDemandAssumptions

REQUIRED_COLUMNS = (
    "Invoice",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
)


def profile_workbook(path: Path, product_limit: int) -> dict[str, object]:
    started = time.perf_counter()
    sheets = pd.read_excel(
        path,
        sheet_name=None,
        usecols=list(REQUIRED_COLUMNS),
        dtype={"Invoice": str, "StockCode": str, "Description": str},
    )
    source = pd.concat(sheets.values(), ignore_index=True)
    source["StockCode"] = source["StockCode"].fillna("").str.strip()
    source["Invoice"] = source["Invoice"].fillna("").str.strip()
    source["Description"] = source["Description"].fillna("").str.strip()
    source["InvoiceDate"] = pd.to_datetime(source["InvoiceDate"], errors="coerce")
    source["Quantity"] = pd.to_numeric(source["Quantity"], errors="coerce")
    workbook_loaded = time.perf_counter()

    usable_identity = source.loc[source["StockCode"] != ""].copy()
    top_products = usable_identity["StockCode"].value_counts().head(product_limit).index.tolist()
    sample = usable_identity.loc[usable_identity["StockCode"].isin(top_products)].copy()
    sample = sample.dropna(subset=["InvoiceDate", "Quantity"])
    cancelled = sample["Invoice"].str.startswith("C", na=False)
    canonical = pd.DataFrame(
        {
            "source_row": sample.index + 2,
            "product_id": sample["StockCode"],
            "product_name": sample["Description"],
            "quantity": sample["Quantity"],
            "returned_quantity": None,
            "order_status": cancelled.map({True: "cancelled", False: "completed"}),
            "order_date": sample["InvoiceDate"],
            "recognition_date": sample["InvoiceDate"],
        }
    ).reset_index(drop=True)

    # The public source has no proof of complete daily exports or stockout
    # tracking. Keeping both confirmations false should produce limited, not
    # decision-ready, series and should preserve absent dates as unknown.
    assumptions = ProductDemandAssumptions(default_unit_of_measure="source_item")
    foundation_started = time.perf_counter()
    result = build_product_demand_calendar(
        canonical,
        RevenueMode.ROW_TOTAL,
        assumptions,
    )
    foundation_finished = time.perf_counter()
    status_counts = Counter(result.calendar["status"])
    readiness_counts = Counter(product.status.value for product in result.readiness.products)
    reason_counts = Counter(
        reason.value for product in result.readiness.products for reason in product.reason_codes
    )
    unavailable_examples = [
        {
            "product_id": product.product_id,
            "reason_codes": [reason.value for reason in product.reason_codes],
        }
        for product in result.readiness.products
        if product.status.value == "unavailable"
    ][:10]
    elapsed = time.perf_counter() - started

    assert len(source) >= 1_000_000
    assert usable_identity["StockCode"].nunique() >= 1_000
    assert not result.calendar.empty
    assert status_counts["missing_unknown"] > 0

    return {
        "source": "UCI Online Retail II",
        "worksheets": list(sheets),
        "source_rows": len(source),
        "distinct_product_codes": int(usable_identity["StockCode"].nunique()),
        "rows_without_product_code": int((source["StockCode"] == "").sum()),
        "negative_quantity_rows": int((source["Quantity"] < 0).sum()),
        "cancellation_rows": int(source["Invoice"].str.startswith("C", na=False).sum()),
        "negative_non_cancellation_rows": int(
            ((source["Quantity"] < 0) & ~source["Invoice"].str.startswith("C", na=False)).sum()
        ),
        "profiled_products": len(result.readiness.products),
        "profiled_source_rows": len(canonical),
        "readiness_counts": dict(readiness_counts),
        "readiness_reason_counts": dict(reason_counts),
        "unavailable_product_examples": unavailable_examples,
        "calendar_rows": len(result.calendar),
        "calendar_status_counts": dict(status_counts),
        "workbook_load_seconds": round(workbook_loaded - started, 3),
        "foundation_seconds": round(foundation_finished - foundation_started, 3),
        "elapsed_seconds": round(elapsed, 3),
        "interpretation": (
            "This source lacks unit, stockout, and export-completeness evidence. "
            "The foundation should therefore keep these product series limited and "
            "preserve absent dates as unknown."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--product-limit", type=int, default=25)
    args = parser.parse_args()
    if args.product_limit <= 0:
        parser.error("--product-limit must be positive")
    report = profile_workbook(args.workbook, args.product_limit)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
