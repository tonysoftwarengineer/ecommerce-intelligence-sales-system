"""Typed contracts for product-level fulfilled-unit preparation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from types import MappingProxyType


class ProductDemandAvailability(str, Enum):
    READY = "ready"
    LIMITED = "limited"
    UNAVAILABLE = "unavailable"


class ProductIdentitySource(str, Enum):
    PRODUCT_ID = "product_id"
    PRODUCT_NAME = "product_name"


class ProductDateStatus(str, Enum):
    OBSERVED = "observed"
    CONFIRMED_ZERO = "confirmed_zero"
    BUSINESS_CLOSED = "business_closed"
    STOCKOUT_LIMITED = "stockout_limited"
    MISSING_UNKNOWN = "missing_unknown"


class ProductDemandReasonCode(str, Enum):
    ORDER_TOTAL_INELIGIBLE = "order_total_ineligible"
    MISSING_PRODUCT_IDENTITY = "missing_product_identity"
    MISSING_QUANTITY = "missing_quantity"
    INVALID_QUANTITY = "invalid_quantity"
    MISSING_UNIT_OF_MEASURE = "missing_unit_of_measure"
    UNIT_CONFLICT = "unit_conflict"
    PRODUCT_NAME_FALLBACK = "product_name_fallback"
    STOCKOUT_DATA_UNAVAILABLE = "stockout_data_unavailable"
    INCOMPLETE_DAILY_COVERAGE = "incomplete_daily_coverage"


@dataclass(frozen=True)
class ProductDemandAssumptions:
    """Explicit user/business evidence; no value here is silently inferred."""

    default_unit_of_measure: str | None = None
    confirm_product_names_unique: bool = False
    confirm_product_categories: bool = False
    export_covers_all_open_days: bool = False
    stockout_tracking_complete: bool = False
    business_closed_dates: frozenset[date] = field(default_factory=frozenset)
    stockout_dates: Mapping[str, frozenset[date]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.default_unit_of_measure is not None:
            normalized_unit = self.default_unit_of_measure.strip().casefold()
            if not normalized_unit:
                raise ValueError("Default unit of measure must not be blank")
            object.__setattr__(self, "default_unit_of_measure", normalized_unit)

        object.__setattr__(
            self,
            "business_closed_dates",
            frozenset(_normalized_date(value) for value in self.business_closed_dates),
        )
        normalized_stockouts: dict[str, frozenset[date]] = {}
        for raw_key, dates in self.stockout_dates.items():
            key = str(raw_key).strip()
            if not key:
                raise ValueError("Stockout product key must not be blank")
            normalized_stockouts[key] = frozenset(_normalized_date(value) for value in dates)
        object.__setattr__(self, "stockout_dates", MappingProxyType(normalized_stockouts))


def _normalized_date(value: date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValueError("Closure and stockout dates must be date values")


@dataclass(frozen=True)
class ProductDemandProductReadiness:
    product_key: str
    product_id: str | None
    product_name: str | None
    identity_source: ProductIdentitySource
    unit_of_measure: str | None
    status: ProductDemandAvailability
    reason_codes: tuple[ProductDemandReasonCode, ...]
    explanations: tuple[str, ...]


@dataclass(frozen=True)
class ProductDemandReadinessReport:
    status: ProductDemandAvailability
    total_rows: int
    unresolved_rows: int
    products: tuple[ProductDemandProductReadiness, ...]
    reason_codes: tuple[ProductDemandReasonCode, ...]
    explanations: tuple[str, ...]

    @property
    def ready_products(self) -> int:
        return sum(product.status is ProductDemandAvailability.READY for product in self.products)

    @property
    def limited_products(self) -> int:
        return sum(product.status is ProductDemandAvailability.LIMITED for product in self.products)

    @property
    def unavailable_products(self) -> int:
        return sum(
            product.status is ProductDemandAvailability.UNAVAILABLE for product in self.products
        )
