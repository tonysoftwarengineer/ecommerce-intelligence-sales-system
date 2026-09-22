"""Development-only comparison for the predeclared global consistency rule."""

from __future__ import annotations

import json

from scripts.compare_product_demand_sparse_policies import (
    PUBLIC,
    policy_summary,
)
from scripts.compare_product_demand_sparse_policies import (
    build_report as build_development_report,
)

OUTPUT = PUBLIC / "product_demand_global_consistency_development.json"


def _scope(products: list[dict], stratum: str) -> list[dict]:
    return [product for product in products if product["descriptive_sample_stratum"] == stratum]


def _summary(products: list[dict], policy: str) -> dict:
    strata = sorted({product["descriptive_sample_stratum"] for product in products})
    return {
        "overall": policy_summary(products, policy),
        "by_stratum": {
            stratum: policy_summary(_scope(products, stratum), policy) for stratum in strata
        },
        "removed_control_forecasts": policy_summary(products, policy, removed=True),
    }


def _gate(candidate: dict, products: list[dict]) -> dict:
    failures: list[str] = []
    inconclusive: list[str] = []
    overall = candidate["overall"]
    if not overall["shown_weeks"]:
        inconclusive.append("candidate_showed_no_forecasts")
    elif overall["skill_vs_zero_percent"] is None or overall["skill_vs_zero_percent"] <= 0:
        failures.append("retained_forecasts_did_not_beat_zero_overall")
    for stratum, evidence in candidate["by_stratum"].items():
        if evidence["shown_weeks"] and (
            evidence["skill_vs_zero_percent"] is None or evidence["skill_vs_zero_percent"] <= 0
        ):
            failures.append(f"retained_forecasts_did_not_beat_zero_in_{stratum}")
    removed = candidate["removed_control_forecasts"]
    if not removed["shown_weeks"]:
        inconclusive.append("consistency_removed_no_current_forecasts")
    elif removed["skill_vs_zero_percent"] is not None and removed["skill_vs_zero_percent"] > 0:
        failures.append("consistency_removed_forecasts_that_beat_zero")
    if any(
        product["decision"]["permissions"]["global_consistency"]
        and not product["decision"]["permissions"]["current_control"]
        for product in products
    ):
        failures.append("consistency_bypassed_current_gate")
    status = "failed" if failures else "inconclusive" if inconclusive else "passed"
    return {
        "status": status,
        "failure_reasons": failures,
        "inconclusive_reasons": inconclusive,
    }


def build_report() -> dict:
    base = build_development_report()
    products = base["products"]
    for product in products:
        permissions = product["decision"]["permissions"]
        permissions["global_consistency"] = (
            permissions["current_control"] and product["decision"]["consistency"]["passed"]
        )
    current = _summary(products, "current_control")
    candidate = _summary(products, "global_consistency")
    return {
        "scope": (
            "Previously used M5 development products; this compares behavior and "
            "cannot provide untouched validation or release approval."
        ),
        "protocol": "milestone-11b-6-global-consistency-development-v1",
        "configuration": {
            "consistency_blocks": 3,
            "weeks_per_block": 13,
            "positive_skill_required_in_every_block": True,
        },
        "lineage": base["lineage"],
        "current_control": current,
        "global_consistency_candidate": candidate,
        "advancement_gate": _gate(candidate, products),
        "products": products,
        "supported_use_approved": False,
    }


def main() -> None:
    report = build_report()
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "current_control": report["current_control"],
                "global_consistency_candidate": report["global_consistency_candidate"],
                "advancement_gate": report["advancement_gate"],
            },
            indent=2,
        )
    )
    print(f"Saved {OUTPUT}")


if __name__ == "__main__":
    main()
