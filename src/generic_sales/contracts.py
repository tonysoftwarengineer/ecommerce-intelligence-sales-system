import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional


class RevenueMode(str, Enum):
    ROW_TOTAL = "row_total"
    UNIT_PRICE_TIMES_QUANTITY = "unit_price_times_quantity"
    ORDER_TOTAL = "order_total"


class NegativeRevenuePolicy(str, Enum):
    REFUNDS = "refunds"
    INVALID = "invalid"


class StandardOrderStatus(str, Enum):
    COMPLETED = "completed"
    PENDING = "pending"
    CANCELLED = "cancelled"
    RETURNED = "returned"


class StandardPaymentStatus(str, Enum):
    PAID = "paid"
    REFUNDED = "refunded"
    PENDING = "pending"
    FAILED = "failed"
    VOIDED = "voided"
    DISPUTED = "disputed"
    CHARGEBACK_WON = "chargeback_won"
    CHARGEBACK_LOST = "chargeback_lost"


class DiscountType(str, Enum):
    NONE = "none"
    FIXED = "fixed"
    PERCENTAGE = "percentage"


class DiscountScope(str, Enum):
    PER_UNIT = "per_unit"
    PER_LINE = "per_line"
    ENTIRE_ORDER = "entire_order"


class OrderDiscountAllocation(str, Enum):
    UNALLOCATED = "unallocated"
    PROPORTIONAL = "proportional"


class RevenueMismatchPolicy(str, Enum):
    WARN = "warn"
    QUARANTINE = "quarantine"


class DataQualityStatus(str, Enum):
    NORMAL = "normal"
    CAUTION = "caution"
    PREVIEW = "preview"
    BLOCKED = "blocked"


class RefundTaxTreatment(str, Enum):
    """Whether a mapped refund amount already includes refunded tax."""

    EXCLUDES_TAX = "excludes_tax"
    INCLUDES_TAX = "includes_tax"


@dataclass(frozen=True)
class SalesProcessingConfig:
    revenue_mode: RevenueMode
    negative_revenue_policy: NegativeRevenuePolicy
    date_format: str
    currency: str
    status_mapping: Mapping[str, StandardOrderStatus] = field(default_factory=dict)
    payment_status_mapping: Mapping[str, StandardPaymentStatus] = field(default_factory=dict)
    assume_all_completed: bool = False
    discount_type: DiscountType = DiscountType.NONE
    discount_scope: DiscountScope = DiscountScope.PER_LINE
    order_discount_allocation: OrderDiscountAllocation = OrderDiscountAllocation.UNALLOCATED
    revenue_mismatch_policy: RevenueMismatchPolicy = RevenueMismatchPolicy.WARN
    mismatch_tolerance: Decimal = Decimal("0.01")
    refund_tax_treatment: Optional[RefundTaxTreatment] = None

    def __post_init__(self) -> None:
        if not self.date_format.strip():
            raise ValueError("Date format must not be empty")
        try:
            sample = datetime(2000, 11, 22, 13, 14, 15)
            datetime.strptime(sample.strftime(self.date_format), self.date_format)
        except ValueError as exc:
            raise ValueError("Date format contains an invalid directive") from exc
        if re.fullmatch(r"[A-Z]{3}", self.currency) is None:
            raise ValueError("Currency must be a three-letter uppercase code")
        try:
            tolerance = Decimal(str(self.mismatch_tolerance))
        except InvalidOperation as exc:
            raise ValueError("Revenue mismatch tolerance must be numeric") from exc
        if tolerance < 0:
            raise ValueError("Revenue mismatch tolerance must not be negative")
        object.__setattr__(self, "mismatch_tolerance", tolerance)
        if (
            self.discount_type is DiscountType.NONE
            and self.discount_scope is not DiscountScope.PER_LINE
        ):
            raise ValueError("Discount scope is only meaningful when a discount type is selected")
        if (
            self.discount_scope is not DiscountScope.ENTIRE_ORDER
            and self.order_discount_allocation is not OrderDiscountAllocation.UNALLOCATED
        ):
            raise ValueError("Order discount allocation requires entire-order discount scope")
        object.__setattr__(
            self,
            "status_mapping",
            {
                str(source).strip().casefold(): StandardOrderStatus(target)
                for source, target in self.status_mapping.items()
            },
        )
        object.__setattr__(
            self,
            "payment_status_mapping",
            {
                str(source).strip().casefold(): StandardPaymentStatus(target)
                for source, target in self.payment_status_mapping.items()
            },
        )


@dataclass(frozen=True)
class ValidationIssue:
    row_number: int
    field: str
    code: str
    message: str


@dataclass(frozen=True)
class DataValidationResult:
    total_rows: int
    valid_rows: int
    invalid_rows: int
    invalid_row_positions: tuple[int, ...]
    issues: tuple[ValidationIssue, ...]
    warnings: tuple[str, ...]
    blocking_errors: tuple[str, ...]

    @property
    def can_transform(self) -> bool:
        return self.valid_rows > 0 and not self.blocking_errors

    @property
    def requires_confirmation(self) -> bool:
        return self.invalid_rows > 0 and self.can_transform


@dataclass(frozen=True)
class DataCorrectionAction:
    field: str
    source_column: Optional[str]
    issue_code: str
    affected_rows: int
    sample_row_numbers: tuple[int, ...]
    problem: str
    instruction: str


@dataclass(frozen=True)
class DataQualityReport:
    status: DataQualityStatus
    invalid_row_percentage: float
    decision_ready: bool
    preview_only: bool
    restricted_outputs: tuple[str, ...]
    message: str
    correction_actions: tuple[DataCorrectionAction, ...]


BASE_REQUIRED_FIELDS = ("order_id", "order_date", "customer_id")


def required_fields_for_mode(revenue_mode: RevenueMode) -> tuple[str, ...]:
    if revenue_mode is RevenueMode.UNIT_PRICE_TIMES_QUANTITY:
        return BASE_REQUIRED_FIELDS + ("unit_price", "quantity")
    return BASE_REQUIRED_FIELDS + ("revenue",)
