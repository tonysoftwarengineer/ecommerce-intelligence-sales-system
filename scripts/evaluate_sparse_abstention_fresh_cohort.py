"""Score the predeclared Milestone 11B-5 sparse-abstention protocol."""

from __future__ import annotations

import json
import time
from pathlib import Path

from scripts.compare_product_demand_sparse_policies import (
    HOLDOUT_WEEKS,
    evaluate_series,
    policy_summary,
)
from src.product_demand.public_data_evaluation import (
    file_sha256,
    load_m5_public_evaluation,
)

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "data/public"
SEED = "milestone-11b-sparse-abstention-v1"
PER_STRATUM = 12


def _scope(
    products: list[dict], *, stratum: str | None = None, training_sparse: bool | None = None
) -> list[dict]:
    return [
        product
        for product in products
        if (stratum is None or product["descriptive_sample_stratum"] == stratum)
        and (training_sparse is None or product["decision"]["training_sparse"] is training_sparse)
    ]


def _summaries(products: list[dict], policy: str) -> dict:
    strata = sorted({product["descriptive_sample_stratum"] for product in products})
    return {
        "overall": policy_summary(products, policy),
        "by_stratum": {
            stratum: policy_summary(_scope(products, stratum=stratum), policy) for stratum in strata
        },
        "by_training_group": {
            "sparse": policy_summary(_scope(products, training_sparse=True), policy),
            "non_sparse": policy_summary(_scope(products, training_sparse=False), policy),
        },
        "removed_control_forecasts": policy_summary(products, policy, removed=True),
    }


def _gate(current: dict, candidate: dict, products: list[dict]) -> dict:
    reasons: list[str] = []
    inconclusive: list[str] = []
    non_sparse_unchanged = all(
        product["decision"]["permissions"]["current_control"]
        == product["decision"]["permissions"]["sparse_abstention"]
        for product in products
        if not product["decision"]["training_sparse"]
    )
    if not non_sparse_unchanged:
        reasons.append("non_sparse_permission_changed")

    overall = candidate["overall"]
    if overall["shown_weeks"] == 0:
        inconclusive.append("candidate_showed_no_forecasts")
    elif overall["skill_vs_zero_percent"] is None or overall["skill_vs_zero_percent"] <= 0:
        reasons.append("candidate_did_not_beat_zero_overall")

    for stratum, evidence in candidate["by_stratum"].items():
        if evidence["shown_weeks"] and (
            evidence["skill_vs_zero_percent"] is None or evidence["skill_vs_zero_percent"] <= 0
        ):
            reasons.append(f"candidate_did_not_beat_zero_in_{stratum}")

    removed = candidate["removed_control_forecasts"]
    if removed["shown_weeks"] == 0:
        inconclusive.append("current_policy_showed_no_sparse_forecasts_to_challenge")
    elif removed["skill_vs_zero_percent"] is not None and removed["skill_vs_zero_percent"] > 0:
        reasons.append("candidate_removed_sparse_forecasts_that_beat_zero")

    # The candidate must only remove; this also protects selected-method identity.
    method_identity_preserved = all(
        product["decision"]["selected_method"] is None
        or product["decision"]["permissions"]["current_control"]
        for product in products
    )
    if not method_identity_preserved:
        reasons.append("selected_method_without_current_permission")

    status = "failed" if reasons else "inconclusive" if inconclusive else "passed"
    return {
        "status": status,
        "failure_reasons": reasons,
        "inconclusive_reasons": inconclusive,
        "non_sparse_permission_identity": non_sparse_unchanged,
        "method_identity_preserved": method_identity_preserved,
        "current_control_coverage_percent": current["overall"]["coverage_percent"],
        "candidate_coverage_percent": candidate["overall"]["coverage_percent"],
    }


def build_report() -> dict:
    started = time.perf_counter()
    development_report = json.loads((PUBLIC / "product_demand_public_evaluation.json").read_text())
    locked_report = json.loads((PUBLIC / "product_demand_locked_evaluation.json").read_text())
    development_ids = {product["source_id"] for product in development_report["m5"]["products"]}
    locked_ids = set(locked_report["cohort"]["locked_source_ids"])
    previously_scored = development_ids | locked_ids
    assert len(development_ids) == 24
    assert len(locked_ids) == 48
    assert development_ids.isdisjoint(locked_ids)

    sales = PUBLIC / "m5_sales_train_evaluation.csv"
    calendar = PUBLIC / "m5_calendar.csv"
    hashes = {"m5_sales": file_sha256(sales), "m5_calendar": file_sha256(calendar)}
    assert hashes == locked_report["source_sha256"]
    preparation = load_m5_public_evaluation(
        sales,
        calendar,
        per_stratum=PER_STRATUM,
        sample_seed=SEED,
        excluded_source_ids=frozenset(previously_scored),
    )
    fresh_ids = set(preparation.selected_source_ids)
    assert len(fresh_ids) == 48
    assert fresh_ids.isdisjoint(previously_scored)
    profiles = {profile.product_key: profile for profile in preparation.profiles}

    products = []
    for series in preparation.series:
        result = evaluate_series(series)
        result["source_id"] = profiles[series.product_key].source_id
        result["descriptive_sample_stratum"] = profiles[series.product_key].stratum
        products.append(result)
        print(f"Evaluated fresh product {len(products)}/48", flush=True)

    current = _summaries(products, "current_control")
    candidate = _summaries(products, "sparse_abstention")
    gate = _gate(current, candidate, products)
    elapsed = (time.perf_counter() - started) * 1000
    return {
        "scope": (
            "Fresh disjoint-product and future-time M5 validation of one predeclared "
            "sparse-abstention candidate; not independent-business or release approval."
        ),
        "protocol": {
            "name": "milestone-11b-5-sparse-abstention-v1",
            "locked_before_scoring": True,
            "sample_seed": SEED,
            "products_per_descriptive_stratum": PER_STRATUM,
            "holdout_weeks_per_product": HOLDOUT_WEEKS,
            "training_sparse_max_positive_day_fraction": "0.1",
        },
        "lineage": {
            "source_sha256": hashes,
            "development_product_count": len(development_ids),
            "previously_locked_product_count": len(locked_ids),
            "fresh_product_count": len(fresh_ids),
            "overlap_with_previously_scored": len(fresh_ids & previously_scored),
            "fresh_source_ids": sorted(fresh_ids),
        },
        "training_sparse_product_count": sum(
            product["decision"]["training_sparse"] for product in products
        ),
        "current_control": current,
        "sparse_abstention_candidate": candidate,
        "predeclared_gate": gate,
        "products": products,
        "supported_use_approved": False,
        "elapsed_ms": round(elapsed, 3),
    }


def main() -> None:
    report = build_report()
    output = PUBLIC / "product_demand_sparse_abstention_fresh_validation.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "training_sparse_product_count": report["training_sparse_product_count"],
                "current_control": report["current_control"],
                "sparse_abstention_candidate": report["sparse_abstention_candidate"],
                "predeclared_gate": report["predeclared_gate"],
            },
            indent=2,
        )
    )
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
