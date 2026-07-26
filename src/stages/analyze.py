import pandas as pd

REVENUE_COLUMN = "price"


def total_revenue(df: pd.DataFrame) -> float:
    return df[REVENUE_COLUMN].sum()


def revenue_by_month(df: pd.DataFrame) -> pd.Series:
    df = df.copy()
    df["month"] = df["order_purchase_timestamp"].dt.to_period("M")
    return df.groupby("month")[REVENUE_COLUMN].sum().sort_index()


def average_order_value(df: pd.DataFrame) -> float:
    order_totals = df.groupby("order_id")[REVENUE_COLUMN].sum()
    return order_totals.mean()


def top_categories_by_revenue(df: pd.DataFrame, n: int = 10) -> pd.Series:
    return (
        df.groupby("product_category_name_english", dropna=False)[REVENUE_COLUMN]
        .sum()
        .sort_values(ascending=False)
        .head(n)
    )


def top_customers_by_spend(df: pd.DataFrame, n: int = 10) -> pd.Series:
    return (
        df.groupby("customer_unique_id")[REVENUE_COLUMN]
        .sum()
        .sort_values(ascending=False)
        .head(n)
    )


def revenue_by_state(df: pd.DataFrame) -> pd.Series:
    return df.groupby("customer_state")[REVENUE_COLUMN].sum().sort_values(ascending=False)


def run_analysis(df: pd.DataFrame) -> dict:
    return {
        "total_revenue": total_revenue(df),
        "revenue_by_month": revenue_by_month(df),
        "average_order_value": average_order_value(df),
        "top_categories_by_revenue": top_categories_by_revenue(df),
        "top_customers_by_spend": top_customers_by_spend(df),
        "revenue_by_state": revenue_by_state(df),
    }
