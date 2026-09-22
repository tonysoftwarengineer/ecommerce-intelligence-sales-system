"""Prepare safe category-level fallback series from validated product calendars."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

import pandas as pd

from src.product_demand.contracts import (
    ProductDateStatus,
    ProductDemandAssumptions,
    ProductDemandAvailability,
    ProductDemandReadinessReport,
)
from src.product_demand.evaluation_contracts import EvaluationSeries, EvaluationSeriesPoint
from src.product_demand.readiness import resolve_product_rows


class CategoryFallbackAvailability(str, Enum):
    READY = "ready"
    UNAVAILABLE = "unavailable"


class CategoryFallbackReasonCode(str, Enum):
    CATEGORY_CONFIRMATION_REQUIRED = "category_confirmation_required"
    MISSING_PRODUCT_CATEGORY = "missing_product_category"
    UNCATEGORIZED_PRODUCTS = "uncategorized_products"
    INCOMPLETE_PRODUCT_CATEGORY = "incomplete_product_category"
    UNRESOLVED_PRODUCT_IDENTITY = "unresolved_product_identity"
    INCONSISTENT_PRODUCT_CATEGORY = "inconsistent_product_category"
    INSUFFICIENT_DISTINCT_PRODUCTS = "insufficient_distinct_products"
    UNSAFE_PRODUCT_SEMANTICS = "unsafe_product_semantics"
    INCOMPATIBLE_UNITS = "incompatible_units"


REASON_EXPLANATIONS: dict[CategoryFallbackReasonCode, str] = {
    CategoryFallbackReasonCode.CATEGORY_CONFIRMATION_REQUIRED: (
        "Confirm that the mapped product categories are correct before category fallback is "
        "evaluated."
    ),
    CategoryFallbackReasonCode.MISSING_PRODUCT_CATEGORY: (
        "Map a product-category column to make category fallback available."
    ),
    CategoryFallbackReasonCode.UNCATEGORIZED_PRODUCTS: (
        "Some resolved products have no category and are excluded from category fallback."
    ),
    CategoryFallbackReasonCode.INCOMPLETE_PRODUCT_CATEGORY: (
        "At least one product has a category on some rows but not others. Complete the category "
        "assignment for that product before combining demand."
    ),
    CategoryFallbackReasonCode.UNRESOLVED_PRODUCT_IDENTITY: (
        "This category contains rows without a resolved product identity. Add stable product "
        "codes or confirm the product-name fallback."
    ),
    CategoryFallbackReasonCode.INCONSISTENT_PRODUCT_CATEGORY: (
        "At least one product belongs to more than one category. Correct or confirm a single "
        "category for each product."
    ),
    CategoryFallbackReasonCode.INSUFFICIENT_DISTINCT_PRODUCTS: (
        "Category fallback requires at least two distinct products; a one-product category does "
        "not add safer aggregate evidence."
    ),
    CategoryFallbackReasonCode.UNSAFE_PRODUCT_SEMANTICS: (
        "At least one category member has unsafe quantity, identity, or calendar semantics. "
        "Correct the product-level issue before combining the category."
    ),
    CategoryFallbackReasonCode.INCOMPATIBLE_UNITS: (
        "Category members use incompatible units. Confirm one compatible unit or provide an "
        "explicit conversion before quantities are added."
    ),
}


@dataclass(frozen=True)
class CategoryFallbackCandidate:
    category_key: str
    category_name: str
    product_keys: tuple[str, ...]
    unit_of_measure: str | None
    availability: CategoryFallbackAvailability
    reason_codes: tuple[CategoryFallbackReasonCode, ...]
    explanations: tuple[str, ...]
    series: EvaluationSeries | None = None

    def __post_init__(self) -> None:
        if not self.category_key.strip() or not self.category_name.strip():
            raise ValueError("Category fallback candidates require a category identity")
        if tuple(sorted(set(self.product_keys))) != self.product_keys:
            raise ValueError("Category product keys must be unique and sorted")
        if self.availability is CategoryFallbackAvailability.READY:
            if self.series is None or self.reason_codes or self.unit_of_measure is None:
                raise ValueError("Ready category candidates require a safe evaluation series")
        elif self.series is not None or not self.reason_codes:
            raise ValueError("Unavailable category candidates require reasons and no series")


@dataclass(frozen=True)
class CategoryFallbackPreparation:
    candidates: tuple[CategoryFallbackCandidate, ...]
    dataset_reason_codes: tuple[CategoryFallbackReasonCode, ...]
    dataset_explanations: tuple[str, ...]


def prepare_category_fallback_candidates(
    canonical_data: pd.DataFrame,
    product_calendar: pd.DataFrame,
    readiness: ProductDemandReadinessReport,
    eligible_product_keys: frozenset[str],
    assumptions: ProductDemandAssumptions,
) -> CategoryFallbackPreparation:
    """Build fallback-only category series without allocating totals to products."""
    if "product_category" not in canonical_data.columns:
        return _dataset_unavailable(CategoryFallbackReasonCode.MISSING_PRODUCT_CATEGORY)
    if not assumptions.confirm_product_categories:
        return _dataset_unavailable(CategoryFallbackReasonCode.CATEGORY_CONFIRMATION_REQUIRED)

    resolved = resolve_product_rows(canonical_data, assumptions)
    resolved["_category_name"] = resolved["product_category"].map(_category_text)
    resolved["_category_key"] = resolved["_category_name"].map(
        lambda value: value.casefold() if value is not None else None
    )
    categorized = resolved.dropna(subset=["_category_key"])
    if categorized.empty:
        return _dataset_unavailable(CategoryFallbackReasonCode.MISSING_PRODUCT_CATEGORY)

    display_names = {
        str(category_key): sorted(
            {str(value) for value in rows["_category_name"]},
            key=lambda value: (value.casefold(), value),
        )[0]
        for category_key, rows in categorized.groupby("_category_key", sort=True)
    }
    product_categories: dict[str, frozenset[str]] = {
        str(product_key): frozenset(str(value) for value in rows["_category_key"])
        for product_key, rows in categorized.dropna(subset=["_product_key"]).groupby(
            "_product_key", sort=True
        )
    }
    category_products: dict[str, set[str]] = {}
    for product_key, category_keys in product_categories.items():
        for category_key in category_keys:
            category_products.setdefault(category_key, set()).add(product_key)

    unresolved_categories = {
        str(value) for value in categorized.loc[categorized["_product_key"].isna(), "_category_key"]
    }
    conflicted_categories = {
        category_key
        for category_keys in product_categories.values()
        if len(category_keys) > 1
        for category_key in category_keys
    }
    incompletely_categorized_product_keys = {
        str(product_key)
        for product_key, rows in resolved.dropna(subset=["_product_key"]).groupby(
            "_product_key", sort=True
        )
        if rows["_category_key"].isna().any() and rows["_category_key"].notna().any()
    }
    readiness_by_key = {product.product_key: product for product in readiness.products}
    candidates: list[CategoryFallbackCandidate] = []

    for category_key in sorted(category_products):
        product_keys = tuple(sorted(category_products[category_key]))
        if any(product_key in eligible_product_keys for product_key in product_keys):
            # Version one is fallback-only. Do not show unreconciled product and category numbers.
            continue

        reasons: list[CategoryFallbackReasonCode] = []
        if category_key in unresolved_categories:
            reasons.append(CategoryFallbackReasonCode.UNRESOLVED_PRODUCT_IDENTITY)
        if category_key in conflicted_categories:
            reasons.append(CategoryFallbackReasonCode.INCONSISTENT_PRODUCT_CATEGORY)
        if any(
            product_key in incompletely_categorized_product_keys for product_key in product_keys
        ):
            reasons.append(CategoryFallbackReasonCode.INCOMPLETE_PRODUCT_CATEGORY)
        if len(product_keys) < 2:
            reasons.append(CategoryFallbackReasonCode.INSUFFICIENT_DISTINCT_PRODUCTS)

        members = [readiness_by_key.get(product_key) for product_key in product_keys]
        if any(
            member is None or member.status is ProductDemandAvailability.UNAVAILABLE
            for member in members
        ):
            reasons.append(CategoryFallbackReasonCode.UNSAFE_PRODUCT_SEMANTICS)
        units = {
            member.unit_of_measure
            for member in members
            if member is not None and member.unit_of_measure is not None
        }
        if len(units) != 1 or any(
            member is None or member.unit_of_measure is None for member in members
        ):
            reasons.append(CategoryFallbackReasonCode.INCOMPATIBLE_UNITS)

        unique_reasons = tuple(dict.fromkeys(reasons))
        category_name = display_names[category_key]
        if unique_reasons:
            candidates.append(
                CategoryFallbackCandidate(
                    category_key=f"category:{category_key}",
                    category_name=category_name,
                    product_keys=product_keys,
                    unit_of_measure=next(iter(units)) if len(units) == 1 else None,
                    availability=CategoryFallbackAvailability.UNAVAILABLE,
                    reason_codes=unique_reasons,
                    explanations=tuple(REASON_EXPLANATIONS[reason] for reason in unique_reasons),
                )
            )
            continue

        unit = next(iter(units))
        series = _build_category_series(
            product_calendar,
            category_key=f"category:{category_key}",
            product_keys=frozenset(product_keys),
            unit_of_measure=unit,
            assumptions=assumptions,
        )
        if series is None:
            reason = CategoryFallbackReasonCode.UNSAFE_PRODUCT_SEMANTICS
            candidates.append(
                CategoryFallbackCandidate(
                    category_key=f"category:{category_key}",
                    category_name=category_name,
                    product_keys=product_keys,
                    unit_of_measure=unit,
                    availability=CategoryFallbackAvailability.UNAVAILABLE,
                    reason_codes=(reason,),
                    explanations=(REASON_EXPLANATIONS[reason],),
                )
            )
            continue
        candidates.append(
            CategoryFallbackCandidate(
                category_key=f"category:{category_key}",
                category_name=category_name,
                product_keys=product_keys,
                unit_of_measure=unit,
                availability=CategoryFallbackAvailability.READY,
                reason_codes=(),
                explanations=(),
                series=series,
            )
        )

    dataset_reasons: list[CategoryFallbackReasonCode] = []
    categorized_product_keys = set(product_categories)
    resolved_product_keys = {
        str(value) for value in resolved["_product_key"].dropna().unique().tolist()
    }
    if resolved_product_keys - categorized_product_keys:
        dataset_reasons.append(CategoryFallbackReasonCode.UNCATEGORIZED_PRODUCTS)
    return CategoryFallbackPreparation(
        candidates=tuple(candidates),
        dataset_reason_codes=tuple(dataset_reasons),
        dataset_explanations=tuple(REASON_EXPLANATIONS[reason] for reason in dataset_reasons),
    )


def _build_category_series(
    product_calendar: pd.DataFrame,
    *,
    category_key: str,
    product_keys: frozenset[str],
    unit_of_measure: str,
    assumptions: ProductDemandAssumptions,
) -> EvaluationSeries | None:
    rows = product_calendar.loc[product_calendar["product_key"].isin(product_keys)].copy()
    if rows.empty:
        return None
    rows["_date"] = pd.to_datetime(rows["date"], errors="coerce").dt.normalize()
    rows = rows.dropna(subset=["_date"])
    if rows.empty:
        return None

    first_date = rows["_date"].min()
    last_date = rows["_date"].max()
    points: list[EvaluationSeriesPoint] = []
    for timestamp in pd.date_range(first_date, last_date, freq="D"):
        day_rows = rows.loc[rows["_date"] == timestamp]
        day = timestamp.date()
        if day in assumptions.business_closed_dates:
            status = ProductDateStatus.BUSINESS_CLOSED
            target = None
        elif day_rows.empty:
            status = ProductDateStatus.MISSING_UNKNOWN
            target = None
        else:
            statuses = {ProductDateStatus(str(value)) for value in day_rows["status"]}
            if ProductDateStatus.MISSING_UNKNOWN in statuses:
                status = ProductDateStatus.MISSING_UNKNOWN
                target = None
            elif ProductDateStatus.STOCKOUT_LIMITED in statuses:
                status = ProductDateStatus.STOCKOUT_LIMITED
                target = None
            elif statuses == {ProductDateStatus.BUSINESS_CLOSED}:
                status = ProductDateStatus.BUSINESS_CLOSED
                target = None
            else:
                status = (
                    ProductDateStatus.OBSERVED
                    if ProductDateStatus.OBSERVED in statuses
                    else ProductDateStatus.CONFIRMED_ZERO
                )
                target = sum(
                    (
                        Decimal(str(value))
                        for value in day_rows["fulfilled_units"]
                        if value is not None
                    ),
                    Decimal("0"),
                )
        points.append(
            EvaluationSeriesPoint(
                date=day,
                status=status,
                target_units=target,
                included=status in {ProductDateStatus.OBSERVED, ProductDateStatus.CONFIRMED_ZERO},
            )
        )
    return EvaluationSeries(
        product_key=category_key,
        unit_of_measure=unit_of_measure,
        points=tuple(points),
    )


def _category_text(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _dataset_unavailable(reason: CategoryFallbackReasonCode) -> CategoryFallbackPreparation:
    return CategoryFallbackPreparation(
        candidates=(),
        dataset_reason_codes=(reason,),
        dataset_explanations=(REASON_EXPLANATIONS[reason],),
    )
