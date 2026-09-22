from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from src.generic_sales.contracts import DiscountScope, DiscountType


@dataclass(frozen=True)
class LineFinancials:
    unit_price: Optional[Decimal]
    quantity: Optional[Decimal]
    subtotal: Optional[Decimal]
    discount_input: Decimal
    discount: Decimal
    calculated_total: Optional[Decimal]
    reported_total: Optional[Decimal]


def parse_decimal(value: object) -> Optional[Decimal]:
    """Parse a CSV value without passing through binary floating point."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        result = Decimal(text)
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def calculate_line_financials(
    unit_price_value: object,
    quantity_value: object,
    discount_value: object,
    reported_total_value: object,
    discount_type: DiscountType,
    discount_scope: DiscountScope,
) -> LineFinancials:
    unit_price = parse_decimal(unit_price_value)
    quantity = parse_decimal(quantity_value)
    reported_total = parse_decimal(reported_total_value)
    discount_input = parse_decimal(discount_value) or Decimal("0")

    subtotal = None
    calculated_total = None
    discount = Decimal("0")
    if unit_price is not None and quantity is not None:
        subtotal = unit_price * quantity
        if discount_type is DiscountType.FIXED:
            if discount_scope is DiscountScope.PER_UNIT:
                discount = discount_input * quantity
            else:
                discount = discount_input
        elif discount_type is DiscountType.PERCENTAGE:
            discount = subtotal * discount_input / Decimal("100")

        if discount_scope is not DiscountScope.ENTIRE_ORDER:
            calculated_total = subtotal - discount

    return LineFinancials(
        unit_price=unit_price,
        quantity=quantity,
        subtotal=subtotal,
        discount_input=discount_input,
        discount=discount,
        calculated_total=calculated_total,
        reported_total=reported_total,
    )


def normalized_mapping_value(value: object) -> str:
    return str(value).strip().casefold()
