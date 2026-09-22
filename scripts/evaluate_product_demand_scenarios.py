"""Run the deterministic Milestone 11B product-demand scenario pack."""

from __future__ import annotations

import json
import time

from src.product_demand.scenario_pack import (
    PRODUCT_DEMAND_SCENARIOS,
    calculate_nonzero_average_inflation,
    run_product_demand_scenario_pack,
)


def build_report() -> dict[str, object]:
    started = time.perf_counter()
    pack = run_product_demand_scenario_pack()
    elapsed_ms = (time.perf_counter() - started) * 1000
    definitions = {scenario.name: scenario for scenario in PRODUCT_DEMAND_SCENARIOS}
    checks = {check.scenario_name: check for check in pack.checks}
    scenarios: list[dict[str, object]] = []
    for result in pack.results:
        check = checks[result.scenario_name]
        scenarios.append(
            {
                "name": result.scenario_name,
                "description": definitions[result.scenario_name].description,
                "expectations_passed": check.passed,
                "expectation_failures": list(check.failures),
                "products": [
                    {
                        "product_key": product.product_key,
                        "status": product.status.value,
                        "evaluated_candidates": sorted(
                            candidate.value for candidate in product.evaluated_candidates
                        ),
                        "evidence_reasons": sorted(
                            reason.value for reason in product.evidence_reasons
                        ),
                        "daily_winner": (
                            product.report.daily_winner.value
                            if product.report is not None
                            and product.report.daily_winner is not None
                            else None
                        ),
                        "seven_day_winner": (
                            product.report.seven_day_winner.value
                            if product.report is not None
                            and product.report.seven_day_winner is not None
                            else None
                        ),
                    }
                    for product in result.products
                ],
            }
        )
    inflation_scenario = definitions["nonzero_day_average_inflation"]
    inflation = calculate_nonzero_average_inflation(inflation_scenario.products[0])
    return {
        "scope": (
            "Deterministic synthetic evaluation evidence; not real-business validation "
            "and not a production trust threshold."
        ),
        "scenario_count": len(pack.results),
        "passed_scenarios": sum(check.passed for check in pack.checks),
        "failed_scenarios": sum(not check.passed for check in pack.checks),
        "elapsed_ms": round(elapsed_ms, 3),
        "nonzero_average_inflation": {
            "nonzero_day_average": str(inflation.nonzero_day_average),
            "implied_seven_day_total": str(inflation.implied_seven_day_total),
            "observed_mean_seven_day_total": str(inflation.observed_mean_seven_day_total),
            "inflation_units": str(inflation.inflation_units),
        },
        "scenarios": scenarios,
    }


def main() -> None:
    print(json.dumps(build_report(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
