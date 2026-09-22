"""Deterministic per-product readiness without forecasting or silent repair."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import pandas as pd

from src.generic_sales.contracts import RevenueMode
from src.product_demand.contracts import (
    ProductDemandAssumptions,
    ProductDemandAvailability,
    ProductDemandProductReadiness,
    ProductDemandReadinessReport,
    ProductDemandReasonCode,
    ProductIdentitySource,
)

REASON_EXPLANATIONS: dict[ProductDemandReasonCode, str] = {
    ProductDemandReasonCode.ORDER_TOTAL_INELIGIBLE: (
        "Product forecasting needs line-item product identity and quantity; order-total "
        "mode intentionally keeps only one row per order."
    ),
    ProductDemandReasonCode.MISSING_PRODUCT_IDENTITY: (
        "A stable Product/SKU code is missing, and no confirmed unique product-name "
        "fallback is available."
    ),
    ProductDemandReasonCode.MISSING_QUANTITY: (
        "A usable line-item quantity is required for fulfilled-unit preparation."
    ),
    ProductDemandReasonCode.INVALID_QUANTITY: (
        "One or more quantities cannot be interpreted safely for the confirmed order status."
    ),
    ProductDemandReasonCode.MISSING_UNIT_OF_MEASURE: (
        "Map a unit of measure or confirm one dataset-level default before quantities are added."
    ),
    ProductDemandReasonCode.UNIT_CONFLICT: (
        "This product uses incompatible units without an explicit conversion rule."
    ),
    ProductDemandReasonCode.PRODUCT_NAME_FALLBACK: (
        "The product name is being used as a confirmed but lower-confidence identity fallback."
    ),
    ProductDemandReasonCode.STOCKOUT_DATA_UNAVAILABLE: (
        "Stockout tracking is incomplete, so fulfilled sales may understate customer interest."
    ),
    ProductDemandReasonCode.INCOMPLETE_DAILY_COVERAGE: (
        "The export is not confirmed complete for every open day, so absent rows remain unknown."
    ),
}


def assess_product_demand_readiness(
    canonical_data: pd.DataFrame,
    revenue_mode: RevenueMode,
    assumptions: ProductDemandAssumptions,
) -> ProductDemandReadinessReport:
    """Assess the smallest safe product scope without choosing a forecast model."""
    if revenue_mode is RevenueMode.ORDER_TOTAL:
        return _global_unavailable(
            len(canonical_data),
            ProductDemandReasonCode.ORDER_TOTAL_INELIGIBLE,
        )
    if "quantity" not in canonical_data.columns:
        return _global_unavailable(
            len(canonical_data),
            ProductDemandReasonCode.MISSING_QUANTITY,
        )

    resolved = resolve_product_rows(canonical_data, assumptions)
    unresolved_rows = int(resolved["_product_key"].isna().sum())
    products: list[ProductDemandProductReadiness] = []

    for product_key, rows in resolved.dropna(subset=["_product_key"]).groupby(
        "_product_key", sort=True
    ):
        key = str(product_key)
        identity_source = ProductIdentitySource(str(rows["_identity_source"].iloc[0]))
        reasons: list[ProductDemandReasonCode] = []
        units = {str(value) for value in rows["_normalized_unit"] if value is not None}
        if rows["_normalized_unit"].isna().any():
            reasons.append(ProductDemandReasonCode.MISSING_UNIT_OF_MEASURE)
        elif len(units) > 1:
            reasons.append(ProductDemandReasonCode.UNIT_CONFLICT)

        quantity_reason = _quantity_reason(rows)
        if quantity_reason is not None:
            reasons.append(quantity_reason)
        if identity_source is ProductIdentitySource.PRODUCT_NAME:
            reasons.append(ProductDemandReasonCode.PRODUCT_NAME_FALLBACK)
        if not assumptions.stockout_tracking_complete:
            reasons.append(ProductDemandReasonCode.STOCKOUT_DATA_UNAVAILABLE)
        if not assumptions.export_covers_all_open_days:
            reasons.append(ProductDemandReasonCode.INCOMPLETE_DAILY_COVERAGE)

        blocking = {
            ProductDemandReasonCode.MISSING_QUANTITY,
            ProductDemandReasonCode.INVALID_QUANTITY,
            ProductDemandReasonCode.MISSING_UNIT_OF_MEASURE,
            ProductDemandReasonCode.UNIT_CONFLICT,
        }
        status = (
            ProductDemandAvailability.UNAVAILABLE
            if any(reason in blocking for reason in reasons)
            else ProductDemandAvailability.LIMITED
            if reasons
            else ProductDemandAvailability.READY
        )
        product_id = _first_text(rows.get("product_id"))
        product_name = _first_text(rows.get("product_name"))
        products.append(
            ProductDemandProductReadiness(
                product_key=key,
                product_id=product_id,
                product_name=product_name,
                identity_source=identity_source,
                unit_of_measure=next(iter(units)) if len(units) == 1 else None,
                status=status,
                reason_codes=tuple(dict.fromkeys(reasons)),
                explanations=tuple(
                    REASON_EXPLANATIONS[reason] for reason in dict.fromkeys(reasons)
                ),
            )
        )

    dataset_reasons: list[ProductDemandReasonCode] = []
    if unresolved_rows:
        dataset_reasons.append(ProductDemandReasonCode.MISSING_PRODUCT_IDENTITY)
    status = _dataset_status(products, unresolved_rows)
    return ProductDemandReadinessReport(
        status=status,
        total_rows=len(canonical_data),
        unresolved_rows=unresolved_rows,
        products=tuple(products),
        reason_codes=tuple(dataset_reasons),
        explanations=tuple(REASON_EXPLANATIONS[reason] for reason in dataset_reasons),
    )


def resolve_product_rows(
    canonical_data: pd.DataFrame,
    assumptions: ProductDemandAssumptions,
) -> pd.DataFrame:
    resolved = canonical_data.copy(deep=True)
    keys: list[str | None] = []
    sources: list[str | None] = []
    units: list[str | None] = []
    for _, row in resolved.iterrows():
        product_id = _text(row.get("product_id"))
        product_name = _text(row.get("product_name"))
        if product_id:
            keys.append(f"id:{product_id}")
            sources.append(ProductIdentitySource.PRODUCT_ID.value)
        elif product_name and assumptions.confirm_product_names_unique:
            keys.append(f"name:{product_name}")
            sources.append(ProductIdentitySource.PRODUCT_NAME.value)
        else:
            keys.append(None)
            sources.append(None)

        unit = _text(row.get("unit_of_measure"))
        units.append(unit.casefold() if unit else assumptions.default_unit_of_measure)
    resolved["_product_key"] = keys
    resolved["_identity_source"] = sources
    resolved["_normalized_unit"] = units
    return resolved


def _quantity_reason(rows: pd.DataFrame) -> ProductDemandReasonCode | None:
    for _, row in rows.iterrows():
        quantity = _decimal(row.get("quantity"))
        if quantity is None:
            return ProductDemandReasonCode.MISSING_QUANTITY
        status = str(row.get("order_status", "completed")).strip().casefold()
        if quantity == 0 or (quantity < 0 and status not in {"cancelled", "returned"}):
            return ProductDemandReasonCode.INVALID_QUANTITY
    return None


def _dataset_status(
    products: list[ProductDemandProductReadiness],
    unresolved_rows: int,
) -> ProductDemandAvailability:
    usable = [
        product
        for product in products
        if product.status is not ProductDemandAvailability.UNAVAILABLE
    ]
    if not usable:
        return ProductDemandAvailability.UNAVAILABLE
    if unresolved_rows or any(
        product.status is not ProductDemandAvailability.READY for product in products
    ):
        return ProductDemandAvailability.LIMITED
    return ProductDemandAvailability.READY


def _global_unavailable(
    total_rows: int,
    reason: ProductDemandReasonCode,
) -> ProductDemandReadinessReport:
    return ProductDemandReadinessReport(
        status=ProductDemandAvailability.UNAVAILABLE,
        total_rows=total_rows,
        unresolved_rows=0,
        products=(),
        reason_codes=(reason,),
        explanations=(REASON_EXPLANATIONS[reason],),
    )


def _first_text(series: pd.Series | None) -> str | None:
    if series is None:
        return None
    return next((text for value in series for text in [_text(value)] if text), None)


def _text(value: object) -> str | None:
    if value is None or bool(pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _decimal(value: object) -> Decimal | None:
    if value is None or bool(pd.isna(value)):
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
