"""Cross-industry synthetic evaluation pack for the anomaly detector.

These cases are intentionally deterministic. Each resembles a different small
business pattern and has a known expected outcome, so the test suite measures
both detection and the system's safe unavailable/no-findings behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pytest

from src.diagnostics.anomaly import build_monthly_anomaly_report
from src.diagnostics.contracts import DiagnosticStatus


@dataclass(frozen=True)
class IndustryScenario:
    name: str
    industry: str
    sales_by_month: tuple[float, ...]
    orders_by_month: tuple[int, ...]
    expected_status: DiagnosticStatus
    expected_insight_ids: frozenset[str]
    latest_period_complete: bool = True
    missing_month_index: int | None = None
    refund_only_current_month: bool = False


SCENARIOS = (
    IndustryScenario(
        name="grocery_retail_stable_sales",
        industry="Grocery retail",
        sales_by_month=(1000, 980, 1020, 1000, 1010, 990, 1005),
        orders_by_month=(10, 10, 10, 10, 10, 10, 10),
        expected_status=DiagnosticStatus.NO_FINDINGS,
        expected_insight_ids=frozenset(),
    ),
    IndustryScenario(
        name="fashion_campaign_sales_spike",
        industry="Fashion ecommerce",
        sales_by_month=(1000, 1000, 1000, 1000, 1000, 1000, 1600),
        orders_by_month=(10, 10, 10, 10, 10, 10, 10),
        expected_status=DiagnosticStatus.AVAILABLE,
        expected_insight_ids=frozenset({"anomaly_recognized_sales", "anomaly_average_order_value"}),
    ),
    IndustryScenario(
        name="electronics_checkout_order_drop",
        industry="Electronics retail",
        sales_by_month=(1000, 1000, 1000, 1000, 1000, 1000, 400),
        orders_by_month=(10, 10, 10, 10, 10, 10, 4),
        expected_status=DiagnosticStatus.AVAILABLE,
        expected_insight_ids=frozenset({"anomaly_recognized_sales", "anomaly_completed_orders"}),
    ),
    IndustryScenario(
        name="food_delivery_higher_basket_value",
        industry="Food delivery",
        sales_by_month=(1200, 1200, 1200, 1200, 1200, 1200, 1800),
        orders_by_month=(12, 12, 12, 12, 12, 12, 12),
        expected_status=DiagnosticStatus.AVAILABLE,
        expected_insight_ids=frozenset({"anomaly_recognized_sales", "anomaly_average_order_value"}),
    ),
    IndustryScenario(
        name="subscription_gradual_growth",
        industry="Subscription commerce",
        sales_by_month=(1000, 1050, 1100, 1150, 1200, 1250, 1300),
        orders_by_month=(10, 10, 11, 11, 12, 12, 13),
        expected_status=DiagnosticStatus.NO_FINDINGS,
        expected_insight_ids=frozenset(),
    ),
    IndustryScenario(
        name="wholesale_large_contract",
        industry="Wholesale distribution",
        sales_by_month=(10000, 10200, 9900, 10100, 10050, 9950, 40000),
        orders_by_month=(10, 10, 10, 10, 10, 10, 10),
        expected_status=DiagnosticStatus.AVAILABLE,
        expected_insight_ids=frozenset({"anomaly_recognized_sales", "anomaly_average_order_value"}),
    ),
    IndustryScenario(
        name="professional_services_low_month",
        industry="Professional services",
        sales_by_month=(3000, 3050, 2950, 3000, 3100, 3000, 1500),
        orders_by_month=(3, 3, 3, 3, 3, 3, 3),
        expected_status=DiagnosticStatus.AVAILABLE,
        expected_insight_ids=frozenset({"anomaly_recognized_sales", "anomaly_average_order_value"}),
    ),
    IndustryScenario(
        name="beauty_missing_sales_history",
        industry="Beauty and cosmetics",
        sales_by_month=(1000, 1000, 1000, 1000, 1000, 1000, 1000, 1600),
        orders_by_month=(10, 10, 10, 10, 10, 10, 10, 10),
        expected_status=DiagnosticStatus.UNAVAILABLE,
        expected_insight_ids=frozenset(),
        missing_month_index=3,
    ),
    IndustryScenario(
        name="logistics_incomplete_current_month",
        industry="Logistics services",
        sales_by_month=(1000, 1000, 1000, 1000, 1000, 1000, 1600),
        orders_by_month=(10, 10, 10, 10, 10, 10, 10),
        expected_status=DiagnosticStatus.UNAVAILABLE,
        expected_insight_ids=frozenset(),
        latest_period_complete=False,
    ),
    IndustryScenario(
        name="pharmacy_refund_only_adjustment",
        industry="Pharmacy retail",
        sales_by_month=(1000, 1000, 1000, 1000, 1000, 1000, 1000),
        orders_by_month=(10, 10, 10, 10, 10, 10, 10),
        expected_status=DiagnosticStatus.NO_FINDINGS,
        expected_insight_ids=frozenset(),
        refund_only_current_month=True,
    ),
)


def _scenario_frame(scenario: IndustryScenario) -> pd.DataFrame:
    rows: list[dict] = []
    periods = pd.period_range("2026-01", periods=len(scenario.sales_by_month), freq="M")
    for index, (period, sales, order_count) in enumerate(
        zip(periods, scenario.sales_by_month, scenario.orders_by_month)
    ):
        if index == scenario.missing_month_index:
            continue
        for order_number in range(order_count):
            rows.append(
                {
                    "order_id": f"{scenario.name}-{index}-{order_number}",
                    "order_date": period.start_time,
                    "recognized_sales": sales / order_count,
                    "revenue": sales / order_count,
                    "currency": "NGN",
                }
            )
    if scenario.refund_only_current_month:
        rows.append(
            {
                "order_id": f"{scenario.name}-refund",
                "order_date": periods[-1].start_time,
                "recognized_sales": 0,
                "revenue": -700,
                "currency": "NGN",
            }
        )
    return pd.DataFrame(rows)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_cross_industry_anomaly_evaluation(scenario: IndustryScenario) -> None:
    report = build_monthly_anomaly_report(
        _scenario_frame(scenario),
        latest_period_complete=scenario.latest_period_complete,
    )

    assert report.status is scenario.expected_status
    assert {insight.id for insight in report.insights} == scenario.expected_insight_ids


def test_evaluation_pack_covers_ten_industries() -> None:
    assert len(SCENARIOS) == 10
    assert len({scenario.industry for scenario in SCENARIOS}) == 10
