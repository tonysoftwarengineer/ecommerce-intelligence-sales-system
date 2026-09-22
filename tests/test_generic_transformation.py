from dataclasses import replace

import pandas as pd
import pandas.testing as pdt
import pytest

from src.generic_sales.contracts import (
    DataValidationResult,
    NegativeRevenuePolicy,
    RevenueMode,
    SalesProcessingConfig,
    ValidationIssue,
)
from src.generic_sales.transformation import (
    QuarantineConfirmationRequired,
    TransformationBlockedError,
    transform_sales_data,
)


def _config(mode: RevenueMode = RevenueMode.ROW_TOTAL) -> SalesProcessingConfig:
    return SalesProcessingConfig(
        revenue_mode=mode,
        negative_revenue_policy=NegativeRevenuePolicy.INVALID,
        date_format="%d/%m/%Y",
        currency="NGN",
        assume_all_completed=True,
    )


def _valid_validation(row_count: int) -> DataValidationResult:
    return DataValidationResult(
        total_rows=row_count,
        valid_rows=row_count,
        invalid_rows=0,
        invalid_row_positions=(),
        issues=(),
        warnings=(),
        blocking_errors=(),
    )


def _base_mapping() -> dict[str, str]:
    return {
        "order_id": "Invoice",
        "order_date": "Date",
        "customer_id": "Buyer",
        "revenue": "Total",
    }


def test_row_total_transforms_exact_types_optional_fields_and_currency() -> None:
    source = pd.DataFrame(
        {
            "Invoice": ["A-1", "A-2"],
            "Date": ["31/01/2025", "01/02/2025"],
            "Buyer": ["C-1", "C-2"],
            "Total": ["12.50", "7"],
            "Units": ["2", "1"],
            "Category": ["Shoes", "Books"],
            "Region": ["Lagos", "Abuja"],
        }
    )
    original = source.copy(deep=True)
    mapping = {
        **_base_mapping(),
        "quantity": "Units",
        "product_category": "Category",
        "state_or_region": "Region",
    }

    result = transform_sales_data(source, mapping, _config(), _valid_validation(2), False)

    assert {
        "source_row",
        "order_id",
        "order_date",
        "recognition_date",
        "customer_id",
        "gross_sales",
        "discount_amount",
        "refund_amount",
        "revenue",
        "net_collected",
        "currency",
        "quantity",
        "product_category",
        "state_or_region",
    }.issubset(result.canonical_data.columns)
    assert result.canonical_data["source_row"].tolist() == [2, 3]
    assert result.canonical_data["order_date"].tolist() == [
        pd.Timestamp("2025-01-31"),
        pd.Timestamp("2025-02-01"),
    ]
    assert result.canonical_data["revenue"].tolist() == [12.5, 7.0]
    assert result.canonical_data["quantity"].tolist() == [2, 1]
    assert result.canonical_data["currency"].tolist() == ["NGN", "NGN"]
    assert result.quarantine.empty
    pdt.assert_frame_equal(source, original)


def test_unit_price_times_quantity_computes_revenue() -> None:
    source = pd.DataFrame(
        {
            "Invoice": ["A-1", "A-2"],
            "Date": ["01/03/2025", "02/03/2025"],
            "Buyer": ["C-1", "C-2"],
            "Price": ["10.25", "4"],
            "Units": ["2", "3"],
        }
    )
    mapping = {
        "order_id": "Invoice",
        "order_date": "Date",
        "customer_id": "Buyer",
        "unit_price": "Price",
        "quantity": "Units",
    }

    result = transform_sales_data(
        source,
        mapping,
        _config(RevenueMode.UNIT_PRICE_TIMES_QUANTITY),
        _valid_validation(2),
        False,
    )

    assert result.canonical_data["revenue"].tolist() == [20.5, 12.0]
    assert result.canonical_data["quantity"].tolist() == [2, 3]
    assert "unit_price" not in result.canonical_data.columns


def test_product_fields_are_preserved_as_text_without_losing_sku_zeroes() -> None:
    source = pd.DataFrame(
        {
            "Invoice": ["A-1"],
            "Date": ["01/03/2025"],
            "Buyer": ["C-1"],
            "Total": ["12"],
            "StockCode": ["0007"],
            "Description": ["Blue Mug"],
            "UOM": ["piece"],
            "Units": ["2"],
        }
    )
    mapping = {
        **_base_mapping(),
        "product_id": "StockCode",
        "product_name": "Description",
        "unit_of_measure": "UOM",
        "quantity": "Units",
    }

    result = transform_sales_data(source, mapping, _config(), _valid_validation(1), False)

    row = result.canonical_data.iloc[0]
    assert row["product_id"] == "0007"
    assert row["product_name"] == "Blue Mug"
    assert row["unit_of_measure"] == "piece"


def test_order_total_counts_each_order_once_and_excludes_line_dimensions() -> None:
    source = pd.DataFrame(
        {
            "Invoice": ["A-1", "A-1", "A-2"],
            "Date": ["01/03/2025", "01/03/2025", "02/03/2025"],
            "Buyer": ["C-1", "C-1", "C-2"],
            "Total": ["150", "150", "80"],
            "Units": ["not-applicable", "not-applicable", "not-applicable"],
            "Category": ["Shoes", "Socks", "Books"],
            "Region": ["Lagos", "Lagos", "Abuja"],
        }
    )
    mapping = {
        **_base_mapping(),
        "quantity": "Units",
        "product_category": "Category",
        "state_or_region": "Region",
    }

    result = transform_sales_data(
        source,
        mapping,
        _config(RevenueMode.ORDER_TOTAL),
        _valid_validation(3),
        False,
    )

    assert result.canonical_data["order_id"].tolist() == ["A-1", "A-2"]
    assert result.canonical_data["revenue"].sum() == 230
    assert result.canonical_data["source_row"].tolist() == [2, 4]
    assert "quantity" not in result.canonical_data.columns
    assert "product_category" not in result.canonical_data.columns
    assert result.canonical_data["state_or_region"].tolist() == ["Lagos", "Abuja"]
    assert "quantity, product_category" in result.warnings[0]


def test_order_total_normalizes_identifiers_before_deduplication() -> None:
    source = pd.DataFrame(
        {
            "Invoice": ["A-1", " A-1 "],
            "Date": ["01/03/2025", "01/03/2025"],
            "Buyer": ["C-1", " C-1 "],
            "Total": ["150", "150"],
            "Category": ["Shoes", "Socks"],
        }
    )

    result = transform_sales_data(
        source,
        _base_mapping(),
        _config(RevenueMode.ORDER_TOTAL),
        _valid_validation(2),
        False,
    )

    assert result.canonical_data["order_id"].tolist() == ["A-1"]
    assert result.canonical_data["customer_id"].tolist() == ["C-1"]
    assert result.canonical_data["revenue"].sum() == 150


def test_invalid_rows_require_confirmation_and_are_quarantined_with_issues() -> None:
    source = pd.DataFrame(
        {
            "Invoice": ["A-1", "A-2", "A-3"],
            "Date": ["01/03/2025", "bad-date", "03/03/2025"],
            "Buyer": ["C-1", "C-2", None],
            "Total": ["10", "20", "30"],
        }
    )
    validation = DataValidationResult(
        total_rows=3,
        valid_rows=1,
        invalid_rows=2,
        invalid_row_positions=(1, 2),
        issues=(
            ValidationIssue(3, "order_date", "invalid_date", "Date is invalid"),
            ValidationIssue(4, "customer_id", "missing_value", "Customer is missing"),
            ValidationIssue(4, "customer_id", "required", "Customer ID is required"),
        ),
        warnings=("Two rows will be quarantined",),
        blocking_errors=(),
    )

    with pytest.raises(QuarantineConfirmationRequired):
        transform_sales_data(source, _base_mapping(), _config(), validation, False)

    result = transform_sales_data(source, _base_mapping(), _config(), validation, True)

    assert result.canonical_data["source_row"].tolist() == [2]
    assert result.quarantine["source_row"].tolist() == [3, 4]
    assert result.quarantine["issue_codes"].tolist() == [
        ["invalid_date"],
        ["missing_value", "required"],
    ]
    assert result.quarantine["issue_reasons"].tolist() == [
        ["Date is invalid"],
        ["Customer is missing", "Customer ID is required"],
    ]
    assert result.warnings == (
        "Two rows will be quarantined",
        "Order date was used as the revenue recognition date.",
    )


def test_unusable_validation_blocks_transformation() -> None:
    source = pd.DataFrame({"Invoice": ["A-1"], "Date": ["bad"], "Buyer": ["C-1"], "Total": ["10"]})
    blocked = DataValidationResult(
        total_rows=1,
        valid_rows=0,
        invalid_rows=1,
        invalid_row_positions=(0,),
        issues=(),
        warnings=(),
        blocking_errors=("No valid rows remain",),
    )

    with pytest.raises(TransformationBlockedError, match="No valid rows remain"):
        transform_sales_data(source, _base_mapping(), _config(), blocked, True)


def test_validation_warning_is_preserved_with_transformation_warning() -> None:
    source = pd.DataFrame(
        {
            "Invoice": ["A-1"],
            "Date": ["01/03/2025"],
            "Buyer": ["C-1"],
            "Total": ["10"],
            "Category": ["Shoes"],
        }
    )
    validation = replace(_valid_validation(1), warnings=("Revenue contains zero values",))
    mapping = {**_base_mapping(), "product_category": "Category"}

    result = transform_sales_data(
        source,
        mapping,
        _config(RevenueMode.ORDER_TOTAL),
        validation,
        False,
    )

    assert result.warnings[0] == "Revenue contains zero values"
    assert "product_category" in result.warnings[1]
