import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.ticker import FuncFormatter

from src.pipeline import run_pipeline
from src.stages.report import relabel_state_names, relabel_unknown_category


def _use_plain_currency_axis(ax: Axes) -> None:
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"R${value:,.0f}"))


def chart_revenue_by_month(ax: Axes, revenue_by_month: pd.Series) -> None:
    ax.plot(revenue_by_month.index.astype(str), revenue_by_month.values)
    ax.set_title("Revenue by Month")
    ax.set_ylabel("Revenue (R$)")
    ax.tick_params(axis="x", rotation=90)
    _use_plain_currency_axis(ax)


def chart_top_categories(ax: Axes, top_categories_by_revenue: pd.Series) -> None:
    labeled = relabel_unknown_category(top_categories_by_revenue)
    ax.bar(labeled.index, labeled.values)
    ax.set_title("Top Categories by Revenue")
    ax.set_ylabel("Revenue (R$)")
    ax.tick_params(axis="x", rotation=45)
    _use_plain_currency_axis(ax)


def chart_top_customers(ax: Axes, top_customers_by_spend: pd.Series) -> None:
    ax.bar(range(len(top_customers_by_spend)), top_customers_by_spend.values)
    ax.set_title("Top Customers by Spend")
    ax.set_xlabel("Customer rank")
    ax.set_ylabel("Spend (R$)")
    _use_plain_currency_axis(ax)


def chart_revenue_by_state(ax: Axes, revenue_by_state: pd.Series) -> None:
    labeled = relabel_state_names(revenue_by_state)
    ax.bar(labeled.index, labeled.values)
    ax.set_title("Revenue by State")
    ax.set_ylabel("Revenue (R$)")
    ax.tick_params(axis="x", rotation=90)
    _use_plain_currency_axis(ax)


def generate_dashboard(results: dict) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle("Ecommerce Sales Intelligence Dashboard", fontsize=16)

    chart_revenue_by_month(axes[0, 0], results["revenue_by_month"])
    chart_top_categories(axes[0, 1], results["top_categories_by_revenue"])
    chart_top_customers(axes[1, 0], results["top_customers_by_spend"])
    chart_revenue_by_state(axes[1, 1], results["revenue_by_state"])

    fig.tight_layout()
    plt.show()


if __name__ == "__main__":
    results = run_pipeline()
    generate_dashboard(results)
