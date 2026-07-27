import pandas as pd

from src.stages.analyze import average_order_value, top_categories_by_revenue, total_revenue


def test_average_order_value_collapses_by_order_before_averaging():
    # order A has 3 line items (10+10+10=30), order B has 1 line item (90)
    # naive mean over all rows would be (10+10+10+90)/4 = 30 -- wrong
    # correct behavior: sum per order first -> [30, 90] -> mean = 60
    df = pd.DataFrame(
        {
            "order_id": ["A", "A", "A", "B"],
            "price": [10.0, 10.0, 10.0, 90.0],
        }
    )
    assert average_order_value(df) == 60.0


def test_total_revenue_sums_price_column():
    df = pd.DataFrame({"price": [10.0, 20.0, 30.0]})
    assert total_revenue(df) == 60.0


def test_top_categories_by_revenue_sorts_descending_and_limits_n():
    df = pd.DataFrame(
        {
            "product_category_name_english": ["a", "b", "c"],
            "price": [10.0, 30.0, 20.0],
        }
    )
    result = top_categories_by_revenue(df, n=2)
    assert list(result.index) == ["b", "c"]
