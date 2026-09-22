from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pandas.testing as pdt
import pytest

from src.generic_sales.contracts import RevenueMode
from src.product_demand.calendar import build_product_demand_calendar
from src.product_demand.contracts import (
    ProductDateStatus,
    ProductDemandAssumptions,
    ProductDemandAvailability,
    ProductDemandReasonCode,
)
from src.product_demand.readiness import assess_product_demand_readiness
from src.schema_mapping import validate_schema_mapping


def _canonical(rows: list[dict[str, object]]) -> pd.DataFrame:
    defaults: dict[str, object] = {
        "product_id": "001",
        "product_name": "Biscuit",
        "unit_of_measure": "piece",
        "quantity": Decimal("1"),
        "returned_quantity": None,
        "order_status": "completed",
        "order_date": pd.Timestamp("2025-01-01"),
        "recognition_date": pd.Timestamp("2025-01-01"),
    }
    return pd.DataFrame(
        [{"source_row": index + 2, **defaults, **row} for index, row in enumerate(rows)]
    )


def _fully_observed(**changes) -> ProductDemandAssumptions:
    values = {
        "export_covers_all_open_days": True,
        "stockout_tracking_complete": True,
    }
    values.update(changes)
    return ProductDemandAssumptions(**values)


def test_assumptions_normalize_default_unit_and_reject_blank_unit() -> None:
    assumptions = ProductDemandAssumptions(default_unit_of_measure=" Pieces ")

    assert assumptions.default_unit_of_measure == "pieces"

    with pytest.raises(ValueError, match="must not be blank"):
        ProductDemandAssumptions(default_unit_of_measure="   ")


def test_product_mapping_fields_are_optional_only_for_line_item_modes() -> None:
    columns = ["Order", "Date", "Customer", "Total", "SKU", "Name", "UOM"]
    mapping = {
        "order_id": "Order",
        "order_date": "Date",
        "customer_id": "Customer",
        "revenue": "Total",
        "product_id": "SKU",
        "product_name": "Name",
        "unit_of_measure": "UOM",
    }

    row_total = validate_schema_mapping(columns, mapping, RevenueMode.ROW_TOTAL)
    order_total = validate_schema_mapping(columns, mapping, RevenueMode.ORDER_TOTAL)

    assert row_total["valid"] is True
    assert order_total["valid"] is False
    assert order_total["unsupported_fields"] == [
        "product_id",
        "product_name",
        "unit_of_measure",
    ]


def test_readiness_accepts_stable_product_id_and_dataset_default_unit() -> None:
    canonical = _canonical(
        [
            {"product_id": "0007", "unit_of_measure": None},
            {"product_id": "0007", "unit_of_measure": ""},
        ]
    )
    assumptions = _fully_observed(default_unit_of_measure="piece")

    report = assess_product_demand_readiness(
        canonical,
        RevenueMode.ROW_TOTAL,
        assumptions,
    )

    assert report.status is ProductDemandAvailability.READY
    assert report.unresolved_rows == 0
    assert report.ready_products == 1
    product = report.products[0]
    assert product.product_key == "id:0007"
    assert product.product_id == "0007"
    assert product.unit_of_measure == "piece"
    assert product.status is ProductDemandAvailability.READY


def test_readiness_marks_confirmed_name_fallback_and_missing_evidence_limited() -> None:
    canonical = _canonical(
        [{"product_id": "", "product_name": "Blue Mug", "unit_of_measure": "piece"}]
    )

    report = assess_product_demand_readiness(
        canonical,
        RevenueMode.ROW_TOTAL,
        ProductDemandAssumptions(confirm_product_names_unique=True),
    )

    product = report.products[0]
    assert report.status is ProductDemandAvailability.LIMITED
    assert product.product_key == "name:Blue Mug"
    assert set(product.reason_codes) == {
        ProductDemandReasonCode.PRODUCT_NAME_FALLBACK,
        ProductDemandReasonCode.STOCKOUT_DATA_UNAVAILABLE,
        ProductDemandReasonCode.INCOMPLETE_DAILY_COVERAGE,
    }


def test_readiness_does_not_invent_product_identity() -> None:
    canonical = _canonical([{"product_id": "", "product_name": "Blue Mug"}])

    report = assess_product_demand_readiness(
        canonical,
        RevenueMode.ROW_TOTAL,
        ProductDemandAssumptions(),
    )

    assert report.status is ProductDemandAvailability.UNAVAILABLE
    assert report.products == ()
    assert report.unresolved_rows == 1
    assert ProductDemandReasonCode.MISSING_PRODUCT_IDENTITY in report.reason_codes


def test_readiness_isolates_unit_conflict_to_affected_product() -> None:
    canonical = _canonical(
        [
            {"product_id": "A", "unit_of_measure": "pack"},
            {"product_id": "A", "unit_of_measure": "piece"},
            {"product_id": "B", "unit_of_measure": "piece"},
        ]
    )

    report = assess_product_demand_readiness(
        canonical,
        RevenueMode.ROW_TOTAL,
        _fully_observed(),
    )

    products = {product.product_id: product for product in report.products}
    assert products["A"].status is ProductDemandAvailability.UNAVAILABLE
    assert products["A"].reason_codes == (ProductDemandReasonCode.UNIT_CONFLICT,)
    assert products["B"].status is ProductDemandAvailability.READY
    assert report.unavailable_products == 1


def test_order_total_mode_is_product_demand_ineligible() -> None:
    report = assess_product_demand_readiness(
        _canonical([{}]),
        RevenueMode.ORDER_TOTAL,
        _fully_observed(),
    )

    assert report.status is ProductDemandAvailability.UNAVAILABLE
    assert report.reason_codes == (ProductDemandReasonCode.ORDER_TOTAL_INELIGIBLE,)
    assert report.products == ()


@pytest.mark.parametrize(
    ("complete_export", "expected_status", "expected_units"),
    [
        (False, ProductDateStatus.MISSING_UNKNOWN, None),
        (True, ProductDateStatus.CONFIRMED_ZERO, Decimal("0")),
    ],
)
def test_calendar_never_silently_turns_unknown_gap_into_zero(
    complete_export: bool,
    expected_status: ProductDateStatus,
    expected_units: Decimal | None,
) -> None:
    canonical = _canonical(
        [
            {"recognition_date": pd.Timestamp("2025-01-01"), "quantity": Decimal("5")},
            {"recognition_date": pd.Timestamp("2025-01-03"), "quantity": Decimal("2")},
        ]
    )
    original = canonical.copy(deep=True)
    assumptions = ProductDemandAssumptions(
        export_covers_all_open_days=complete_export,
        stockout_tracking_complete=True,
    )

    result = build_product_demand_calendar(canonical, RevenueMode.ROW_TOTAL, assumptions)

    day_two = result.calendar.loc[result.calendar["date"] == pd.Timestamp("2025-01-02")].iloc[0]
    assert day_two["status"] == expected_status.value
    assert day_two["fulfilled_units"] == expected_units
    pdt.assert_frame_equal(canonical, original)


def test_calendar_distinguishes_closure_stockout_and_observed_sales() -> None:
    canonical = _canonical(
        [
            {"recognition_date": pd.Timestamp("2025-01-01"), "quantity": Decimal("5")},
            {"recognition_date": pd.Timestamp("2025-01-04"), "quantity": Decimal("2")},
        ]
    )
    assumptions = _fully_observed(
        business_closed_dates=frozenset({pd.Timestamp("2025-01-02").date()}),
        stockout_dates={"id:001": frozenset({pd.Timestamp("2025-01-03").date()})},
    )

    result = build_product_demand_calendar(canonical, RevenueMode.ROW_TOTAL, assumptions)

    assert result.calendar["status"].tolist() == [
        ProductDateStatus.OBSERVED.value,
        ProductDateStatus.BUSINESS_CLOSED.value,
        ProductDateStatus.STOCKOUT_LIMITED.value,
        ProductDateStatus.OBSERVED.value,
    ]
    assert result.calendar["fulfilled_units"].tolist() == [
        Decimal("5"),
        Decimal("0"),
        Decimal("0"),
        Decimal("2"),
    ]


def test_calendar_applies_cancellation_and_return_semantics_without_erasing_demand() -> None:
    canonical = _canonical(
        [
            {
                "recognition_date": pd.Timestamp("2025-01-01"),
                "quantity": Decimal("4"),
                "order_status": "cancelled",
            },
            {
                "recognition_date": pd.Timestamp("2025-01-02"),
                "quantity": Decimal("4"),
                "returned_quantity": Decimal("4"),
                "order_status": "returned",
            },
            {
                "recognition_date": pd.Timestamp("2025-01-03"),
                "quantity": Decimal("-2"),
                "returned_quantity": Decimal("-2"),
                "order_status": "returned",
            },
        ]
    )

    result = build_product_demand_calendar(
        canonical,
        RevenueMode.ROW_TOTAL,
        _fully_observed(),
    )

    assert result.calendar["fulfilled_units"].tolist() == [
        Decimal("0"),
        Decimal("4"),
        Decimal("0"),
    ]
    assert result.calendar["returned_units"].tolist() == [
        Decimal("0"),
        Decimal("4"),
        Decimal("2"),
    ]


def test_observed_sales_on_known_stockout_day_are_preserved_but_censored() -> None:
    canonical = _canonical(
        [{"recognition_date": pd.Timestamp("2025-01-01"), "quantity": Decimal("3")}]
    )
    assumptions = _fully_observed(
        stockout_dates={"id:001": frozenset({pd.Timestamp("2025-01-01").date()})}
    )

    result = build_product_demand_calendar(canonical, RevenueMode.ROW_TOTAL, assumptions)

    row = result.calendar.iloc[0]
    assert row["status"] == ProductDateStatus.STOCKOUT_LIMITED.value
    assert row["fulfilled_units"] == Decimal("3")


def test_calendar_excludes_only_unavailable_product_series() -> None:
    canonical = _canonical(
        [
            {"product_id": "A", "unit_of_measure": "pack"},
            {"product_id": "A", "unit_of_measure": "piece"},
            {"product_id": "B", "unit_of_measure": "piece"},
        ]
    )

    result = build_product_demand_calendar(
        canonical,
        RevenueMode.ROW_TOTAL,
        _fully_observed(),
    )

    assert result.calendar["product_id"].unique().tolist() == ["B"]
    assert result.readiness.unavailable_products == 1
