"""Generate Milestone 11B-1 Step 7 review evidence from UCI and M5."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from src.product_demand.daily_shape import (
    daily_shape_portfolio_to_dict,
    evaluate_daily_shape_portfolio,
)
from src.product_demand.evaluation_review import (
    review_evidence_to_dict,
    review_public_evaluations,
)
from src.product_demand.history_sensitivity import (
    evaluate_history_sensitivity_portfolio,
    history_sensitivity_portfolio_to_dict,
)
from src.product_demand.public_data_evaluation import (
    evaluate_public_series,
    file_sha256,
    load_m5_public_evaluation,
    load_uci_public_evaluation,
)
from src.product_demand.trust_gate import (
    assess_weekly_zero_skill_portfolio,
    weekly_zero_skill_portfolio_to_dict,
)


def build_review(
    uci_workbook: Path,
    m5_sales: Path,
    m5_calendar: Path,
) -> dict[str, object]:
    started = time.perf_counter()
    uci = load_uci_public_evaluation(uci_workbook)
    uci_reports = evaluate_public_series(uci)
    uci_review = review_public_evaluations(uci, uci_reports)
    uci_finished = time.perf_counter()

    m5 = load_m5_public_evaluation(m5_sales, m5_calendar)
    m5_reports = evaluate_public_series(m5)
    m5_review = review_public_evaluations(m5, m5_reports)
    m5_finished = time.perf_counter()
    uci_payload = review_evidence_to_dict(uci_review)
    uci_payload["weekly_zero_skill_gate"] = weekly_zero_skill_portfolio_to_dict(
        assess_weekly_zero_skill_portfolio(uci_reports)
    )
    uci_payload["daily_shape_comparison"] = daily_shape_portfolio_to_dict(
        evaluate_daily_shape_portfolio(uci_reports)
    )
    uci_payload["history_length_sensitivity"] = history_sensitivity_portfolio_to_dict(
        evaluate_history_sensitivity_portfolio(uci_reports),
        {product.product_key: product.stratum for product in uci_review.products},
    )
    m5_payload = review_evidence_to_dict(m5_review)
    m5_payload["weekly_zero_skill_gate"] = weekly_zero_skill_portfolio_to_dict(
        assess_weekly_zero_skill_portfolio(m5_reports)
    )
    m5_payload["daily_shape_comparison"] = daily_shape_portfolio_to_dict(
        evaluate_daily_shape_portfolio(m5_reports)
    )
    m5_payload["history_length_sensitivity"] = history_sensitivity_portfolio_to_dict(
        evaluate_history_sensitivity_portfolio(m5_reports),
        {product.product_key: product.stratum for product in m5_review.products},
    )
    return {
        "scope": (
            "Milestone 11B-1 architecture-review evidence. It proposes no accepted "
            "production threshold and changes no forecast result."
        ),
        "source_sha256": {
            "uci": file_sha256(uci_workbook),
            "m5_sales": file_sha256(m5_sales),
            "m5_calendar": file_sha256(m5_calendar),
        },
        "latency_ms": {
            "uci_prepare_evaluate_review": round((uci_finished - started) * 1000, 3),
            "m5_prepare_evaluate_review": round((m5_finished - uci_finished) * 1000, 3),
            "total_before_serialization": round((m5_finished - started) * 1000, 3),
        },
        "uci": uci_payload,
        "m5": m5_payload,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uci-workbook", type=Path, required=True)
    parser.add_argument("--m5-sales", type=Path, required=True)
    parser.add_argument("--m5-calendar", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    review = build_review(args.uci_workbook, args.m5_sales, args.m5_calendar)
    payload = json.dumps(review, indent=2, sort_keys=True)
    if args.output is None:
        print(payload)
    else:
        args.output.write_text(f"{payload}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
