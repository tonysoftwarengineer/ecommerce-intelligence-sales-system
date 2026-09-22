"""Development-only sparse-policy comparison. Never imported by the live API."""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pandas as pd

from src.product_demand.baselines import BaselineUnavailableError, forecast_baseline
from src.product_demand.contracts import (
    ProductDemandAvailability,
    ProductDemandProductReadiness,
    ProductIdentitySource,
)
from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    EvaluationConfiguration,
    EvaluationSeries,
    ProductEvaluationReport,
)
from src.product_demand.metrics import evaluate_product_baselines
from src.product_demand.public_data_evaluation import (
    file_sha256,
    prepare_m5_public_evaluation,
)
from src.product_demand.trust_gate import assess_weekly_zero_skill
from src.product_demand.trust_policy import assess_product_demand_trust

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "data/public"
POLICIES = ("current_control", "sparse_consistency", "sparse_abstention")
WEEKLY_CANDIDATES = (
    BaselineCandidate.ZERO,
    BaselineCandidate.LAST_WEEK_TOTAL,
    BaselineCandidate.MEAN_4_WEEKLY_TOTALS,
    BaselineCandidate.SBA_CROSTON,
)
HOLDOUT_WEEKS = 13
BLOCK_WEEKS = 13
BLOCK_COUNT = 3


def training_sparse(history: EvaluationSeries) -> bool:
    if any(not p.included or p.target_units is None for p in history.points):
        raise ValueError("Sparse classification requires complete known training targets")
    positive = sum(p.target_units > 0 for p in history.points if p.target_units is not None)
    return positive * 10 <= len(history.points)


def block_evidence(pairs: list[tuple[Decimal, Decimal]]) -> dict:
    """Input pairs are chronological (selected absolute error, zero absolute error)."""
    required = BLOCK_WEEKS * BLOCK_COUNT
    if len(pairs) < required:
        return {"passed": False, "reason": "insufficient_consistency_weeks", "blocks": []}
    recent = pairs[-required:]
    blocks = []
    for offset in range(0, required, BLOCK_WEEKS):
        block = recent[offset : offset + BLOCK_WEEKS]
        selected = sum((pair[0] for pair in block), Decimal(0))
        zero = sum((pair[1] for pair in block), Decimal(0))
        passed = zero > 0 and selected < zero
        blocks.append(
            {
                "selected_absolute_error": str(selected),
                "zero_absolute_error": str(zero),
                "passed": passed,
            }
        )
    passed = all(block["passed"] for block in blocks)
    return {
        "passed": passed,
        "reason": None if passed else "inconsistent_block_skill",
        "blocks": blocks,
    }


def report_consistency(report: ProductEvaluationReport) -> dict:
    selected = report.seven_day_winner
    if selected is None:
        return block_evidence([])
    by_candidate = {
        evaluation.candidate.candidate: {fold.forecast_dates: fold for fold in evaluation.folds}
        for evaluation in report.candidate_evaluations
    }
    selected_folds = by_candidate.get(selected, {})
    zero_folds = by_candidate.get(BaselineCandidate.ZERO, {})
    shared = sorted(set(selected_folds).intersection(zero_folds))
    pairs = []
    for dates in shared:
        fold = selected_folds[dates]
        actual = sum(fold.actual_daily_units, Decimal(0))
        pairs.append(
            (
                abs(fold.predicted_total_units - actual),
                abs(zero_folds[dates].predicted_total_units - actual),
            )
        )
    return block_evidence(pairs)


def initial_decisions(history: EvaluationSeries) -> dict:
    """Only training enters this function; no future targets or sample stratum."""
    report = evaluate_product_baselines(history, EvaluationConfiguration(), WEEKLY_CANDIDATES)
    readiness = ProductDemandProductReadiness(
        product_key=history.product_key,
        product_id=history.product_key,
        product_name=None,
        identity_source=ProductIdentitySource.PRODUCT_ID,
        unit_of_measure=history.unit_of_measure,
        status=ProductDemandAvailability.READY,
        reason_codes=(),
        explanations=(),
    )
    trust = assess_product_demand_trust(readiness, report, assess_weekly_zero_skill(report))
    sparse = training_sparse(history)
    consistency = report_consistency(report)
    current = trust.numeric_forecast_allowed
    permissions = {
        "current_control": current,
        "sparse_consistency": current and (not sparse or consistency["passed"]),
        "sparse_abstention": current and not sparse,
    }
    return {
        "training_sparse": sparse,
        "selected_method": (
            trust.selected_candidate.value if current and trust.selected_candidate else None
        ),
        "shared_historical_weeks": trust.shared_fold_count,
        "historical_skill_vs_zero": str(trust.skill_vs_zero)
        if trust.skill_vs_zero is not None
        else None,
        "current_policy_reasons": [r.value for r in trust.policy_reasons],
        "consistency": consistency,
        "permissions": permissions,
    }


def evaluate_series(series: EvaluationSeries) -> dict:
    split = len(series.points) - HOLDOUT_WEEKS * 7
    if split <= 0:
        raise ValueError("Insufficient history before development validation")
    history = EvaluationSeries(series.product_key, series.unit_of_measure, series.points[:split])
    decision = initial_decisions(history)
    candidate = (
        BaselineCandidate(decision["selected_method"]) if decision["selected_method"] else None
    )
    outcomes = []
    for week in range(HOLDOUT_WEEKS):
        start = split + week * 7
        history = EvaluationSeries(
            series.product_key, series.unit_of_measure, series.points[:start]
        )
        actual_points = series.points[start : start + 7]
        if any(not p.included or p.target_units is None for p in actual_points):
            raise ValueError("Development validation contains unknown targets")
        prediction = None
        reason = None
        if candidate is not None:
            try:
                forecast = forecast_baseline(history, candidate)
                assert forecast.forecast_dates == tuple(p.date for p in actual_points)
                prediction = str(forecast.predicted_total_units)
            except BaselineUnavailableError:
                reason = "final_forecast_unavailable"
        actual = sum(
            (p.target_units for p in actual_points if p.target_units is not None), Decimal(0)
        )
        outcomes.append(
            {
                "week": week + 1,
                "actual": str(actual),
                "prediction": prediction,
                "forecast_failure": reason,
            }
        )
    return {
        "product_key": series.product_key,
        "training_end": series.points[split - 1].date.isoformat(),
        "decision": decision,
        "outcomes": outcomes,
    }


def summarize(pairs: list[tuple[Decimal, Decimal]], opportunities: int) -> dict:
    """Score only shown forecasts; abstention is not a zero prediction."""
    actual = sum((pair[1] for pair in pairs), Decimal(0))
    errors = [prediction - observed for prediction, observed in pairs]
    absolute = sum((abs(error) for error in errors), Decimal(0))
    return {
        "opportunities": opportunities,
        "shown_weeks": len(pairs),
        "coverage_percent": 100 * len(pairs) / opportunities if opportunities else 0,
        "mae": float(absolute / len(pairs)) if pairs else None,
        "wape_percent": float(100 * absolute / actual) if pairs and actual else None,
        "skill_vs_zero_percent": float(100 * (1 - absolute / actual)) if pairs and actual else None,
        "overforecast_units": str(sum((e for e in errors if e > 0), Decimal(0))),
        "underforecast_units": str(sum((-e for e in errors if e < 0), Decimal(0))),
    }


def policy_summary(products: list[dict], policy: str, *, removed: bool = False) -> dict:
    pairs = []
    for product in products:
        permissions = product["decision"]["permissions"]
        included = (
            permissions["current_control"] and not permissions[policy]
            if removed
            else permissions[policy]
        )
        if included:
            for outcome in product["outcomes"]:
                if outcome["prediction"] is not None:
                    pairs.append((Decimal(outcome["prediction"]), Decimal(outcome["actual"])))
    return summarize(pairs, len(products) * HOLDOUT_WEEKS)


def build_report() -> dict:
    previous = json.loads((PUBLIC / "product_demand_public_evaluation.json").read_text())
    # Read locked membership only for exclusion auditing; never consume its scores.
    locked_ids = set(
        json.loads((PUBLIC / "product_demand_locked_evaluation.json").read_text())["cohort"][
            "locked_source_ids"
        ]
    )
    development_ids = {p["source_id"] for p in previous["m5"]["products"]}
    assert len(development_ids) == 24 and development_ids.isdisjoint(locked_ids)
    paths = {
        "m5_sales": PUBLIC / "m5_sales_train_evaluation.csv",
        "m5_calendar": PUBLIC / "m5_calendar.csv",
    }
    hashes = {key: file_sha256(path) for key, path in paths.items()}
    assert all(hashes[key] == previous["sources"][key]["sha256"] for key in paths)
    header = pd.read_csv(paths["m5_sales"], nrows=0).columns
    dtypes = {column: "int32" for column in header if column.startswith("d_")}
    selected_chunks = []
    for chunk in pd.read_csv(paths["m5_sales"], dtype=dtypes, chunksize=2000):
        selected_chunks.append(chunk.loc[chunk["id"].isin(development_ids)].copy())
    sales = pd.concat(selected_chunks, ignore_index=True)
    assert set(sales["id"]) == development_ids
    calendar = pd.read_csv(paths["m5_calendar"], usecols=["d", "date"])
    preparation = prepare_m5_public_evaluation(sales, calendar, per_stratum=6)
    assert set(preparation.selected_source_ids) == development_ids
    profiles = {p.product_key: p for p in preparation.profiles}
    products = []
    for series in preparation.series:
        product = evaluate_series(series)
        product["descriptive_sample_stratum"] = profiles[series.product_key].stratum
        products.append(product)
        print(f"Evaluated development product {len(products)}/24", flush=True)
    summaries = {}
    for policy in POLICIES:
        summaries[policy] = {
            "overall": policy_summary(products, policy),
            "by_training_group": {
                group: policy_summary(
                    [p for p in products if p["decision"]["training_sparse"] == flag], policy
                )
                for group, flag in (("sparse", True), ("non_sparse", False))
            },
            "removed_control_forecasts": policy_summary(products, policy, removed=True),
        }
    return {
        "scope": (
            "Development-only comparison on previously used products; "
            "NOT untouched validation or release approval."
        ),
        "protocol": "2026-09-15 sparse-policy-comparison-v1",
        "configuration": {
            "development_validation_weeks": HOLDOUT_WEEKS,
            "sparse_nonzero_day_max_fraction": "0.1",
            "consistency_blocks": BLOCK_COUNT,
            "weeks_per_block": BLOCK_WEEKS,
        },
        "lineage": {
            "source_sha256": hashes,
            "development_source_ids": sorted(development_ids),
            "locked_overlap_count": 0,
        },
        "training_group_product_counts": dict(
            Counter(
                "sparse" if p["decision"]["training_sparse"] else "non_sparse" for p in products
            )
        ),
        "policies": summaries,
        "products": products,
        "category_fallback": {
            "comparative_accuracy": "not_evaluated",
            "reason": "Sampled products do not establish complete business-category membership.",
        },
        "supported_use_approved": False,
    }


def main() -> None:
    report = build_report()
    output = PUBLIC / "product_demand_sparse_policy_comparison.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["policies"], indent=2))
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
