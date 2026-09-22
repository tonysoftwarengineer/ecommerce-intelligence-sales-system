from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pandas.testing as pdt

from src.generic_sales.contracts import RevenueMode
from src.product_demand.contracts import ProductDemandAssumptions
from src.product_demand.service import ProductDemandAnalysisStatus, analyze_product_demand
from src.product_demand.trust_policy import ProductDemandPolicyReason, ProductDemandTrustState


def _row(
    product_id: str,
    day: date,
    *,
    quantity: int = 3,
    unit: str = "piece",
) -> dict[str, object]:
    return {
        "product_id": product_id,
        "product_name": f"Product {product_id}",
        "unit_of_measure": unit,
        "quantity": Decimal(quantity),
        "returned_quantity": None,
        "order_status": "completed",
        "order_date": pd.Timestamp(day),
        "recognition_date": pd.Timestamp(day),
    }


def _daily_rows(
    product_id: str,
    days: int,
    *,
    start: date = date(2025, 1, 1),
    quantity: int = 3,
) -> list[dict[str, object]]:
    return [
        _row(product_id, start + timedelta(days=offset), quantity=quantity)
        for offset in range(days)
    ]


def _assumptions(**changes) -> ProductDemandAssumptions:
    values = {
        "export_covers_all_open_days": True,
        "stockout_tracking_complete": True,
    }
    values.update(changes)
    return ProductDemandAssumptions(**values)


def test_service_connects_evidence_to_one_weekly_preview() -> None:
    canonical = pd.DataFrame(_daily_rows("A", 119))

    result = analyze_product_demand(canonical, RevenueMode.ROW_TOTAL, _assumptions())

    assert result.status is ProductDemandAnalysisStatus.PREVIEW_AVAILABLE
    assert result.preview_product_count == 1
    assert result.unavailable_product_count == 0
    product = result.products[0]
    assert product.trust.state is ProductDemandTrustState.LIMITED_PREVIEW
    assert product.trust.shared_fold_count == 13
    assert product.forecast is not None
    assert product.forecast.predicted_total_units == 21
    assert product.forecast.predicted_daily_units is None
    assert product.average_daily_planning_rate == 3
    assert len(product.forecast.forecast_dates) == 7


def test_short_product_is_unavailable_without_blocking_an_eligible_product() -> None:
    canonical = pd.DataFrame([*_daily_rows("A", 119), *_daily_rows("B", 35)])

    result = analyze_product_demand(canonical, RevenueMode.ROW_TOTAL, _assumptions())

    assert result.status is ProductDemandAnalysisStatus.PARTIAL_PREVIEW
    assert result.preview_product_count == 1
    assert result.unavailable_product_count == 1
    products = {item.readiness.product_id: item for item in result.products}
    assert products["A"].forecast is not None
    assert products["B"].forecast is None
    assert products["B"].trust.state is ProductDemandTrustState.UNAVAILABLE
    assert products["B"].trust.policy_reasons == (ProductDemandPolicyReason.NO_WEEKLY_WINNER,)


def test_unusable_product_semantics_do_not_create_fake_evaluation_evidence() -> None:
    rows = [
        _row("A", date(2025, 1, 1), unit="piece"),
        _row("A", date(2025, 1, 2), unit="pack"),
    ]

    result = analyze_product_demand(pd.DataFrame(rows), RevenueMode.ROW_TOTAL, _assumptions())

    assert result.status is ProductDemandAnalysisStatus.UNAVAILABLE
    product = result.products[0]
    assert product.evaluation is None
    assert product.zero_skill is None
    assert product.forecast is None
    assert product.trust.policy_reasons == (ProductDemandPolicyReason.UNSAFE_SEMANTICS,)


def test_recent_closed_day_downgrades_final_forecast_instead_of_crashing() -> None:
    start = date(2025, 1, 1)
    closed = start + timedelta(days=152)
    rows = [
        _row("A", start + timedelta(days=offset))
        for offset in range(154)
        if start + timedelta(days=offset) != closed
    ]

    result = analyze_product_demand(
        pd.DataFrame(rows),
        RevenueMode.ROW_TOTAL,
        _assumptions(business_closed_dates=frozenset({closed})),
    )

    assert result.status is ProductDemandAnalysisStatus.UNAVAILABLE
    product = result.products[0]
    assert product.evaluation is not None
    assert product.zero_skill is not None
    assert product.forecast is None
    assert product.trust.policy_reasons == (ProductDemandPolicyReason.FINAL_FORECAST_UNAVAILABLE,)
    assert "latest product history" in product.trust.explanations[-1]


def test_order_total_mode_returns_a_global_unavailable_result() -> None:
    canonical = pd.DataFrame(_daily_rows("A", 119))

    result = analyze_product_demand(canonical, RevenueMode.ORDER_TOTAL, _assumptions())

    assert result.status is ProductDemandAnalysisStatus.UNAVAILABLE
    assert result.products == ()
    assert result.preview_product_count == 0
    assert result.readiness.reason_codes


def test_service_is_deterministic_and_does_not_mutate_canonical_input() -> None:
    canonical = pd.DataFrame(_daily_rows("A", 119))
    original = canonical.copy(deep=True)

    first = analyze_product_demand(canonical, RevenueMode.ROW_TOTAL, _assumptions())
    second = analyze_product_demand(canonical, RevenueMode.ROW_TOTAL, _assumptions())

    assert first == second
    pdt.assert_frame_equal(canonical, original)
