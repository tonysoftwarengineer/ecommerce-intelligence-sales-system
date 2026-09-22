"""Run reproducible UCI and M5 public-data evidence for Milestone 11B Step 6."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from src.product_demand.public_data_evaluation import (
    evaluate_public_series,
    file_sha256,
    load_m5_public_evaluation,
    load_uci_public_evaluation,
    public_evaluation_evidence,
)


def build_report(
    uci_workbook: Path,
    m5_sales: Path,
    m5_calendar: Path,
    *,
    uci_product_limit: int = 25,
    m5_per_stratum: int = 6,
) -> dict[str, object]:
    started = time.perf_counter()
    uci_started = time.perf_counter()
    uci = load_uci_public_evaluation(uci_workbook, product_limit=uci_product_limit)
    uci_prepared = time.perf_counter()
    uci_reports = evaluate_public_series(uci)
    uci_evaluated = time.perf_counter()

    m5_started = time.perf_counter()
    m5 = load_m5_public_evaluation(
        m5_sales,
        m5_calendar,
        per_stratum=m5_per_stratum,
    )
    m5_prepared = time.perf_counter()
    m5_reports = evaluate_public_series(m5)
    m5_evaluated = time.perf_counter()

    return {
        "scope": (
            "Public historical evaluation of unchanged transparent baselines. Results are "
            "evaluation-only evidence, not production trust thresholds or proof of future "
            "business performance."
        ),
        "sources": {
            "uci": {
                "name": "UCI Online Retail II",
                "citation": "https://doi.org/10.24432/C5CG6D",
                "sha256": file_sha256(uci_workbook),
                "bytes": uci_workbook.stat().st_size,
            },
            "m5_sales": {
                "name": "M5 sales_train_evaluation.csv",
                "archive": "https://doi.org/10.5281/zenodo.10203108",
                "sha256": file_sha256(m5_sales),
                "bytes": m5_sales.stat().st_size,
            },
            "m5_calendar": {
                "name": "M5 calendar.csv",
                "archive": "https://doi.org/10.5281/zenodo.10203108",
                "sha256": file_sha256(m5_calendar),
                "bytes": m5_calendar.stat().st_size,
            },
        },
        "configuration": {
            "forecast_horizon_days": 7,
            "origin_step_days": 7,
            "minimum_training_days": 28,
            "minimum_folds": 3,
            "uci_product_limit": uci_product_limit,
            "m5_products_per_stratum": m5_per_stratum,
            "m5_sample_seed": "milestone-11b-public-v1",
        },
        "latency_ms": {
            "uci_preparation": round((uci_prepared - uci_started) * 1000, 3),
            "uci_evaluation": round((uci_evaluated - uci_prepared) * 1000, 3),
            "m5_preparation": round((m5_prepared - m5_started) * 1000, 3),
            "m5_evaluation": round((m5_evaluated - m5_prepared) * 1000, 3),
            "total_before_serialization": round((m5_evaluated - started) * 1000, 3),
        },
        "uci": public_evaluation_evidence(uci, uci_reports),
        "m5": public_evaluation_evidence(m5, m5_reports),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uci-workbook", type=Path, required=True)
    parser.add_argument("--m5-sales", type=Path, required=True)
    parser.add_argument("--m5-calendar", type=Path, required=True)
    parser.add_argument("--uci-product-limit", type=int, default=25)
    parser.add_argument("--m5-per-stratum", type=int, default=6)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(
        args.uci_workbook,
        args.m5_sales,
        args.m5_calendar,
        uci_product_limit=args.uci_product_limit,
        m5_per_stratum=args.m5_per_stratum,
    )
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output is None:
        print(payload)
    else:
        args.output.write_text(f"{payload}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
