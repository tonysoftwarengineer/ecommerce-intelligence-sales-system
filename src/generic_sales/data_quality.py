"""Deterministic data-quality readiness and CSV repair guidance."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

from src.generic_sales.contracts import (
    DataCorrectionAction,
    DataQualityReport,
    DataQualityStatus,
    DataValidationResult,
    ValidationIssue,
)

CAUTION_INVALID_PERCENTAGE = 5.0
PREVIEW_INVALID_PERCENTAGE = 20.0
RESTRICTED_DECISION_OUTPUTS = ("forecast", "diagnostics", "recommendations")
SAMPLE_REPAIR_ROWS = 5


def assess_data_quality(
    validation: DataValidationResult,
    mapping: Mapping[str, str],
    date_format: str,
) -> DataQualityReport:
    """Turn validation evidence into one backend-owned readiness decision."""
    invalid_percentage = _invalid_percentage(validation)
    status = _status(validation, invalid_percentage)
    decision_ready = status in {DataQualityStatus.NORMAL, DataQualityStatus.CAUTION}
    preview_only = status is DataQualityStatus.PREVIEW
    return DataQualityReport(
        status=status,
        invalid_row_percentage=invalid_percentage,
        decision_ready=decision_ready,
        preview_only=preview_only,
        restricted_outputs=RESTRICTED_DECISION_OUTPUTS if not decision_ready else (),
        message=_status_message(validation, status, invalid_percentage),
        correction_actions=_correction_actions(validation.issues, mapping, date_format),
    )


def data_quality_report_to_dict(report: DataQualityReport) -> dict:
    """Serialize the domain contract explicitly so API fields remain stable."""
    return {
        "status": report.status.value,
        "invalid_row_percentage": report.invalid_row_percentage,
        "decision_ready": report.decision_ready,
        "preview_only": report.preview_only,
        "restricted_outputs": list(report.restricted_outputs),
        "message": report.message,
        "correction_actions": [
            {
                "field": action.field,
                "source_column": action.source_column,
                "issue_code": action.issue_code,
                "affected_rows": action.affected_rows,
                "sample_row_numbers": list(action.sample_row_numbers),
                "problem": action.problem,
                "instruction": action.instruction,
            }
            for action in report.correction_actions
        ],
    }


def _invalid_percentage(validation: DataValidationResult) -> float:
    if validation.total_rows == 0:
        return 0.0
    return round(validation.invalid_rows / validation.total_rows * 100, 1)


def _status(validation: DataValidationResult, invalid_percentage: float) -> DataQualityStatus:
    if not validation.can_transform:
        return DataQualityStatus.BLOCKED
    if invalid_percentage >= PREVIEW_INVALID_PERCENTAGE:
        return DataQualityStatus.PREVIEW
    if invalid_percentage >= CAUTION_INVALID_PERCENTAGE:
        return DataQualityStatus.CAUTION
    return DataQualityStatus.NORMAL


def _status_message(
    validation: DataValidationResult,
    status: DataQualityStatus,
    invalid_percentage: float,
) -> str:
    if status is DataQualityStatus.BLOCKED:
        return (
            validation.blocking_errors[0]
            if validation.blocking_errors
            else "Analysis is blocked because no trustworthy rows remain."
        )
    if validation.invalid_rows == 0:
        return "Every source row passed validation."
    excluded = (
        f"{invalid_percentage:.1f}% of source rows ({validation.invalid_rows} of "
        f"{validation.total_rows}) will be excluded."
    )
    if status is DataQualityStatus.PREVIEW:
        return (
            f"{excluded} This analysis is available for preview only and may not represent "
            "the full business. Correct the CSV before using it for decisions."
        )
    if status is DataQualityStatus.CAUTION:
        return (
            f"{excluded} The analysis can continue, but review and correct the rejected rows "
            "before relying on important decisions."
        )
    return f"{excluded} The remaining data is decision-ready, with a minor quality note."


def _correction_actions(
    issues: tuple[ValidationIssue, ...],
    mapping: Mapping[str, str],
    date_format: str,
) -> tuple[DataCorrectionAction, ...]:
    grouped: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for issue in issues:
        grouped[(issue.field, issue.code, issue.message)].append(issue.row_number)

    actions = [
        DataCorrectionAction(
            field=field,
            source_column=mapping.get(field),
            issue_code=code,
            affected_rows=len(set(row_numbers)),
            sample_row_numbers=tuple(sorted(set(row_numbers))[:SAMPLE_REPAIR_ROWS]),
            problem=message,
            instruction=_repair_instruction(code, field, date_format),
        )
        for (field, code, message), row_numbers in grouped.items()
    ]
    return tuple(
        sorted(
            actions,
            key=lambda action: (-action.affected_rows, action.field, action.issue_code),
        )
    )


def _repair_instruction(code: str, field: str, date_format: str) -> str:
    field_label = field.replace("_", " ").title()
    instructions = {
        "missing_required_value": f"Fill every blank {field_label} value, then revalidate.",
        "invalid_date": (
            f"Use real dates that consistently match the confirmed format {date_format}."
        ),
        "invalid_number": (
            f"Replace non-numeric {field_label} values with valid numbers without text labels."
        ),
        "exact_duplicate": "Remove duplicate rows or keep only the authoritative copy.",
        "negative_revenue": (
            "Correct negative sales values or choose the refund policy when they represent refunds."
        ),
        "negative_quantity": "Correct negative quantities or map returned quantity separately.",
        "zero_quantity": "Replace zero quantities with the actual sold quantity.",
        "invalid_discount": "Use a valid non-negative discount in the confirmed representation.",
        "discount_exceeds_subtotal": (
            "Correct the discount so it does not exceed the corresponding sale subtotal."
        ),
        "revenue_mismatch": (
            "Correct the reported total or the price, quantity, and discount inputs "
            "so they reconcile."
        ),
        "missing_status": (
            "Fill the blank status value and confirm how it maps to a standard status."
        ),
        "unknown_status": (
            "Correct the status value or add it to the confirmed order-status mapping."
        ),
        "missing_payment_status": (
            "Fill the blank payment status and confirm its standard payment-status mapping."
        ),
        "unknown_payment_status": (
            "Correct the payment status or add it to the confirmed payment-status mapping."
        ),
        "invalid_currency": "Use a consistent three-letter currency code such as USD, NGN, or GBP.",
        "order_conflict": (
            "Make the customer, date, location, and order-level values consistent "
            "for this order ID."
        ),
        "order_payment_conflict": (
            "Make the payment facts consistent across every row belonging to this order."
        ),
        "negative_adjustment": f"Replace negative {field_label} values with non-negative amounts.",
        "return_exceeds_quantity": (
            "Correct returned quantity so it does not exceed the quantity originally sold."
        ),
        "partial_return_requires_refund_amount": (
            "Add the refund amount for the partial return or correct the return classification."
        ),
        "refund_signal_conflict": (
            "Reconcile refund amount, returned quantity, order status, and payment status."
        ),
    }
    return instructions.get(code, "Correct the flagged source values, then revalidate the CSV.")
