import pandas as pd

FULFILLED_STATUSES = ["delivered", "shipped"]


def clean_orders(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["order_purchase_timestamp"] = pd.to_datetime(df["order_purchase_timestamp"])
    df = df[df["order_status"].isin(FULFILLED_STATUSES)]
    return df


def clean_order_items(df: pd.DataFrame) -> pd.DataFrame:
    return df.copy()


def clean_customers(df: pd.DataFrame) -> pd.DataFrame:
    return df.copy()


def clean_products(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["product_category_name"] = df["product_category_name"].fillna("unknown")
    return df


def clean_category_translation(df: pd.DataFrame) -> pd.DataFrame:
    return df.copy()


CLEAN_FUNCTIONS = {
    "orders": clean_orders,
    "order_items": clean_order_items,
    "customers": clean_customers,
    "products": clean_products,
    "category_translation": clean_category_translation,
}


def clean_all(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {name: func(tables[name]) for name, func in CLEAN_FUNCTIONS.items()}
