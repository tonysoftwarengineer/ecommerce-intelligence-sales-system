from decimal import Decimal
from typing import Any

import pandas as pd

from src.generic_sales.contracts import (
    DiscountScope,
    DiscountType,
    NegativeRevenuePolicy,
    OrderDiscountAllocation,
    RefundTaxTreatment,
    RevenueMode,
    SalesProcessingConfig,
    StandardOrderStatus,
    StandardPaymentStatus,
)
from src.generic_sales.transformation import transform_sales_data
from src.generic_sales.validation import validate_sales_data


def mapping(**extra: str) -> dict[str, str]:
    return {
        "order_id": "Order",
        "order_date": "Date",
        "customer_id": "Customer",
        "revenue": "Total",
        **extra,
    }


def config(**overrides) -> SalesProcessingConfig:
    values: dict[str, Any] = {
        "revenue_mode": RevenueMode.ROW_TOTAL,
        "negative_revenue_policy": NegativeRevenuePolicy.INVALID,
        "date_format": "%Y-%m-%d",
        "currency": "USD",
        "assume_all_completed": True,
    }
    values.update(overrides)
    return SalesProcessingConfig(**values)


def test_missing_status_requires_explicit_all_completed_confirmation() -> None:
    frame = pd.DataFrame(
        {"Order": ["A1"], "Date": ["2026-01-01"], "Customer": ["C1"], "Total": [100]}
    )

    result = validate_sales_data(frame, mapping(), config(assume_all_completed=False))

    assert result.can_transform is False
    assert "Confirm that every row is a completed sale" in result.blocking_errors[0]


def test_status_rules_keep_gross_refunds_pending_and_net_separate() -> None:
    frame = pd.DataFrame(
        {
            "Order": ["A1", "A2", "A3", "A4"],
            "Date": ["2026-01-01"] * 4,
            "Customer": ["C1", "C2", "C3", "C4"],
            "Total": [100, 80, 60, 40],
            "Status": ["Done", "Waiting", "Cancelled", "Returned"],
        }
    )
    retail_config = config(
        assume_all_completed=False,
        status_mapping={
            "Done": StandardOrderStatus.COMPLETED,
            "Waiting": StandardOrderStatus.PENDING,
            "Cancelled": StandardOrderStatus.CANCELLED,
            "Returned": StandardOrderStatus.RETURNED,
        },
    )
    retail_mapping = mapping(order_status="Status")

    validation = validate_sales_data(frame, retail_mapping, retail_config)
    transformed = transform_sales_data(frame, retail_mapping, retail_config, validation, False)
    canonical = transformed.canonical_data.set_index("order_id")

    assert validation.can_transform is True
    assert canonical.loc["A1", "revenue"] == Decimal("100")
    assert canonical.loc["A2", "pending_value"] == Decimal("80")
    assert canonical.loc["A2", "revenue"] == 0
    assert canonical.loc["A3", "revenue"] == 0
    assert canonical.loc["A4", "gross_sales"] == Decimal("40")
    assert canonical.loc["A4", "refund_amount"] == Decimal("40")
    assert canonical.loc["A4", "revenue"] == 0


def test_unknown_status_is_quarantinable_and_never_counted_silently() -> None:
    frame = pd.DataFrame(
        {
            "Order": ["A1", "A2"],
            "Date": ["2026-01-01", "2026-01-02"],
            "Customer": ["C1", "C2"],
            "Total": [100, 80],
            "Status": ["Done", "Mystery"],
        }
    )
    retail_config = config(
        assume_all_completed=False,
        status_mapping={"Done": StandardOrderStatus.COMPLETED},
    )

    result = validate_sales_data(frame, mapping(order_status="Status"), retail_config)

    assert result.valid_rows == 1
    assert result.requires_confirmation is True
    assert any(issue.code == "unknown_status" for issue in result.issues)


def test_calculated_revenue_uses_fixed_line_discount_and_warns_on_reported_mismatch() -> None:
    frame = pd.DataFrame(
        {
            "Order": ["A1"],
            "Date": ["2026-01-01"],
            "Customer": ["C1"],
            "Price": ["25.00"],
            "Quantity": ["2"],
            "Discount": ["5.00"],
            "Reported": ["47.00"],
        }
    )
    retail_mapping = {
        "order_id": "Order",
        "order_date": "Date",
        "customer_id": "Customer",
        "unit_price": "Price",
        "quantity": "Quantity",
        "discount": "Discount",
        "revenue": "Reported",
    }
    retail_config = config(
        revenue_mode=RevenueMode.UNIT_PRICE_TIMES_QUANTITY,
        discount_type=DiscountType.FIXED,
        discount_scope=DiscountScope.PER_LINE,
    )

    validation = validate_sales_data(frame, retail_mapping, retail_config)
    transformed = transform_sales_data(frame, retail_mapping, retail_config, validation, False)
    row = transformed.canonical_data.iloc[0]

    assert validation.invalid_rows == 0
    assert any("reported/calculated" in warning for warning in validation.warnings)
    assert row["gross_sales"] == Decimal("50.00")
    assert row["discount_amount"] == Decimal("5.00")
    assert row["revenue"] == Decimal("45.00")
    assert row["reconciliation_difference"] == Decimal("2.00")


def test_refund_signals_and_completed_failed_payment_conflicts_are_quarantined() -> None:
    frame = pd.DataFrame(
        {
            "Order": ["A1", "A2"],
            "Date": ["2026-01-01", "2026-01-02"],
            "Customer": ["C1", "C2"],
            "Total": [-50, 100],
            "Refund": [50, 0],
            "Status": ["Done", "Done"],
            "Payment": ["Paid", "Failed"],
        }
    )
    retail_config = config(
        negative_revenue_policy=NegativeRevenuePolicy.REFUNDS,
        assume_all_completed=False,
        status_mapping={"Done": StandardOrderStatus.COMPLETED},
        payment_status_mapping={
            "Paid": StandardPaymentStatus.PAID,
            "Failed": StandardPaymentStatus.FAILED,
        },
    )

    result = validate_sales_data(
        frame,
        mapping(refund_amount="Refund", order_status="Status", payment_status="Payment"),
        retail_config,
    )

    assert result.invalid_rows == 2
    assert {issue.code for issue in result.issues} == {
        "refund_signal_conflict",
        "order_payment_conflict",
    }


def test_multiple_currencies_are_valid_but_must_be_reported_separately() -> None:
    frame = pd.DataFrame(
        {
            "Order": ["A1", "A2"],
            "Date": ["2026-01-01", "2026-01-02"],
            "Customer": ["C1", "C2"],
            "Total": [100, 200],
            "Currency": ["USD", "NGN"],
        }
    )

    result = validate_sales_data(frame, mapping(currency="Currency"), config())

    assert result.can_transform is True
    assert any("reported separately" in warning for warning in result.warnings)


def test_partial_return_requires_an_explicit_refund_amount() -> None:
    frame = pd.DataFrame(
        {
            "Order": ["A1"],
            "Date": ["2026-01-01"],
            "Customer": ["C1"],
            "Total": [100],
            "Quantity": [4],
            "Returned": [1],
            "Status": ["Returned"],
        }
    )
    retail_config = config(
        assume_all_completed=False,
        status_mapping={"Returned": StandardOrderStatus.RETURNED},
    )

    result = validate_sales_data(
        frame,
        mapping(
            quantity="Quantity",
            returned_quantity="Returned",
            order_status="Status",
        ),
        retail_config,
    )

    assert result.invalid_rows == 1
    assert "partial_return_requires_refund_amount" in {issue.code for issue in result.issues}


def test_tax_inclusive_refund_keeps_tax_out_of_revenue_refund() -> None:
    frame = pd.DataFrame(
        {
            "Order": ["A1"],
            "Date": ["2026-01-01"],
            "Customer": ["C1"],
            "Total": [100],
            "Tax": [10],
            "Refund": [110],
            "Status": ["Returned"],
        }
    )
    retail_mapping = mapping(tax_amount="Tax", refund_amount="Refund", order_status="Status")
    retail_config = config(
        assume_all_completed=False,
        status_mapping={"Returned": StandardOrderStatus.RETURNED},
        refund_tax_treatment=RefundTaxTreatment.INCLUDES_TAX,
    )

    validation = validate_sales_data(frame, retail_mapping, retail_config)
    transformed = transform_sales_data(frame, retail_mapping, retail_config, validation, False)
    row = transformed.canonical_data.iloc[0]

    assert validation.can_transform is True
    assert row["refund_amount"] == Decimal("100")
    assert row["tax_refunded"] == Decimal("10")
    assert row["tax_amount"] == Decimal("0")


def test_refund_and_tax_mapping_requires_explicit_tax_treatment() -> None:
    frame = pd.DataFrame(
        {
            "Order": ["A1"],
            "Date": ["2026-01-01"],
            "Customer": ["C1"],
            "Total": [100],
            "Tax": [10],
            "Refund": [110],
        }
    )

    validation = validate_sales_data(
        frame,
        mapping(tax_amount="Tax", refund_amount="Refund"),
        config(),
    )

    assert validation.can_transform is False
    assert validation.blocking_errors == (
        "Map the refund tax treatment: confirm whether the refund amount includes tax.",
    )


def test_entire_order_discount_is_allocated_without_changing_its_total() -> None:
    frame = pd.DataFrame(
        {
            "Order": ["A1", "A1"],
            "Date": ["2026-01-01", "2026-01-01"],
            "Customer": ["C1", "C1"],
            "Price": ["60", "40"],
            "Quantity": ["1", "1"],
            "Discount": ["10", "10"],
        }
    )
    retail_mapping = {
        "order_id": "Order",
        "order_date": "Date",
        "customer_id": "Customer",
        "unit_price": "Price",
        "quantity": "Quantity",
        "discount": "Discount",
    }
    retail_config = config(
        revenue_mode=RevenueMode.UNIT_PRICE_TIMES_QUANTITY,
        discount_type=DiscountType.FIXED,
        discount_scope=DiscountScope.ENTIRE_ORDER,
        order_discount_allocation=OrderDiscountAllocation.PROPORTIONAL,
    )

    validation = validate_sales_data(frame, retail_mapping, retail_config)
    transformed = transform_sales_data(frame, retail_mapping, retail_config, validation, False)

    assert validation.can_transform is True
    assert transformed.canonical_data["discount_amount"].sum() == Decimal("10")
    assert transformed.canonical_data["revenue"].sum() == Decimal("90")
