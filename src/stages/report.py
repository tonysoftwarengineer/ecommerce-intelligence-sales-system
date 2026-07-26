import pandas as pd

BRAZIL_STATE_NAMES = {
    "SP": "São Paulo",
    "RJ": "Rio de Janeiro",
    "MG": "Minas Gerais",
    "RS": "Rio Grande do Sul",
    "PR": "Paraná",
    "SC": "Santa Catarina",
    "BA": "Bahia",
    "DF": "Distrito Federal",
    "GO": "Goiás",
    "ES": "Espírito Santo",
    "PE": "Pernambuco",
    "CE": "Ceará",
    "PA": "Pará",
    "MT": "Mato Grosso",
    "MA": "Maranhão",
    "MS": "Mato Grosso do Sul",
    "PB": "Paraíba",
    "PI": "Piauí",
    "RN": "Rio Grande do Norte",
    "AL": "Alagoas",
    "SE": "Sergipe",
    "TO": "Tocantins",
    "RO": "Rondônia",
    "AM": "Amazonas",
    "AC": "Acre",
    "AP": "Amapá",
    "RR": "Roraima",
}


def format_currency(value: float) -> str:
    return f"R${value:,.2f}"


def relabel_unknown_category(series: pd.Series) -> pd.Series:
    result = series.copy()
    result.index = result.index.fillna("Unknown")
    return result


def relabel_state_names(series: pd.Series) -> pd.Series:
    return series.rename(index=BRAZIL_STATE_NAMES)


def generate_report(results: dict) -> None:
    print("=" * 50)
    print("ECOMMERCE SALES INTELLIGENCE REPORT")
    print("=" * 50)

    print(f"\nTotal Revenue: {format_currency(results['total_revenue'])}")
    print(f"Average Order Value: {format_currency(results['average_order_value'])}")

    print("\nRevenue by Month:")
    for month, revenue in results["revenue_by_month"].items():
        print(f"  {month}: {format_currency(revenue)}")

    print("\nTop Categories by Revenue:")
    top_categories = relabel_unknown_category(results["top_categories_by_revenue"])
    for category, revenue in top_categories.items():
        print(f"  {category}: {format_currency(revenue)}")

    print("\nTop Customers by Spend:")
    for customer_id, revenue in results["top_customers_by_spend"].items():
        print(f"  {customer_id}: {format_currency(revenue)}")

    print("\nRevenue by State:")
    revenue_by_state = relabel_state_names(results["revenue_by_state"])
    for state, revenue in revenue_by_state.items():
        print(f"  {state}: {format_currency(revenue)}")
