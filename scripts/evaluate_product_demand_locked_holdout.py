"""Run the predeclared Milestone 11B-4 locked M5 holdout protocol."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd

from src.product_demand.locked_evaluation import (
    evaluate_locked_holdout,
    locked_evaluation_to_dict,
)
from src.product_demand.public_data_evaluation import (
    file_sha256,
    prepare_m5_public_evaluation,
)

DEVELOPMENT_SEED = "milestone-11b-public-v1"
LOCKED_SEED = "milestone-11b-locked-v1"
DEVELOPMENT_PER_STRATUM = 6
LOCKED_PER_STRATUM = 12


def build_report(sales_path: Path, calendar_path: Path) -> dict[str, object]:
    started = time.perf_counter()
    header = pd.read_csv(sales_path, nrows=0).columns.tolist()
    day_columns = [column for column in header if str(column).startswith("d_")]
    sales = pd.read_csv(sales_path, dtype={column: "int32" for column in day_columns})
    calendar = pd.read_csv(calendar_path, usecols=["d", "date"])
    loaded = time.perf_counter()

    development = prepare_m5_public_evaluation(
        sales,
        calendar,
        per_stratum=DEVELOPMENT_PER_STRATUM,
        sample_seed=DEVELOPMENT_SEED,
    )
    locked = prepare_m5_public_evaluation(
        sales,
        calendar,
        per_stratum=LOCKED_PER_STRATUM,
        sample_seed=LOCKED_SEED,
        excluded_source_ids=frozenset(development.selected_source_ids),
    )
    prepared = time.perf_counter()
    result = evaluate_locked_holdout(locked, development.selected_source_ids)
    evaluated = time.perf_counter()
    report = locked_evaluation_to_dict(result)
    report["protocol"] = {
        "name": "milestone-11b-4-locked-m5-v1",
        "locked_before_scoring": True,
        "development_seed": DEVELOPMENT_SEED,
        "locked_seed": LOCKED_SEED,
        "development_products_per_stratum": DEVELOPMENT_PER_STRATUM,
        "locked_products_per_stratum": LOCKED_PER_STRATUM,
    }
    report["source_sha256"] = {
        "m5_sales": file_sha256(sales_path),
        "m5_calendar": file_sha256(calendar_path),
    }
    report["latency_ms"] = {
        "source_loading": round((loaded - started) * 1000, 3),
        "cohort_preparation": round((prepared - loaded) * 1000, 3),
        "locked_evaluation": round((evaluated - prepared) * 1000, 3),
        "total_before_serialization": round((evaluated - started) * 1000, 3),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--m5-sales", type=Path, required=True)
    parser.add_argument("--m5-calendar", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.m5_sales, args.m5_calendar)
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output is None:
        print(payload)
    else:
        args.output.write_text(f"{payload}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
