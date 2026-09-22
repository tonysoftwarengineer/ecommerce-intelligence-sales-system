import pytest

from src.generic_sales.contracts import (
    NegativeRevenuePolicy,
    RevenueMode,
    SalesProcessingConfig,
)


def test_processing_config_rejects_invalid_date_directive() -> None:
    with pytest.raises(ValueError, match="invalid directive"):
        SalesProcessingConfig(
            revenue_mode=RevenueMode.ROW_TOTAL,
            negative_revenue_policy=NegativeRevenuePolicy.INVALID,
            date_format="%Q",
            currency="USD",
        )


def test_processing_config_requires_uppercase_three_letter_currency() -> None:
    with pytest.raises(ValueError, match="three-letter uppercase"):
        SalesProcessingConfig(
            revenue_mode=RevenueMode.ROW_TOTAL,
            negative_revenue_policy=NegativeRevenuePolicy.INVALID,
            date_format="%Y-%m-%d",
            currency="usd",
        )
