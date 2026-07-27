import pandas as pd

from src.stages.clean import CLEAN_FUNCTIONS, clean_all, clean_orders, clean_products


def test_clean_orders_keeps_only_fulfilled_statuses():
    # Canceled/unavailable orders would inflate revenue for sales that never
    # actually happened.
    df = pd.DataFrame(
        {
            "order_status": ["delivered", "shipped", "canceled", "unavailable", "processing"],
            "order_purchase_timestamp": ["2018-01-0%d 10:00:00" % i for i in range(1, 6)],
        }
    )
    result = clean_orders(df)

    assert set(result["order_status"]) == {"delivered", "shipped"}
    assert len(result) == 2


def test_clean_orders_parses_timestamps():
    # Stored as text in the CSV; without conversion there is no .dt accessor
    # and revenue-by-month cannot group.
    df = pd.DataFrame(
        {
            "order_status": ["delivered"],
            "order_purchase_timestamp": ["2018-01-15 10:30:00"],
        }
    )
    result = clean_orders(df)

    assert pd.api.types.is_datetime64_any_dtype(result["order_purchase_timestamp"])


def test_clean_products_fills_missing_category_rather_than_dropping():
    # Dropping these rows would remove their sales from the join, shrinking
    # total revenue -- not just the category breakdown.
    df = pd.DataFrame({"product_category_name": ["toys", None, "auto"]})
    result = clean_products(df)

    assert len(result) == 3
    assert result["product_category_name"].tolist() == ["toys", "unknown", "auto"]


def test_clean_does_not_mutate_the_caller_input():
    df = pd.DataFrame({"product_category_name": [None]})
    clean_products(df)

    assert df["product_category_name"].isna().all()


def test_clean_all_returns_only_the_five_tables_in_scope():
    # ingest() returns 9 tables; only 5 feed any business question. Cleaning
    # the rest would be code with no consumer.
    tables = {
        name: pd.DataFrame({"order_status": [], "order_purchase_timestamp": []})
        if name == "orders"
        else pd.DataFrame({"product_category_name": []})
        for name in CLEAN_FUNCTIONS
    }
    tables["payments"] = pd.DataFrame({"unused": [1]})

    result = clean_all(tables)

    assert set(result) == set(CLEAN_FUNCTIONS)
    assert "payments" not in result
