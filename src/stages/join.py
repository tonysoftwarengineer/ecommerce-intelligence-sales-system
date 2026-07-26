import pandas as pd


def _require_unique(df: pd.DataFrame, column: str) -> None:
    if not df[column].is_unique:
        raise ValueError(f"'{column}' must be unique before joining, found duplicates")


def join_all(cleaned: dict[str, pd.DataFrame]) -> pd.DataFrame:
    order_items = cleaned["order_items"]
    orders = cleaned["orders"]
    customers = cleaned["customers"]
    products = cleaned["products"]
    category_translation = cleaned["category_translation"]

    _require_unique(orders, "order_id")
    _require_unique(customers, "customer_id")
    _require_unique(products, "product_id")
    _require_unique(category_translation, "product_category_name")

    df = order_items.merge(orders, on="order_id", how="inner")
    if len(df) > len(order_items):
        raise ValueError(
            "inner join on order_id increased row count — orders.order_id is no "
            "longer unique as expected"
        )

    df = df.merge(customers, on="customer_id", how="left")
    if df["customer_state"].isna().any():
        raise ValueError("some orders did not match a customer after the left join")

    df = df.merge(products, on="product_id", how="left")
    df = df.merge(category_translation, on="product_category_name", how="left")

    return df
