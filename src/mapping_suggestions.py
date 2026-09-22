"""Deterministic, explainable mapping suggestions for common small-business exports."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from src.generic_sales.contracts import RevenueMode
from src.schema_mapping import MODE_OPTIONAL_FIELDS

ALIASES: dict[str, tuple[str, ...]] = {
    "order_id": ("orderid", "ordernumber", "invoice", "invoiceid", "transactionid"),
    "line_item_id": ("lineitemid", "orderlineid", "orderitemid", "itemid"),
    "order_date": (
        "orderdate",
        "transactiondate",
        "saledate",
        "purchasedate",
        "invoicedate",
        "date",
    ),
    "customer_id": (
        "customerid",
        "customercode",
        "clientid",
        "clientcode",
        "buyerid",
        "customer",
        "client",
    ),
    "revenue": ("netrevenue", "revenue", "ordertotal", "totalamount", "salesamount"),
    "unit_price": ("unitprice", "sellingprice", "saleprice", "itemprice"),
    "quantity": ("quantity", "qty", "units", "unitssold"),
    "discount": ("linediscount", "discountamount", "discountvalue", "discount"),
    "product_id": (
        "productid",
        "productcode",
        "stockcode",
        "skucode",
        "sku",
        "itemcode",
    ),
    "product_name": (
        "productname",
        "itemname",
        "stockdescription",
        "description",
    ),
    "unit_of_measure": ("unitofmeasure", "uom", "quantityunit", "salesunit", "unit"),
    "product_category": (
        "productcategory",
        "merchandisedepartment",
        "category",
        "department",
    ),
    "state_or_region": (
        "stateorregion",
        "salesterritory",
        "territory",
        "state",
        "region",
        "province",
        "city",
    ),
    "order_status": ("orderstatus", "fulfillmentstatus", "status"),
    "payment_status": ("paymentstatus", "transactionstatus", "paymentstate"),
    "payment_amount": ("paymentamount", "amountpaid", "collectedamount"),
    "refund_amount": ("refundamount", "refundedamount"),
    "returned_quantity": ("returnedquantity", "returnquantity", "qtyreturned"),
    "recognition_date": ("revenuerecognitiondate", "recognitiondate", "completeddate", "paiddate"),
    "refund_date": ("refunddate", "returneddate"),
    "tax_amount": ("taxamount", "vatamount", "vat", "tax"),
    "shipping_amount": ("shippingfee", "shippingamount", "deliveryfee", "freightvalue"),
    "chargeback_amount": ("chargebackamount", "disputeamount"),
    "currency": ("currency", "currencycode", "iso4217"),
}

CURRENCY_SUFFIXES = ("ngn", "usd", "gbp", "eur", "cad", "aud", "zar")


def suggest_schema_mapping(columns: Iterable[str], revenue_mode: RevenueMode) -> dict[str, Any]:
    """Return transparent header-based suggestions; never treat them as confirmed mappings."""
    source_columns = [str(column) for column in columns]
    normalized = {column: _normalized_header(column) for column in source_columns}
    price_column = _best_column("unit_price", normalized, set())
    quantity_column = _best_column("quantity", normalized, set())
    has_price_quantity = (
        price_column
        and quantity_column
        and price_column["confidence"] >= 0.9
        and quantity_column["confidence"] >= 0.9
    )
    suggested_mode = RevenueMode.UNIT_PRICE_TIMES_QUANTITY if has_price_quantity else revenue_mode

    fields = [
        *(
            ("order_id", "order_date", "customer_id", "unit_price", "quantity")
            if suggested_mode is RevenueMode.UNIT_PRICE_TIMES_QUANTITY
            else ("order_id", "order_date", "customer_id", "revenue")
        ),
        *MODE_OPTIONAL_FIELDS[suggested_mode],
    ]
    used: set[str] = set()
    mapping: dict[str, str] = {}
    candidates: list[dict[str, Any]] = []
    for field in fields:
        if field == "revenue" and suggested_mode is RevenueMode.UNIT_PRICE_TIMES_QUANTITY:
            # A value named "net revenue" is often an already-derived output.
            # Do not invite a false reconciliation against the chosen calculation.
            continue
        candidate = _best_column(field, normalized, used)
        if candidate is None:
            continue
        mapping[field] = candidate["column"]
        used.add(candidate["column"])
        candidates.append({"field": field, **candidate})

    warnings = ["Suggestions are based on column headers and must be reviewed before analysis."]
    if suggested_mode is RevenueMode.UNIT_PRICE_TIMES_QUANTITY:
        warnings.append(
            "Unit price and quantity were found, so price × quantity is recommended "
            "instead of trusting a derived total."
        )
        reported_total = _best_column("revenue", normalized, set())
        if reported_total is not None:
            warnings.append(
                f"{reported_total['column']} looks like a reported total. It was not "
                "auto-mapped because price × quantity is authoritative; map it as the "
                "optional reported total if you want reconciliation checks."
            )
    if "discount" in mapping and _normalized_header(mapping["discount"]) == "discountvalue":
        warnings.append(
            "The selected discount column may be ambiguous. Confirm its type and scope "
            "before validation."
        )
    return {
        "recommended_revenue_mode": suggested_mode.value,
        "mapping": mapping,
        "candidates": candidates,
        "warnings": warnings,
    }


def _best_column(field: str, normalized: dict[str, str], used: set[str]) -> dict[str, Any] | None:
    scored = [
        (score, column, reason)
        for column, value in normalized.items()
        if column not in used
        for score, reason in [_score_header(field, value)]
        if score > 0
    ]
    if not scored:
        return None
    score, column, reason = max(scored, key=lambda item: (item[0], -len(item[1])))
    return {"column": column, "confidence": score, "reason": reason}


def _score_header(field: str, value: str) -> tuple[float, str]:
    aliases = ALIASES.get(field, ())
    for index, alias in enumerate(aliases):
        preference = 0.01 * index
        if value == alias:
            return 1.0 - preference, "Exact normalized header match."
        if value.endswith(alias) and len(value) > len(alias):
            return 0.94 - preference, "Header ends with a recognized field name."
    if field == "state_or_region" and value.endswith("state"):
        return 0.9, "Header identifies a state field."
    if field == "product_category" and value.endswith("category"):
        return 0.9, "Header identifies a category field."
    if field == "recognition_date" and "recognition" in value and "date" in value:
        return 0.9, "Header identifies a recognition date."
    return 0.0, ""


def _normalized_header(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]", "", value.casefold())
    for suffix in CURRENCY_SUFFIXES:
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            return normalized[: -len(suffix)]
    return normalized
