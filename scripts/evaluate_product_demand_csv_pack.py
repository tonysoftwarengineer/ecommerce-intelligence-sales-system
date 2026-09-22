"""Ten reproducible CSV-to-demand API tests; no policy tuning or external data.

Run from the repository root:
    python3 -m scripts.evaluate_product_demand_csv_pack
"""

from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from io import StringIO
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from api.routes import analysis_store, upload_store

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "tests/fixtures/product_demand_csv_pack"
START = date(2025, 1, 1)
FIELDS = (
    "order_id",
    "order_date",
    "customer_id",
    "revenue",
    "product_id",
    "product_name",
    "quantity",
    "unit_of_measure",
    "order_status",
    "product_category",
)


@dataclass
class CsvScenario:
    name: str
    description: str
    rows: list[dict]
    expected_products: int
    expected_categories: int = 0
    expected_unavailable_products: int = 1
    expected_invalid_rows: int = 0
    assumptions: dict = field(default_factory=dict)
    required_reason: str | None = None

    def confirmations(self) -> dict:
        return {
            "export_covers_all_open_days": True,
            "stockout_tracking_complete": True,
            "confirm_product_categories": bool(self.rows[0]["product_category"]),
            **self.assumptions,
        }


def row(
    product: str,
    offset: int,
    units: int,
    *,
    category: str = "",
    unit: str = "piece",
    status: str = "Completed",
) -> dict:
    return {
        "order_id": f"{product}-{offset:04d}",
        "order_date": (START + timedelta(days=offset)).isoformat(),
        "customer_id": f"C-{offset % 37:03d}",
        "revenue": abs(units) * 1500,
        "product_id": product,
        "product_name": f"Item {product}",
        "quantity": units,
        "unit_of_measure": unit,
        "order_status": status,
        "product_category": category,
    }


def scenarios() -> list[CsvScenario]:
    rng = random.Random(20260915)
    weekday = [
        row(
            "RETAIL-01",
            i,
            (8, 9, 10, 10, 15, 23, 19)[(START + timedelta(days=i)).weekday()] + rng.randint(-3, 3),
        )
        for i in range(210)
    ]
    trend = [row("GROWTH-01", i, 6 + i // 14 + rng.randint(-2, 2)) for i in range(210)]
    intermittent = [
        row("SPARE-01", i, rng.randint(3, 12))
        for i in range(210)
        if rng.random() < 0.38 or i in {0, 209}
    ]
    # Cancelled orders deliberately have large quantities: these are NOT fulfilled demand.
    intermittent += [row("SPARE-01", i, 500, status="Cancelled") for i in (31, 79, 143)]
    alternating = [
        row("KIT-A" if w % 2 == 0 else "KIT-B", w * 7, 7, category="Meal Kits", unit="portion")
        for w in range(20)
    ]
    mixed = [row("HEALTHY", i, 12 + rng.randint(-3, 3)) for i in range(210)]
    mixed += [row("NEW", i, rng.randint(1, 8)) for i in range(180, 210)]
    # No fulfilled orders for this product: zero must not become a confident preview.
    mixed += [row("CANCELLED-ONLY", i, 4, status="Cancelled") for i in range(210)]
    gaps = [row("GAPS", i, rng.randint(5, 15)) for i in range(210) if i % 11 != 3]
    stockouts = [row("STOCK", i, rng.randint(6, 14)) for i in range(210) if not 165 <= i <= 173]
    conflicting = [
        row("UNIT-CONFLICT", i, rng.randint(5, 12), unit="pack" if i % 2 else "piece")
        for i in range(210)
    ]
    invalid = [row("BAD-DATA", i, rng.randint(5, 12)) for i in range(210)]
    for i in range(90):
        if i % 2:
            invalid[i]["quantity"] = -4
        else:
            invalid[i]["order_date"] = "not-a-date"
    return [
        CsvScenario(
            "01_noisy_weekday_retail",
            "Noisy daily sales with a weekend uplift.",
            weekday,
            1,
            expected_unavailable_products=0,
        ),
        CsvScenario(
            "02_growing_demand",
            "Rising daily demand with noise; assess error, not perfection.",
            trend,
            1,
            expected_unavailable_products=0,
        ),
        CsvScenario(
            "03_intermittent_and_cancellations",
            "Irregular spare-part sales and three large cancelled orders.",
            intermittent,
            1,
            expected_unavailable_products=0,
        ),
        CsvScenario(
            "04_category_fallback",
            "Alternating products fail individually; their combined category passes.",
            alternating,
            0,
            1,
            2,
        ),
        CsvScenario(
            "05_mixed_products",
            "Healthy product, new product, and cancelled-only product; isolate failures.",
            mixed,
            1,
            expected_unavailable_products=2,
        ),
        CsvScenario(
            "06_short_history",
            "Thirty-five daily observations cannot supply thirteen shared test weeks.",
            [row("SHORT", i, rng.randint(4, 12)) for i in range(35)],
            0,
            required_reason="no_weekly_winner",
        ),
        CsvScenario(
            "07_unknown_missing_days",
            "Export completeness is not confirmed: gaps must not become zero sales.",
            gaps,
            0,
            assumptions={"export_covers_all_open_days": False},
            required_reason="incomplete_daily_coverage",
        ),
        CsvScenario(
            "08_unrecorded_stockouts",
            "Stockout tracking is incomplete: observed sales cannot establish unrestricted demand.",
            stockouts,
            0,
            assumptions={"stockout_tracking_complete": False},
            required_reason="stockout_data_unavailable",
        ),
        CsvScenario(
            "09_conflicting_units",
            "One SKU mixes packs and pieces with no conversion evidence.",
            conflicting,
            0,
            required_reason="unit_conflict",
        ),
        CsvScenario(
            "10_many_invalid_rows",
            "Ninety invalid dates/negative quantities: dashboard preview only, no demand forecast.",
            invalid,
            0,
            expected_unavailable_products=0,
            expected_invalid_rows=90,
            required_reason="insufficient_data_quality",
        ),
    ]


def csv_text(case: CsvScenario) -> str:
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(sorted(case.rows, key=lambda r: (r["order_date"], r["order_id"])))
    return output.getvalue()


def post(client: TestClient, path: str, **kwargs) -> dict:
    response = client.post(path, **kwargs)
    assert response.status_code == 200, f"{path}: {response.status_code}: {response.text}"
    return response.json()


def run_case(client: TestClient, case: CsvScenario) -> dict:
    upload = post(
        client,
        "/api/v1/uploads/preview",
        files={"file": (case.name + ".csv", csv_text(case), "text/csv")},
    )
    mapping = {key: key for key in FIELDS if key != "product_category" or case.rows[0][key]}
    mapped = post(
        client,
        "/api/v1/uploads/validate-mapping",
        json={"upload_id": upload["upload_id"], "mapping": mapping, "revenue_mode": "row_total"},
    )
    assert mapped["valid"], mapped["errors"]
    request = {
        "upload_id": upload["upload_id"],
        "mapping": mapping,
        "revenue_mode": "row_total",
        "negative_revenue_policy": "invalid",
        "date_format": "%Y-%m-%d",
        "currency": "NGN",
        "assume_all_completed": False,
        "status_mapping": {"Completed": "completed", "Cancelled": "cancelled"},
        "discount_type": "none",
    }
    validation = post(client, "/api/v1/uploads/validate-data", json=request)
    assert validation["invalid_rows"] == case.expected_invalid_rows
    assert validation["valid_rows"] + validation["invalid_rows"] == len(case.rows)
    analysis = post(
        client,
        "/api/v1/uploads/analyze",
        json={
            **request,
            "confirm_quarantine": bool(case.expected_invalid_rows),
            # Synthetic fixture declaration, not an inference from the last transaction date.
            "latest_period_complete": True,
        },
    )
    assert analysis["quarantined_rows"] == case.expected_invalid_rows
    # Independent financial oracle: only valid completed sales contribute revenue.
    expected_revenue = sum(
        r["revenue"]
        for r in case.rows
        if r["order_status"] == "Completed"
        and r["order_date"] != "not-a-date"
        and r["quantity"] > 0
    )
    assert analysis["kpis"]["net_revenue"] == expected_revenue
    demand = post(
        client,
        f"/api/v1/analyses/{analysis['analysis_id']}/product-demand",
        json=case.confirmations(),
    )
    observed_counts = (
        demand["preview_product_count"],
        demand["preview_category_count"],
        demand["unavailable_product_count"],
    )
    expected_counts = (
        case.expected_products,
        case.expected_categories,
        case.expected_unavailable_products,
    )
    assert observed_counts == expected_counts, (
        f"Expected product/category/unavailable counts {expected_counts}; got {observed_counts}"
    )
    assert demand["supported_use_approved"] is False
    reasons = set(demand["dataset_reason_codes"])
    for entry in [*demand["products"], *demand["categories"]]:
        reasons.update(entry.get("data_reason_codes", []))
        reasons.update(entry.get("category_reason_codes", []))
        reasons.update(entry["policy_reason_codes"])
        forecast = entry["forecast"]
        if not entry["numeric_forecast_allowed"]:
            assert forecast is None and entry["explanations"]
            continue
        assert forecast is not None and entry["trust_state"] == "limited_preview"
        assert math.isfinite(forecast["total_units"]) and forecast["total_units"] >= 0
        assert math.isclose(
            forecast["average_daily_planning_rate"] * 7,
            forecast["total_units"],
            rel_tol=1e-7,
            abs_tol=1e-7,
        )
        assert len(forecast["forecast_dates"]) == 7
        assert forecast["daily_predictions_provided"] is False
        evidence = entry["evidence"]
        assert evidence["shared_test_weeks"] >= 13 and evidence["benchmark_passed"]
        assert (
            evidence["selected_mean_absolute_error_units"]
            < evidence["zero_mean_absolute_error_units"]
        )
        assert "not decision-ready" in entry["warning"]
    if case.required_reason:
        assert case.required_reason in reasons, sorted(reasons)
    if case.name == "04_category_fallback" and case.expected_categories:
        assert demand["categories"][0]["forecast"]["total_units"] == 7
    if case.name == "05_mixed_products":
        products = {p["product_id"]: p for p in demand["products"]}
        assert products["HEALTHY"]["numeric_forecast_allowed"]
        assert products["NEW"]["forecast"] is None
        assert "no_weekly_winner" in products["NEW"]["policy_reason_codes"]
        assert products["CANCELLED-ONLY"]["forecast"] is None
        assert "non_positive_zero_skill" in products["CANCELLED-ONLY"]["policy_reason_codes"]
    if case.expected_invalid_rows:
        assert validation["data_quality"]["decision_ready"] is False
        assert validation["data_quality"]["correction_actions"]
        for suffix in ("canonical.csv", "quarantine.csv"):
            response = client.get(f"/api/v1/analyses/{analysis['analysis_id']}/{suffix}")
            assert response.status_code == 200
            count = len(list(csv.DictReader(StringIO(response.text))))
            expected = (
                case.expected_invalid_rows
                if suffix == "quarantine.csv"
                else validation["valid_rows"]
            )
            assert count == expected
    return {
        "name": case.name,
        "description": case.description,
        "expectations_passed": True,
        "total_rows": len(case.rows),
        "expected": {
            "product_previews": case.expected_products,
            "category_previews": case.expected_categories,
            "unavailable_products": case.expected_unavailable_products,
            "invalid_rows": case.expected_invalid_rows,
        },
        "validation": validation,
        "net_revenue_ngn": expected_revenue,
        "assumptions": case.confirmations(),
        "demand": demand,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    client = TestClient(app)  # No Olist startup/download needed for private CSV routes.
    for case in scenarios():
        (OUTPUT_DIR / (case.name + ".csv")).write_text(csv_text(case), encoding="utf-8")
        try:
            result = run_case(client, case)
        except AssertionError as exc:
            result = {"name": case.name, "expectations_passed": False, "failure": str(exc)}
        finally:
            # This is a separate test process; never deletes the live server's sessions.
            upload_store.clear()
            analysis_store.clear()
        results.append(result)
        print(f"{case.name}: {'PASS' if result['expectations_passed'] else 'FAIL'}", flush=True)
    report = {
        "scope": (
            "Seeded synthetic CSV/API behavior checks; not real-business accuracy validation "
            "or production approval."
        ),
        "seed": 20260915,
        "scenario_count": len(results),
        "passed_scenarios": sum(r["expectations_passed"] for r in results),
        "scenarios": results,
    }
    (OUTPUT_DIR / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Ten-CSV product-demand test pack",
        "",
        report["scope"],
        "",
        "Run: `python3 -m scripts.evaluate_product_demand_csv_pack`",
        "",
        "## Manual mapping",
        "",
        "Choose **Row total**, map same-named columns, currency NGN, date format %Y-%m-%d.",
        "Map Completed to completed sale; Cancelled to excluded. No discount calculation.",
        "Map product_category only in file 04. Product IDs and unit_of_measure are provided:",
        "do not confirm unique names or set a default unit. Latest month completeness is declared",
        "for these synthetic fixtures only. In a real export, the business must confirm it.",
        "",
        "## Demand confirmations",
        "",
        "Check export coverage and stockout tracking for every file EXCEPT:",
        "file 07: leave export coverage unchecked; file 08: leave stockout tracking unchecked.",
        "File 04: additionally confirm category mappings. No planned closures are declared.",
        "These confirmations are fixture facts, not instructions to guess for real business data.",
        "",
        "## Expected and observed outcomes",
        "",
        "| CSV | Expected product/category previews | Invalid rows | Checks |",
        "|---|---:|---:|---|",
    ]
    for case, result in zip(scenarios(), results):
        lines.append(
            f"| {case.name}.csv | {case.expected_products}/{case.expected_categories} "
            f"| {case.expected_invalid_rows} "
            f"| {'PASS' if result['expectations_passed'] else 'FAIL'} |"
        )
    lines += [
        "",
        "## Historical selection evidence for available product previews",
        "",
        "These are historical model-selection errors, not independent future test errors.",
        "",
        "| CSV | Product | Selected method | Weekly forecast | Historical weekly MAE "
        "| Zero MAE | Shared test weeks |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for result in results:
        for product in result.get("demand", {}).get("products", []):
            if product["forecast"] is not None:
                evidence = product["evidence"]
                lines.append(
                    f"| {result['name']} | {product['product_id']} | {product['selected_method']} "
                    f"| {product['forecast']['total_units']:.2f} "
                    f"| {evidence['selected_mean_absolute_error_units']:.2f} "
                    f"| {evidence['zero_mean_absolute_error_units']:.2f} "
                    f"| {evidence['shared_test_weeks']} |"
                )
    lines += [
        "",
        "File 05 must isolate two unavailable products without hiding the healthy product.",
        "File 10 requires quarantine confirmation; the dashboard is preview-only "
        "and demand is unavailable.",
        "Every emitted number must beat zero over at least 13 common historical test weeks.",
        "The daily planning rate is weekly total / 7, not seven daily predictions.",
        "",
        "## Limitations",
        "",
        "Passing these tests proves the stated behavior on ten fixtures, "
        "not that all failures are handled.",
        "Historical errors used to select the winning method are not an independent "
        "held-out accuracy estimate.",
        "No forecasts were validated against future real-business outcomes; "
        "no policies were loosened.",
        "These tests exercise the real API in-process, not browser interactions. "
        "Full responses and error",
        "metrics are saved in report.json. Existing browser tests should still be run separately.",
        "The earlier locked evaluation's sparse-stratum failure remains unresolved; "
        "these synthetic checks do not supersede docs/PRODUCT_DEMAND_LOCKED_EVALUATION.md.",
        "",
    ]
    (OUTPUT_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")
    client.close()
    if report["passed_scenarios"] != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
