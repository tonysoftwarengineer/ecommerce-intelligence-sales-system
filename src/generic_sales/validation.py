from collections import Counter, defaultdict
from collections.abc import Mapping
from decimal import Decimal
from typing import Optional

import pandas as pd

from src.generic_sales.contracts import (
    DataValidationResult,
    DiscountScope,
    DiscountType,
    NegativeRevenuePolicy,
    RevenueMismatchPolicy,
    RevenueMode,
    SalesProcessingConfig,
    StandardOrderStatus,
    StandardPaymentStatus,
    ValidationIssue,
)
from src.generic_sales.financial_rules import (
    LineFinancials,
    calculate_line_financials,
    normalized_mapping_value,
    parse_decimal,
)


def _is_blank(value: object) -> bool:
    return bool(pd.isna(value)) or (isinstance(value, str) and not value.strip())


def _normalized_identifier(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def validate_sales_data(
    df: pd.DataFrame,
    mapping: Mapping[str, str],
    config: SalesProcessingConfig,
) -> DataValidationResult:
    """Validate retail semantics without mutating or silently repairing source rows."""
    if df.empty:
        return DataValidationResult(
            total_rows=0,
            valid_rows=0,
            invalid_rows=0,
            invalid_row_positions=(),
            issues=(),
            warnings=(),
            blocking_errors=("The uploaded dataset contains no data rows.",),
        )

    total_rows = len(df)
    issues_by_position: dict[int, list[ValidationIssue]] = defaultdict(list)
    blocking_errors: list[str] = []
    warnings: list[str] = []

    def add_issue(position: int, field: str, code: str, message: str) -> None:
        issues_by_position[position].append(ValidationIssue(position + 2, field, code, message))

    order_ids = df[mapping["order_id"]]
    order_dates = df[mapping["order_date"]]
    customer_ids = df[mapping["customer_id"]]
    parsed_dates = _validate_dates(
        order_dates,
        "order_date",
        "Order date",
        config.date_format,
        add_issue,
        required=True,
    )
    for optional_date, label in (
        ("recognition_date", "Recognition date"),
        ("refund_date", "Refund date"),
    ):
        if optional_date in mapping:
            _validate_dates(
                df[mapping[optional_date]],
                optional_date,
                label,
                config.date_format,
                add_issue,
                required=False,
            )

    for position, value in enumerate(order_ids):
        if _is_blank(value):
            add_issue(position, "order_id", "missing_required_value", "Order ID is required.")
    for position, value in enumerate(customer_ids):
        if _is_blank(value):
            add_issue(
                position,
                "customer_id",
                "missing_required_value",
                "Customer ID is required.",
            )

    if config.discount_type is not DiscountType.NONE and "discount" not in mapping:
        blocking_errors.append("The selected discount type requires a mapped discount column.")
    if config.discount_type is DiscountType.NONE and "discount" in mapping:
        warnings.append("A discount column is mapped but the selected discount type is 'none'.")
    if (
        "refund_amount" in mapping
        and "tax_amount" in mapping
        and config.refund_tax_treatment is None
    ):
        blocking_errors.append(
            "Map the refund tax treatment: confirm whether the refund amount includes tax."
        )

    financials = [_line_financials(df, position, mapping, config) for position in range(total_rows)]
    authoritative_values = _validate_financial_values(
        financials,
        mapping,
        config,
        add_issue,
        warnings,
    )

    statuses = _validate_order_statuses(
        df,
        mapping,
        config,
        add_issue,
        blocking_errors,
        warnings,
    )
    payment_statuses = _validate_payment_statuses(
        df,
        mapping,
        config,
        add_issue,
        warnings,
    )
    _validate_adjustments(
        df,
        mapping,
        statuses,
        payment_statuses,
        authoritative_values,
        config,
        add_issue,
    )
    _validate_currency(df, mapping, config, add_issue, warnings)

    for position, is_duplicate in enumerate(df.duplicated(keep="first")):
        if is_duplicate:
            add_issue(
                position,
                "row",
                "exact_duplicate",
                "This row exactly duplicates an earlier row.",
            )

    _validate_order_consistency(
        df,
        mapping,
        order_ids,
        customer_ids,
        parsed_dates,
        df[mapping["state_or_region"]] if "state_or_region" in mapping else None,
        authoritative_values,
        financials,
        statuses,
        payment_statuses,
        config,
        add_issue,
    )

    invalid_row_positions = tuple(sorted(issues_by_position))
    valid_rows = total_rows - len(invalid_row_positions)
    if valid_rows == 0:
        blocking_errors.append("No valid rows remain after data validation.")

    issues = tuple(
        issue for position in sorted(issues_by_position) for issue in issues_by_position[position]
    )
    return DataValidationResult(
        total_rows=total_rows,
        valid_rows=valid_rows,
        invalid_rows=len(invalid_row_positions),
        invalid_row_positions=invalid_row_positions,
        issues=issues,
        warnings=tuple(warnings),
        blocking_errors=tuple(dict.fromkeys(blocking_errors)),
    )


def _line_financials(
    df: pd.DataFrame,
    position: int,
    mapping: Mapping[str, str],
    config: SalesProcessingConfig,
) -> LineFinancials:
    row = df.iloc[position]
    return calculate_line_financials(
        row[mapping["unit_price"]] if "unit_price" in mapping else None,
        row[mapping["quantity"]] if "quantity" in mapping else None,
        row[mapping["discount"]] if "discount" in mapping else None,
        row[mapping["revenue"]] if "revenue" in mapping else None,
        config.discount_type,
        config.discount_scope,
    )


def _validate_financial_values(
    financials: list[LineFinancials],
    mapping: Mapping[str, str],
    config: SalesProcessingConfig,
    add_issue,
    warnings: list[str],
) -> list[Optional[Decimal]]:
    authoritative: list[Optional[Decimal]] = []
    mismatch_count = 0
    zero_count = 0
    negative_count = 0
    for position, values in enumerate(financials):
        if "unit_price" in mapping and values.unit_price is None:
            add_issue(position, "unit_price", "invalid_number", "Unit price must be numeric.")
        if "quantity" in mapping and values.quantity is None:
            add_issue(position, "quantity", "invalid_number", "Quantity must be numeric.")
        if "revenue" in mapping and values.reported_total is None:
            add_issue(position, "revenue", "invalid_number", "Reported total must be numeric.")

        discount_input = values.discount_input
        if config.discount_type is not DiscountType.NONE:
            raw_discount = values.discount
            if config.discount_type is DiscountType.PERCENTAGE and not 0 <= raw_discount <= 100:
                add_issue(
                    position,
                    "discount",
                    "invalid_discount",
                    "Percentage discount must be between 0 and 100.",
                )
            elif raw_discount < 0:
                add_issue(
                    position,
                    "discount",
                    "invalid_discount",
                    "Discount must not be negative.",
                )

        value = (
            values.calculated_total
            if config.revenue_mode is RevenueMode.UNIT_PRICE_TIMES_QUANTITY
            else values.reported_total
        )
        if config.discount_scope is DiscountScope.ENTIRE_ORDER and value is None:
            value = values.subtotal
        authoritative.append(value)

        if (
            value is not None
            and value < 0
            and config.negative_revenue_policy is NegativeRevenuePolicy.INVALID
        ):
            add_issue(
                position,
                "revenue",
                "negative_revenue",
                "Negative revenue is not permitted under the selected policy.",
            )
        elif value is not None and value < 0:
            negative_count += 1
        if value == 0:
            zero_count += 1

        if values.calculated_total is not None and values.reported_total is not None:
            difference = abs(values.reported_total - values.calculated_total)
            if difference > config.mismatch_tolerance:
                mismatch_count += 1
                if config.revenue_mismatch_policy is RevenueMismatchPolicy.QUARANTINE:
                    add_issue(
                        position,
                        "revenue",
                        "revenue_mismatch",
                        "Reported and calculated totals exceed the confirmed tolerance.",
                    )

        if (
            discount_input > 0
            and values.subtotal is not None
            and values.discount > values.subtotal
            and config.discount_type is DiscountType.FIXED
            and config.discount_scope is not DiscountScope.PER_UNIT
        ):
            add_issue(
                position,
                "discount",
                "discount_exceeds_subtotal",
                "Fixed discount exceeds the line subtotal.",
            )

    if mismatch_count and config.revenue_mismatch_policy is RevenueMismatchPolicy.WARN:
        warnings.append(
            f"{mismatch_count} row(s) have reported/calculated revenue differences above "
            f"{config.mismatch_tolerance}; the selected authoritative source will be used."
        )
    if negative_count:
        warnings.append(
            f"{negative_count} row(s) contain negative revenue and will be treated as refunds."
        )
    if zero_count:
        warnings.append(f"{zero_count} row(s) contain zero revenue.")
    return authoritative


def _validate_order_statuses(
    df: pd.DataFrame,
    mapping: Mapping[str, str],
    config: SalesProcessingConfig,
    add_issue,
    blocking_errors: list[str],
    warnings: list[str],
) -> list[Optional[StandardOrderStatus]]:
    if "order_status" not in mapping:
        if not config.assume_all_completed:
            blocking_errors.append(
                "No order-status column is mapped. Confirm that every row is a completed sale."
            )
        return [StandardOrderStatus.COMPLETED] * len(df)

    statuses: list[Optional[StandardOrderStatus]] = []
    counts: Counter[StandardOrderStatus] = Counter()
    for position, raw_value in enumerate(df[mapping["order_status"]]):
        normalized = normalized_mapping_value(raw_value)
        status = config.status_mapping.get(normalized)
        statuses.append(status)
        if not normalized:
            add_issue(position, "order_status", "missing_status", "Order status is required.")
        elif status is None:
            add_issue(
                position,
                "order_status",
                "unknown_status",
                f"Order status '{str(raw_value).strip()}' has not been classified.",
            )
        else:
            counts[status] += 1
    if counts:
        warnings.append(
            "Order statuses: "
            + ", ".join(
                f"{status.value}={count}"
                for status, count in sorted(counts.items(), key=lambda item: item[0].value)
            )
        )
    return statuses


def _validate_payment_statuses(
    df: pd.DataFrame,
    mapping: Mapping[str, str],
    config: SalesProcessingConfig,
    add_issue,
    warnings: list[str],
) -> list[Optional[StandardPaymentStatus]]:
    if "payment_status" not in mapping:
        return [None] * len(df)
    statuses: list[Optional[StandardPaymentStatus]] = []
    for position, raw_value in enumerate(df[mapping["payment_status"]]):
        normalized = normalized_mapping_value(raw_value)
        status = config.payment_status_mapping.get(normalized)
        statuses.append(status)
        if not normalized:
            add_issue(
                position, "payment_status", "missing_payment_status", "Payment status is blank."
            )
        elif status is None:
            add_issue(
                position,
                "payment_status",
                "unknown_payment_status",
                f"Payment status '{str(raw_value).strip()}' has not been classified.",
            )
    if statuses:
        warnings.append("Payment status rules were applied to the uploaded rows.")
    return statuses


def _validate_adjustments(
    df: pd.DataFrame,
    mapping: Mapping[str, str],
    statuses: list[Optional[StandardOrderStatus]],
    payment_statuses: list[Optional[StandardPaymentStatus]],
    authoritative: list[Optional[Decimal]],
    config: SalesProcessingConfig,
    add_issue,
) -> None:
    numeric_fields = (
        "refund_amount",
        "returned_quantity",
        "tax_amount",
        "shipping_amount",
        "chargeback_amount",
        "payment_amount",
    )
    parsed: dict[str, list[Optional[Decimal]]] = {}
    for field in numeric_fields:
        if field not in mapping:
            continue
        parsed[field] = [parse_decimal(value) for value in df[mapping[field]]]
        for position, (raw, value) in enumerate(zip(df[mapping[field]], parsed[field])):
            if _is_blank(raw):
                parsed[field][position] = Decimal("0")
            elif value is None:
                add_issue(position, field, "invalid_number", f"{field} must be numeric.")
            elif value < 0:
                add_issue(position, field, "negative_adjustment", f"{field} must not be negative.")

    quantities = (
        [parse_decimal(value) for value in df[mapping["quantity"]]]
        if "quantity" in mapping
        else [None] * len(df)
    )
    for position, quantity in enumerate(quantities):
        if quantity == 0:
            add_issue(position, "quantity", "zero_quantity", "Quantity must not be zero.")
        if quantity is not None and quantity < 0:
            is_return = statuses[position] is StandardOrderStatus.RETURNED
            if (
                not is_return
                and config.negative_revenue_policy is not NegativeRevenuePolicy.REFUNDS
            ):
                add_issue(
                    position,
                    "quantity",
                    "negative_quantity",
                    "Negative quantity requires an explicitly confirmed return meaning.",
                )

    returned_quantities = parsed.get("returned_quantity")
    if returned_quantities:
        for position, returned in enumerate(returned_quantities):
            quantity = quantities[position]
            if (
                returned is not None
                and quantity is not None
                and quantity > 0
                and returned > quantity
            ):
                add_issue(
                    position,
                    "returned_quantity",
                    "return_exceeds_quantity",
                    "Returned quantity exceeds sold quantity.",
                )

    refunds = parsed.get("refund_amount", [Decimal("0")] * len(df))
    for position, value in enumerate(authoritative):
        refund = refunds[position] or Decimal("0")
        returned = returned_quantities[position] if returned_quantities else None
        quantity = quantities[position]
        if (
            statuses[position] is StandardOrderStatus.RETURNED
            and returned is not None
            and quantity is not None
            and Decimal("0") < returned < quantity
            and refund == 0
        ):
            add_issue(
                position,
                "refund_amount",
                "partial_return_requires_refund_amount",
                "A partial return requires an explicit refund amount.",
            )
        if value is not None and value < 0 and refund > 0:
            add_issue(
                position,
                "refund_amount",
                "refund_signal_conflict",
                "Negative revenue and refund amount would represent the same refund twice.",
            )
        if statuses[position] is StandardOrderStatus.RETURNED and value is not None and value < 0:
            add_issue(
                position,
                "revenue",
                "refund_signal_conflict",
                "Returned status requires the original positive sale amount, not negative revenue.",
            )
        payment = payment_statuses[position]
        if statuses[position] is StandardOrderStatus.COMPLETED and payment in {
            StandardPaymentStatus.FAILED,
            StandardPaymentStatus.VOIDED,
        }:
            add_issue(
                position,
                "payment_status",
                "order_payment_conflict",
                "Completed order conflicts with failed or voided payment status.",
            )


def _validate_currency(
    df: pd.DataFrame,
    mapping: Mapping[str, str],
    config: SalesProcessingConfig,
    add_issue,
    warnings: list[str],
) -> None:
    if "currency" not in mapping:
        return
    currencies = set()
    for position, raw in enumerate(df[mapping["currency"]]):
        value = str(raw).strip().upper()
        if len(value) != 3 or not value.isalpha():
            add_issue(
                position,
                "currency",
                "invalid_currency",
                "Currency must be a three-letter uppercase code.",
            )
        else:
            currencies.add(value)
    if len(currencies) > 1:
        warnings.append(
            "Multiple currencies were detected and must be reported separately: "
            + ", ".join(sorted(currencies))
        )
    elif currencies and config.currency not in currencies:
        warnings.append("The fallback currency differs from the mapped row currency.")


def _validate_dates(values, field, label, date_format, add_issue, required):
    blank = values.map(_is_blank)
    parsed = pd.to_datetime(values, format=date_format, errors="coerce", exact=True)
    for position, (is_blank, parsed_date) in enumerate(zip(blank, parsed)):
        if is_blank and required:
            add_issue(position, field, "missing_required_value", f"{label} is required.")
        elif not is_blank and pd.isna(parsed_date):
            add_issue(
                position,
                field,
                "invalid_date",
                f"{label} does not match the confirmed date format.",
            )
    return parsed


def _validate_order_consistency(
    df,
    mapping,
    order_ids,
    customer_ids,
    parsed_dates,
    states,
    authoritative,
    financials,
    statuses,
    payment_statuses,
    config,
    add_issue,
) -> None:
    positions_by_order: dict[object, list[int]] = defaultdict(list)
    for position, order_id in enumerate(order_ids):
        if not _is_blank(order_id):
            positions_by_order[_normalized_identifier(order_id)].append(position)

    for positions in positions_by_order.values():
        if len(positions) < 2:
            continue
        conflicts = []
        customers = {
            _normalized_identifier(customer_ids.iloc[position])
            for position in positions
            if not _is_blank(customer_ids.iloc[position])
        }
        dates = {
            parsed_dates.iloc[position]
            for position in positions
            if pd.notna(parsed_dates.iloc[position])
        }
        if len(customers) > 1:
            conflicts.append("customer_id")
        if len(dates) > 1:
            conflicts.append("order_date")
        if config.revenue_mode is RevenueMode.ORDER_TOTAL:
            totals = {
                authoritative[position]
                for position in positions
                if authoritative[position] is not None
            }
            if len(totals) > 1:
                conflicts.append("revenue")
            order_statuses = {statuses[position] for position in positions}
            if len(order_statuses) > 1:
                conflicts.append("order_status")
            payments = {payment_statuses[position] for position in positions}
            if len(payments) > 1:
                conflicts.append("payment_status")
            for field in (
                "recognition_date",
                "refund_date",
                "refund_amount",
                "tax_amount",
                "shipping_amount",
                "chargeback_amount",
                "payment_amount",
                "currency",
            ):
                if field not in mapping:
                    continue
                values = {
                    _normalized_order_value(df.iloc[position][mapping[field]], field)
                    for position in positions
                }
                if len(values) > 1:
                    conflicts.append(field)
        if states is not None:
            regions = {
                None
                if _is_blank(states.iloc[position])
                else _normalized_identifier(states.iloc[position])
                for position in positions
            }
            if len(regions) > 1:
                conflicts.append("state_or_region")
        if config.discount_scope is DiscountScope.ENTIRE_ORDER:
            discounts = {
                financials[position].discount_input
                for position in positions
                if financials[position].discount_input
            }
            if len(discounts) > 1:
                conflicts.append("discount")
        for field in conflicts:
            for position in positions:
                add_issue(
                    position,
                    field,
                    "order_conflict",
                    f"Rows for this order contain conflicting {field} values.",
                )


def _normalized_order_value(value, field):
    if field in {
        "refund_amount",
        "tax_amount",
        "shipping_amount",
        "chargeback_amount",
        "payment_amount",
    }:
        return parse_decimal(value) if not _is_blank(value) else Decimal("0")
    if _is_blank(value):
        return ""
    text = str(value).strip()
    return text.upper() if field == "currency" else text.casefold()
