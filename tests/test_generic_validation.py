import pandas as pd
import pandas.testing as pdt
import pytest

from src.generic_sales.contracts import (
    NegativeRevenuePolicy,
    RevenueMode,
    SalesProcessingConfig,
)
from src.generic_sales.validation import validate_sales_data


def config(
    revenue_mode: RevenueMode = RevenueMode.ROW_TOTAL,
    negative_policy: NegativeRevenuePolicy = NegativeRevenuePolicy.INVALID,
) -> SalesProcessingConfig:
    return SalesProcessingConfig(
        revenue_mode=revenue_mode,
        negative_revenue_policy=negative_policy,
        date_format="%Y-%m-%d",
        currency="USD",
        assume_all_completed=True,
    )


def mapping_for(revenue_mode: RevenueMode = RevenueMode.ROW_TOTAL) -> dict[str, str]:
    base = {
        "order_id": "Order",
        "order_date": "Date",
        "customer_id": "Customer",
    }
    if revenue_mode is RevenueMode.UNIT_PRICE_TIMES_QUANTITY:
        return {**base, "unit_price": "Price", "quantity": "Quantity"}
    return {**base, "revenue": "Total"}


def sales_frame(**overrides: list[object]) -> pd.DataFrame:
    data: dict[str, list[object]] = {
        "Order": ["A001", "A002"],
        "Date": ["2025-01-01", "2025-01-02"],
        "Customer": ["C001", "C002"],
        "Total": [100.0, 200.0],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def issue_codes(result) -> list[str]:
    return [issue.code for issue in result.issues]


def test_valid_row_total_data_can_be_transformed_without_confirmation():
    result = validate_sales_data(sales_frame(), mapping_for(), config())

    assert result.total_rows == 2
    assert result.valid_rows == 2
    assert result.invalid_rows == 0
    assert result.invalid_row_positions == ()
    assert result.issues == ()
    assert result.can_transform is True
    assert result.requires_confirmation is False


def test_invalid_required_values_dates_and_numbers_accumulate_per_row():
    frame = sales_frame(
        Order=["", "A002"],
        Date=["not-a-date", None],
        Customer=[None, "   "],
        Total=["unknown", "also-unknown"],
    )

    result = validate_sales_data(frame, mapping_for(), config())

    assert result.invalid_row_positions == (0, 1)
    assert result.valid_rows == 0
    assert len(result.issues) == 7
    assert result.issues[0].row_number == 2
    assert result.issues[-1].row_number == 3
    assert set(issue_codes(result)) == {
        "missing_required_value",
        "invalid_date",
        "invalid_number",
    }
    assert result.can_transform is False
    assert result.blocking_errors == ("No valid rows remain after data validation.",)


def test_source_row_numbers_are_csv_line_numbers_and_positions_are_unique():
    frame = sales_frame(Date=["bad", "2025-01-02"], Total=["bad", 200])

    result = validate_sales_data(frame, mapping_for(), config())

    assert result.invalid_row_positions == (0,)
    assert {issue.row_number for issue in result.issues} == {2}
    assert result.requires_confirmation is True


def test_exact_duplicates_keep_first_and_quarantine_later_rows():
    frame = pd.concat([sales_frame().iloc[[0]]] * 3, ignore_index=True)

    result = validate_sales_data(frame, mapping_for(), config())

    assert result.valid_rows == 1
    assert result.invalid_row_positions == (1, 2)
    duplicate_issues = [issue for issue in result.issues if issue.code == "exact_duplicate"]
    assert [issue.row_number for issue in duplicate_issues] == [3, 4]


def test_repeated_order_ids_are_valid_line_items_when_order_data_is_consistent():
    frame = sales_frame(
        Order=["A001", "A001"],
        Date=["2025-01-01", "2025-01-01"],
        Customer=["C001", "C001"],
        Total=[100, 50],
    )

    result = validate_sales_data(frame, mapping_for(), config())

    assert result.valid_rows == 2
    assert result.issues == ()


@pytest.mark.parametrize(
    ("field", "values"),
    [
        ("Customer", ["C001", "C999"]),
        ("Date", ["2025-01-01", "2025-01-02"]),
    ],
)
def test_order_identity_conflicts_quarantine_every_row_in_the_order(field, values):
    frame = sales_frame(
        Order=["A001", "A001", "A002"],
        Date=["2025-01-01", "2025-01-01", "2025-01-03"],
        Customer=["C001", "C001", "C002"],
        Total=[100, 50, 25],
    )
    frame[field] = values + [frame[field].iloc[2]]

    result = validate_sales_data(frame, mapping_for(), config())

    assert result.invalid_row_positions == (0, 1)
    conflict_issues = [issue for issue in result.issues if issue.code == "order_conflict"]
    assert [issue.row_number for issue in conflict_issues] == [2, 3]


def test_order_total_conflict_quarantines_entire_order_without_exposing_values():
    frame = sales_frame(
        Order=["A001", "A001", "A002"],
        Date=["2025-01-01", "2025-01-01", "2025-01-03"],
        Customer=["C001", "C001", "C002"],
        Total=[100, 125, 25],
    )

    result = validate_sales_data(
        frame,
        mapping_for(RevenueMode.ORDER_TOTAL),
        config(RevenueMode.ORDER_TOTAL),
    )

    assert result.invalid_row_positions == (0, 1)
    messages = [issue.message for issue in result.issues]
    assert all("100" not in message and "125" not in message for message in messages)


def test_mapped_state_conflict_quarantines_every_row_in_the_order():
    frame = sales_frame(
        Order=["A001", "A001", "A002"],
        Date=["2025-01-01", "2025-01-01", "2025-01-03"],
        Customer=["C001", "C001", "C002"],
        Total=[100, 50, 25],
        State=["Lagos", "Abuja", "Kano"],
    )
    mapping = {**mapping_for(), "state_or_region": "State"}

    result = validate_sales_data(frame, mapping, config())

    assert result.invalid_row_positions == (0, 1)
    state_conflicts = [
        issue
        for issue in result.issues
        if issue.code == "order_conflict" and issue.field == "state_or_region"
    ]
    assert [issue.row_number for issue in state_conflicts] == [2, 3]


def test_product_category_and_quantity_may_differ_across_order_line_items():
    frame = sales_frame(
        Order=["A001", "A001"],
        Date=["2025-01-01", "2025-01-01"],
        Customer=["C001", "C001"],
        Total=[100, 50],
        State=["Lagos", "Lagos"],
        Category=["Shoes", "Socks"],
        Quantity=[1, 3],
    )
    mapping = {
        **mapping_for(),
        "state_or_region": "State",
        "product_category": "Category",
        "quantity": "Quantity",
    }

    result = validate_sales_data(frame, mapping, config())

    assert result.valid_rows == 2
    assert result.issues == ()


def test_negative_revenue_is_invalid_under_invalid_policy():
    frame = sales_frame(Total=[-25, 200])

    result = validate_sales_data(frame, mapping_for(), config())

    assert result.invalid_row_positions == (0,)
    assert "negative_revenue" in issue_codes(result)
    assert result.warnings == ()


def test_negative_revenue_is_kept_and_aggregated_under_refund_policy():
    frame = sales_frame(Total=[-25, -10])

    result = validate_sales_data(
        frame,
        mapping_for(),
        config(negative_policy=NegativeRevenuePolicy.REFUNDS),
    )

    assert result.valid_rows == 2
    assert result.issues == ()
    assert result.warnings == ("2 row(s) contain negative revenue and will be treated as refunds.",)
    assert all("25" not in warning and "10" not in warning for warning in result.warnings)


def test_zero_revenue_remains_valid_and_creates_aggregate_warning():
    frame = sales_frame(Total=[0, 200])

    result = validate_sales_data(frame, mapping_for(), config())

    assert result.valid_rows == 2
    assert result.warnings == ("1 row(s) contain zero revenue.",)


def test_unit_price_times_quantity_mode_validates_inputs_and_computes_policy_revenue():
    frame = pd.DataFrame(
        {
            "Order": ["A001", "A002", "A003"],
            "Date": ["2025-01-01", "2025-01-02", "2025-01-03"],
            "Customer": ["C001", "C002", "C003"],
            "Price": [10, "bad", -5],
            "Quantity": [2, 3, 2],
        }
    )

    result = validate_sales_data(
        frame,
        mapping_for(RevenueMode.UNIT_PRICE_TIMES_QUANTITY),
        config(RevenueMode.UNIT_PRICE_TIMES_QUANTITY),
    )

    assert result.invalid_row_positions == (1, 2)
    assert {issue.field for issue in result.issues} == {"unit_price", "revenue"}


def test_order_total_mode_allows_repeated_consistent_totals():
    frame = sales_frame(
        Order=["A001", "A001"],
        Date=["2025-01-01", "2025-01-01"],
        Customer=["C001", "C001"],
        Total=[150, 150],
    )

    result = validate_sales_data(
        frame,
        mapping_for(RevenueMode.ORDER_TOTAL),
        config(RevenueMode.ORDER_TOTAL),
    )

    assert result.valid_rows == 1
    assert result.invalid_row_positions == (1,)
    assert issue_codes(result) == ["exact_duplicate"]


def test_empty_dataframe_is_blocked():
    frame = pd.DataFrame(columns=["Order", "Date", "Customer", "Total"])

    result = validate_sales_data(frame, mapping_for(), config())

    assert result.total_rows == 0
    assert result.can_transform is False
    assert result.blocking_errors == ("The uploaded dataset contains no data rows.",)


def test_validation_does_not_mutate_the_input_dataframe():
    frame = sales_frame(Date=["bad", "2025-01-02"], Total=[-10, 0])
    original = frame.copy(deep=True)

    validate_sales_data(frame, mapping_for(), config())

    pdt.assert_frame_equal(frame, original)
