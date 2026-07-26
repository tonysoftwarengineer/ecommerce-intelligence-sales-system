import pandas as pd
import pytest

from src.stages.join import join_all


def _base_cleaned():
    return {
        "orders": pd.DataFrame({"order_id": ["o1"], "customer_id": ["c1"]}),
        "order_items": pd.DataFrame(
            {"order_id": ["o1"], "product_id": ["p1"], "price": [10.0]}
        ),
        "customers": pd.DataFrame(
            {"customer_id": ["c1"], "customer_unique_id": ["u1"], "customer_state": ["SP"]}
        ),
        "products": pd.DataFrame(
            {"product_id": ["p1"], "product_category_name": ["cat1"]}
        ),
        "category_translation": pd.DataFrame(
            {"product_category_name": ["cat1"], "product_category_name_english": ["cat1_en"]}
        ),
    }


def test_join_all_raises_on_duplicate_order_id():
    cleaned = _base_cleaned()
    cleaned["orders"] = pd.DataFrame(
        {"order_id": ["o1", "o1"], "customer_id": ["c1", "c1"]}
    )
    with pytest.raises(ValueError, match="unique"):
        join_all(cleaned)


def test_join_all_raises_when_customer_missing_after_left_join():
    cleaned = _base_cleaned()
    cleaned["orders"] = pd.DataFrame({"order_id": ["o1"], "customer_id": ["c_missing"]})
    with pytest.raises(ValueError, match="did not match a customer"):
        join_all(cleaned)


def test_join_all_succeeds_on_valid_data():
    result = join_all(_base_cleaned())
    assert len(result) == 1
    assert result.iloc[0]["price"] == 10.0
