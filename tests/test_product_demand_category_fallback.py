from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd

from src.generic_sales.contracts import RevenueMode
from src.product_demand.category_fallback import CategoryFallbackReasonCode
from src.product_demand.contracts import ProductDemandAssumptions
from src.product_demand.service import ProductDemandAnalysisStatus, analyze_product_demand


def _weekly_rows(
    weeks: int = 20,
    *,
    category: str = "Meal Kits",
    alternate_products: bool = True,
) -> list[dict[str, object]]:
    start = date(2025, 1, 1)
    rows: list[dict[str, object]] = []
    for week in range(weeks):
        product_id = "A" if not alternate_products or week % 2 == 0 else "B"
        rows.append(
            {
                "product_id": product_id,
                "product_name": f"Product {product_id}",
                "product_category": category,
                "unit_of_measure": "portion",
                "quantity": Decimal("7"),
                "returned_quantity": None,
                "order_status": "completed",
                "order_date": pd.Timestamp(start + timedelta(days=week * 7)),
                "recognition_date": pd.Timestamp(start + timedelta(days=week * 7)),
            }
        )
    return rows


def _assumptions(*, confirm_categories: bool = True) -> ProductDemandAssumptions:
    return ProductDemandAssumptions(
        confirm_product_categories=confirm_categories,
        export_covers_all_open_days=True,
        stockout_tracking_complete=True,
    )


def test_sparse_products_fall_back_to_one_evidence_gated_category_preview() -> None:
    result = analyze_product_demand(
        pd.DataFrame(_weekly_rows()),
        RevenueMode.ROW_TOTAL,
        _assumptions(),
    )

    assert result.status is ProductDemandAnalysisStatus.PARTIAL_PREVIEW
    assert result.preview_product_count == 0
    assert result.unavailable_product_count == 2
    assert result.preview_category_count == 1
    category = result.categories[0]
    assert category.category_name == "Meal Kits"
    assert category.product_keys == ("id:A", "id:B")
    assert category.forecast is not None
    assert category.forecast.predicted_total_units == 7
    assert category.average_daily_planning_rate == 1
    assert category.trust is not None
    assert category.trust.shared_fold_count >= 13


def test_category_fallback_requires_explicit_bulk_confirmation() -> None:
    result = analyze_product_demand(
        pd.DataFrame(_weekly_rows()),
        RevenueMode.ROW_TOTAL,
        _assumptions(confirm_categories=False),
    )

    assert result.preview_category_count == 0
    assert result.categories == ()
    assert result.category_dataset_reason_codes == (
        CategoryFallbackReasonCode.CATEGORY_CONFIRMATION_REQUIRED,
    )


def test_sparse_products_without_categories_receive_correction_guidance() -> None:
    rows = _weekly_rows()
    for row in rows:
        del row["product_category"]

    result = analyze_product_demand(
        pd.DataFrame(rows),
        RevenueMode.ROW_TOTAL,
        _assumptions(),
    )

    assert result.preview_category_count == 0
    assert result.category_dataset_reason_codes == (
        CategoryFallbackReasonCode.MISSING_PRODUCT_CATEGORY,
    )


def test_category_fallback_is_suppressed_when_a_member_product_passes() -> None:
    start = date(2025, 1, 1)
    rows = []
    for offset in range(119):
        for product_id in ("A", "B"):
            rows.append(
                {
                    **_weekly_rows(1, alternate_products=False)[0],
                    "product_id": product_id,
                    "product_name": f"Product {product_id}",
                    "quantity": Decimal("3"),
                    "order_date": pd.Timestamp(start + timedelta(days=offset)),
                    "recognition_date": pd.Timestamp(start + timedelta(days=offset)),
                }
            )

    result = analyze_product_demand(
        pd.DataFrame(rows),
        RevenueMode.ROW_TOTAL,
        _assumptions(),
    )

    assert result.preview_product_count == 2
    assert result.categories == ()


def test_incompatible_category_units_are_explained_without_a_number() -> None:
    rows = _weekly_rows()
    for row in rows:
        if row["product_id"] == "B":
            row["unit_of_measure"] = "pack"

    result = analyze_product_demand(
        pd.DataFrame(rows),
        RevenueMode.ROW_TOTAL,
        _assumptions(),
    )

    assert result.preview_category_count == 0
    assert result.unavailable_category_count == 1
    category = result.categories[0]
    assert category.forecast is None
    assert category.reason_codes == (CategoryFallbackReasonCode.INCOMPATIBLE_UNITS,)


def test_one_product_category_does_not_disguise_the_failed_product_forecast() -> None:
    rows = [row for row in _weekly_rows() if row["product_id"] == "A"]

    result = analyze_product_demand(
        pd.DataFrame(rows),
        RevenueMode.ROW_TOTAL,
        _assumptions(),
    )

    assert result.preview_product_count == 0
    assert result.preview_category_count == 0
    assert result.categories[0].reason_codes == (
        CategoryFallbackReasonCode.INSUFFICIENT_DISTINCT_PRODUCTS,
    )


def test_conflicting_product_categories_are_explained_without_a_number() -> None:
    rows = _weekly_rows()
    rows[0]["product_category"] = "Prepared Food"

    result = analyze_product_demand(
        pd.DataFrame(rows),
        RevenueMode.ROW_TOTAL,
        _assumptions(),
    )

    assert result.preview_category_count == 0
    assert any(
        CategoryFallbackReasonCode.INCONSISTENT_PRODUCT_CATEGORY in category.reason_codes
        for category in result.categories
    )
    assert all(category.forecast is None for category in result.categories)


def test_partially_missing_product_category_is_explained_without_a_number() -> None:
    rows = _weekly_rows()
    rows[0]["product_category"] = None

    result = analyze_product_demand(
        pd.DataFrame(rows),
        RevenueMode.ROW_TOTAL,
        _assumptions(),
    )

    assert result.preview_category_count == 0
    assert result.unavailable_category_count == 1
    assert result.categories[0].reason_codes == (
        CategoryFallbackReasonCode.INCOMPLETE_PRODUCT_CATEGORY,
    )
