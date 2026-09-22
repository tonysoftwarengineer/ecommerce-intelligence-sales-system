"""Transform validated retail data into an auditable canonical sales schema."""

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

import pandas as pd

from src.generic_sales.contracts import (
    DataValidationResult,
    DiscountScope,
    DiscountType,
    OrderDiscountAllocation,
    RefundTaxTreatment,
    RevenueMode,
    SalesProcessingConfig,
    StandardOrderStatus,
    StandardPaymentStatus,
    required_fields_for_mode,
)
from src.generic_sales.financial_rules import (
    LineFinancials,
    calculate_line_financials,
    normalized_mapping_value,
    parse_decimal,
)


class SalesTransformationError(ValueError):
    """Base exception for expected canonical-transformation failures."""


class TransformationBlockedError(SalesTransformationError):
    pass


class QuarantineConfirmationRequired(SalesTransformationError):
    pass


class TransformationInputError(SalesTransformationError):
    pass


@dataclass(frozen=True)
class CanonicalTransformationResult:
    canonical_data: pd.DataFrame
    quarantine: pd.DataFrame
    warnings: tuple[str, ...]


def transform_sales_data(
    df: pd.DataFrame,
    mapping: Mapping[str, str],
    config: SalesProcessingConfig,
    validation: DataValidationResult,
    confirm_quarantine: bool,
) -> CanonicalTransformationResult:
    """Transform accepted rows and preserve rejected source rows with reasons."""
    _ensure_transformation_allowed(df, mapping, config, validation, confirm_quarantine)
    source = df.copy(deep=True)
    source.insert(0, "source_row", range(2, len(source) + 2))
    invalid_positions = set(validation.invalid_row_positions)
    accepted = source.iloc[
        [position for position in range(len(source)) if position not in invalid_positions]
    ].copy()
    if config.revenue_mode is RevenueMode.ORDER_TOTAL:
        normalized_order_ids = accepted[mapping["order_id"]].map(_text)
        accepted = accepted.loc[~normalized_order_ids.duplicated(keep="first")].copy()

    quarantine = _build_quarantine(source, validation)
    canonical, transformation_warnings = _build_canonical(accepted, mapping, config)
    return CanonicalTransformationResult(
        canonical_data=canonical,
        quarantine=quarantine,
        warnings=tuple(validation.warnings) + transformation_warnings,
    )


def _ensure_transformation_allowed(
    df: pd.DataFrame,
    mapping: Mapping[str, str],
    config: SalesProcessingConfig,
    validation: DataValidationResult,
    confirm_quarantine: bool,
) -> None:
    if not validation.can_transform:
        details = "; ".join(validation.blocking_errors) or "no valid rows remain"
        raise TransformationBlockedError(f"Dataset cannot be transformed: {details}")
    if validation.requires_confirmation and not confirm_quarantine:
        raise QuarantineConfirmationRequired(
            "Invalid rows must be explicitly confirmed before they can be quarantined"
        )
    if validation.total_rows != len(df):
        raise TransformationInputError(
            "Validation result does not belong to this dataframe: row counts differ"
        )
    positions = validation.invalid_row_positions
    if len(set(positions)) != len(positions):
        raise TransformationInputError("Validation contains duplicate invalid row positions")
    if any(position < 0 or position >= len(df) for position in positions):
        raise TransformationInputError("Validation contains an invalid row position")
    if validation.invalid_rows != len(positions):
        raise TransformationInputError("Validation invalid-row count is inconsistent")
    if validation.valid_rows != len(df) - len(positions):
        raise TransformationInputError("Validation valid-row count is inconsistent")

    missing_mappings = [
        field for field in required_fields_for_mode(config.revenue_mode) if field not in mapping
    ]
    if missing_mappings:
        raise TransformationInputError(
            f"Required canonical fields are not mapped: {', '.join(missing_mappings)}"
        )
    missing_columns = sorted(set(mapping.values()).difference(df.columns))
    if missing_columns:
        raise TransformationInputError(
            f"Mapped source columns do not exist: {', '.join(missing_columns)}"
        )
    if "source_row" in df.columns:
        raise TransformationInputError(
            "Uploaded data must not contain the reserved column 'source_row'"
        )


def _build_quarantine(source: pd.DataFrame, validation: DataValidationResult) -> pd.DataFrame:
    original_columns = list(source.columns)
    quarantine = source.iloc[sorted(validation.invalid_row_positions)].copy().reset_index(drop=True)
    issues_by_row: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for issue in validation.issues:
        issues_by_row[issue.row_number].append((issue.code, issue.message))
    quarantine["issue_codes"] = [
        [code for code, _ in issues_by_row.get(int(source_row), [])]
        for source_row in quarantine["source_row"]
    ]
    quarantine["issue_reasons"] = [
        [message for _, message in issues_by_row.get(int(source_row), [])]
        for source_row in quarantine["source_row"]
    ]
    return quarantine.loc[:, original_columns + ["issue_codes", "issue_reasons"]]


def _build_canonical(
    accepted: pd.DataFrame,
    mapping: Mapping[str, str],
    config: SalesProcessingConfig,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    rows: list[dict[str, object]] = []
    prepared = [_prepare_source_row(row, mapping, config) for _, row in accepted.iterrows()]
    _apply_order_discounts(prepared, config)
    for prepared_row in prepared:
        rows.append(_canonical_row(prepared_row, mapping, config))
    canonical = pd.DataFrame(rows)
    # A mapped optional field is still part of the confirmed schema even when
    # every accepted value is blank. Preserve that column so capability-aware
    # analytics can label the missing values instead of crashing on a missing
    # DataFrame column.
    for field in (
        "line_item_id",
        "quantity",
        "returned_quantity",
        "product_id",
        "product_name",
        "unit_of_measure",
        "product_category",
        "state_or_region",
        "payment_amount",
    ):
        if config.revenue_mode is RevenueMode.ORDER_TOTAL and field in {
            "line_item_id",
            "quantity",
            "returned_quantity",
            "product_id",
            "product_name",
            "unit_of_measure",
            "product_category",
        }:
            continue
        if field in mapping and field not in canonical.columns:
            canonical[field] = None
    warnings: list[str] = []
    if config.revenue_mode is RevenueMode.ORDER_TOTAL:
        excluded = [
            field
            for field in (
                "quantity",
                "product_id",
                "product_name",
                "unit_of_measure",
                "product_category",
            )
            if field in mapping
        ]
        if excluded:
            warnings.append(
                "Order-total mode excluded fields that cannot be allocated to individual "
                "products: " + ", ".join(excluded)
            )
    if "recognition_date" not in mapping:
        warnings.append("Order date was used as the revenue recognition date.")
    if (
        "refund_date" not in mapping
        and not canonical.empty
        and canonical["refund_amount"].map(lambda value: value > 0).any()
    ):
        warnings.append(
            "Refund date was not mapped; refunds were assigned to the revenue recognition date."
        )
    if (
        config.discount_scope is DiscountScope.ENTIRE_ORDER
        and config.order_discount_allocation is OrderDiscountAllocation.UNALLOCATED
    ):
        warnings.append(
            "Order-level discounts remain unallocated; category revenue is shown before "
            "those discounts."
        )
    return canonical, tuple(warnings)


def _prepare_source_row(row, mapping, config) -> dict[str, object]:
    financials = calculate_line_financials(
        row[mapping["unit_price"]] if "unit_price" in mapping else None,
        row[mapping["quantity"]] if "quantity" in mapping else None,
        row[mapping["discount"]] if "discount" in mapping else None,
        row[mapping["revenue"]] if "revenue" in mapping else None,
        config.discount_type,
        config.discount_scope,
    )
    authoritative = (
        financials.calculated_total
        if config.revenue_mode is RevenueMode.UNIT_PRICE_TIMES_QUANTITY
        else financials.reported_total
    )
    if authoritative is None and config.discount_scope is DiscountScope.ENTIRE_ORDER:
        authoritative = financials.subtotal
    if authoritative is None:
        raise TransformationInputError("Accepted row has no authoritative revenue value")

    status = StandardOrderStatus.COMPLETED
    if "order_status" in mapping:
        status = config.status_mapping[normalized_mapping_value(row[mapping["order_status"]])]
    payment_status = None
    if "payment_status" in mapping:
        payment_status = config.payment_status_mapping[
            normalized_mapping_value(row[mapping["payment_status"]])
        ]
    return {
        "_order_key": _text(row[mapping["order_id"]]),
        "source": row,
        "financials": financials,
        "authoritative": authoritative,
        "allocated_order_discount": Decimal("0"),
        "status": status,
        "payment_status": payment_status,
    }


def _apply_order_discounts(
    prepared: list[dict[str, object]],
    config: SalesProcessingConfig,
) -> None:
    if config.discount_scope is not DiscountScope.ENTIRE_ORDER:
        return
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in prepared:
        groups[str(row["_order_key"])].append(row)

    for rows in groups.values():
        financial_rows: list[LineFinancials] = []
        for row in rows:
            values = row["financials"]
            assert isinstance(values, LineFinancials)
            financial_rows.append(values)
        subtotals = [values.subtotal or Decimal("0") for values in financial_rows]
        total = sum(subtotals, Decimal("0"))
        if config.discount_type is DiscountType.PERCENTAGE:
            percentage = next(
                (values.discount_input for values in financial_rows if values.discount_input > 0),
                Decimal("0"),
            )
            order_discount = total * percentage / Decimal("100")
        else:
            order_discount = next(
                (values.discount_input for values in financial_rows if values.discount_input > 0),
                Decimal("0"),
            )
        if not order_discount:
            continue
        if config.order_discount_allocation is OrderDiscountAllocation.PROPORTIONAL:
            allocated = Decimal("0")
            for index, (row, subtotal) in enumerate(zip(rows, subtotals)):
                share = (
                    order_discount - allocated
                    if index == len(rows) - 1
                    else order_discount * subtotal / total
                )
                row["allocated_order_discount"] = share
                if config.revenue_mode is RevenueMode.UNIT_PRICE_TIMES_QUANTITY:
                    row["authoritative"] = row["authoritative"] - share  # type: ignore[operator]
                allocated += share
        else:
            rows[0]["allocated_order_discount"] = order_discount
            if config.revenue_mode is RevenueMode.UNIT_PRICE_TIMES_QUANTITY:
                rows[0]["authoritative"] = rows[0]["authoritative"] - order_discount  # type: ignore[operator]


def _canonical_row(
    prepared: dict[str, Any],
    mapping: Mapping[str, str],
    config: SalesProcessingConfig,
) -> dict[str, object]:
    source = prepared["source"]
    financials: LineFinancials = prepared["financials"]
    sale_amount: Decimal = prepared["authoritative"]
    status: StandardOrderStatus = prepared["status"]
    payment: Optional[StandardPaymentStatus] = prepared["payment_status"]
    explicit_refund = _mapped_decimal(source, mapping, "refund_amount")
    chargeback = _mapped_decimal(source, mapping, "chargeback_amount")
    tax = _mapped_decimal(source, mapping, "tax_amount")
    shipping = _mapped_decimal(source, mapping, "shipping_amount")
    payment_amount = _mapped_decimal(source, mapping, "payment_amount", nullable=True)
    refund = Decimal("0")
    recognized_sale = Decimal("0")
    pending_value = Decimal("0")

    if sale_amount < 0:
        refund = abs(sale_amount)
    elif status is StandardOrderStatus.COMPLETED:
        recognized_sale = sale_amount
        refund = explicit_refund
    elif status is StandardOrderStatus.PENDING:
        pending_value = sale_amount
    elif status is StandardOrderStatus.RETURNED:
        recognized_sale = sale_amount
        refund = explicit_refund or sale_amount

    recognized_tax = tax if recognized_sale else Decimal("0")
    refunded_tax = Decimal("0")
    if explicit_refund and config.refund_tax_treatment is RefundTaxTreatment.INCLUDES_TAX:
        refunded_tax = min(explicit_refund, recognized_tax)
        refund -= refunded_tax

    net_revenue = recognized_sale - refund
    if payment is StandardPaymentStatus.CHARGEBACK_LOST:
        chargeback = chargeback or recognized_sale
    disputed_value = recognized_sale if payment is StandardPaymentStatus.DISPUTED else Decimal("0")
    net_collected = payment_amount - chargeback if payment_amount is not None else None
    recognition_date = _mapped_date(source, mapping, "recognition_date", config.date_format)
    if recognition_date is None:
        recognition_date = _mapped_date(source, mapping, "order_date", config.date_format)

    gross = financials.subtotal
    if gross is None:
        gross = max(recognized_sale + financials.discount, Decimal("0"))
    if not recognized_sale:
        gross = Decimal("0")
    discount_amount = (
        prepared["allocated_order_discount"]
        if config.discount_scope is DiscountScope.ENTIRE_ORDER
        else financials.discount
    )
    recognized_discount = discount_amount if recognized_sale else Decimal("0")
    net_tax = recognized_tax - refunded_tax
    recognized_shipping = shipping if recognized_sale else Decimal("0")
    category_revenue = net_revenue
    if (
        config.discount_scope is DiscountScope.ENTIRE_ORDER
        and config.order_discount_allocation is OrderDiscountAllocation.UNALLOCATED
    ):
        category_revenue = max(financials.subtotal or recognized_sale, Decimal("0")) - refund

    row = {
        "source_row": int(source["source_row"]),
        "order_id": _text(source[mapping["order_id"]]),
        "line_item_id": _optional_text(source, mapping, "line_item_id"),
        "order_date": _mapped_date(source, mapping, "order_date", config.date_format),
        "recognition_date": recognition_date,
        "refund_date": _mapped_date(source, mapping, "refund_date", config.date_format),
        "customer_id": _text(source[mapping["customer_id"]]),
        "order_status": status.value,
        "payment_status": payment.value if payment else None,
        "reported_total": financials.reported_total,
        "calculated_total": financials.calculated_total,
        "reconciliation_difference": _difference(financials),
        "gross_sales": gross,
        "discount_amount": recognized_discount,
        "recognized_sales": recognized_sale,
        "refund_amount": refund,
        "revenue": net_revenue,
        "pending_value": pending_value,
        "tax_amount": net_tax,
        "tax_refunded": refunded_tax,
        "shipping_amount": recognized_shipping,
        "total_customer_charge": net_revenue + net_tax + recognized_shipping,
        "chargeback_amount": chargeback,
        "disputed_value": disputed_value,
        "net_collected": net_collected,
        "payment_amount": payment_amount,
        "currency": _currency(source, mapping, config),
        "quantity": (
            _mapped_decimal(source, mapping, "quantity", nullable=True)
            if config.revenue_mode is not RevenueMode.ORDER_TOTAL
            else None
        ),
        "returned_quantity": (
            _mapped_decimal(source, mapping, "returned_quantity", nullable=True)
            or (
                _mapped_decimal(source, mapping, "quantity", nullable=True)
                if status is StandardOrderStatus.RETURNED
                else None
            )
        ),
        "product_id": (
            _optional_text(source, mapping, "product_id")
            if config.revenue_mode is not RevenueMode.ORDER_TOTAL
            else None
        ),
        "product_name": (
            _optional_text(source, mapping, "product_name")
            if config.revenue_mode is not RevenueMode.ORDER_TOTAL
            else None
        ),
        "unit_of_measure": (
            _optional_text(source, mapping, "unit_of_measure")
            if config.revenue_mode is not RevenueMode.ORDER_TOTAL
            else None
        ),
        "product_category": (
            _optional_text(source, mapping, "product_category")
            if config.revenue_mode is not RevenueMode.ORDER_TOTAL
            else None
        ),
        "state_or_region": _optional_text(source, mapping, "state_or_region"),
        "category_revenue": category_revenue,
    }
    return {key: value for key, value in row.items() if value is not None or key == "net_collected"}


def _difference(values: LineFinancials):
    if values.reported_total is None or values.calculated_total is None:
        return None
    return values.reported_total - values.calculated_total


def _mapped_decimal(source, mapping, field, nullable=False):
    if field not in mapping:
        return None if nullable else Decimal("0")
    value = parse_decimal(source[mapping[field]])
    return value if value is not None else (None if nullable else Decimal("0"))


def _mapped_date(source, mapping, field, date_format):
    if field not in mapping or not str(source[mapping[field]]).strip():
        return None
    return pd.to_datetime(source[mapping[field]], format=date_format, exact=True)


def _optional_text(source, mapping, field):
    if field not in mapping:
        return None
    raw_value = source[mapping[field]]
    if pd.isna(raw_value):
        return None
    value = _text(raw_value)
    return value or None


def _text(value):
    return value.strip() if isinstance(value, str) else str(value)


def _currency(source, mapping, config):
    return (
        str(source[mapping["currency"]]).strip().upper()
        if "currency" in mapping
        else config.currency
    )
