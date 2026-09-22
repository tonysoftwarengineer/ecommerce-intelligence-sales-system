from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.generic_sales.contracts import RevenueMode, required_fields_for_mode

MODE_OPTIONAL_FIELDS = {
    RevenueMode.ROW_TOTAL: (
        "unit_price",
        "quantity",
        "discount",
        "product_id",
        "product_name",
        "unit_of_measure",
        "product_category",
        "state_or_region",
        "order_status",
        "payment_status",
        "payment_amount",
        "refund_amount",
        "returned_quantity",
        "recognition_date",
        "refund_date",
        "tax_amount",
        "shipping_amount",
        "chargeback_amount",
        "currency",
        "line_item_id",
    ),
    RevenueMode.UNIT_PRICE_TIMES_QUANTITY: (
        "revenue",
        "discount",
        "product_id",
        "product_name",
        "unit_of_measure",
        "product_category",
        "state_or_region",
        "order_status",
        "payment_status",
        "payment_amount",
        "refund_amount",
        "returned_quantity",
        "recognition_date",
        "refund_date",
        "tax_amount",
        "shipping_amount",
        "chargeback_amount",
        "currency",
        "line_item_id",
    ),
    RevenueMode.ORDER_TOTAL: (
        "discount",
        "state_or_region",
        "order_status",
        "payment_status",
        "payment_amount",
        "refund_amount",
        "recognition_date",
        "refund_date",
        "tax_amount",
        "shipping_amount",
        "chargeback_amount",
        "currency",
    ),
}


def validate_schema_mapping(
    columns: Sequence[str],
    mapping: Mapping[str, str],
    revenue_mode: RevenueMode = RevenueMode.ROW_TOTAL,
) -> dict[str, Any]:
    """Validate a user's mapping from canonical fields to uploaded CSV columns."""
    available_columns = set(columns)
    mapped_fields = dict(mapping)
    required_fields = required_fields_for_mode(revenue_mode)
    optional_fields = MODE_OPTIONAL_FIELDS[revenue_mode]
    supported_fields = frozenset(required_fields + optional_fields)

    missing_required_fields = [field for field in required_fields if not mapped_fields.get(field)]
    unsupported_fields = sorted(set(mapped_fields) - supported_fields)
    unknown_mapped_columns = sorted(
        {
            source_column
            for source_column in mapped_fields.values()
            if source_column and source_column not in available_columns
        }
    )

    source_column_counts = Counter(
        source_column for source_column in mapped_fields.values() if source_column
    )
    duplicate_mapped_columns = sorted(
        column for column, count in source_column_counts.items() if count > 1
    )
    mapped_supported_columns = {
        source_column
        for field, source_column in mapped_fields.items()
        if field in supported_fields and source_column
    }
    unmapped_columns = [column for column in columns if column not in mapped_supported_columns]

    errors = []
    if missing_required_fields:
        errors.append("Missing required mappings: " + ", ".join(missing_required_fields))
    if unsupported_fields:
        errors.append("Unsupported canonical fields: " + ", ".join(unsupported_fields))
    if unknown_mapped_columns:
        errors.append(
            "Mapped columns not found in the uploaded CSV: " + ", ".join(unknown_mapped_columns)
        )
    if duplicate_mapped_columns:
        errors.append(
            "CSV columns cannot be mapped more than once: " + ", ".join(duplicate_mapped_columns)
        )

    warnings = []
    if unmapped_columns:
        warnings.append(
            "These columns will be excluded from analysis: " + ", ".join(unmapped_columns)
        )

    return {
        "valid": not errors,
        "required_fields": list(required_fields),
        "optional_fields": list(optional_fields),
        "mapped_fields": mapped_fields,
        "missing_required_fields": missing_required_fields,
        "unsupported_fields": unsupported_fields,
        "unknown_mapped_columns": unknown_mapped_columns,
        "duplicate_mapped_columns": duplicate_mapped_columns,
        "unmapped_columns": unmapped_columns,
        "errors": errors,
        "warnings": warnings,
    }
