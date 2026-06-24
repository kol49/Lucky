from __future__ import annotations

from collections.abc import Iterable

from profitmap.db.models import Product


def allocate_fixed_expenses(products: Iterable[Product], total_expenses: float, method: str) -> dict[int, float]:
    product_list = list(products)
    if not product_list:
        return {}

    weights: dict[int, float] = {}
    for product in product_list:
        variable_cost = (
            product.purchase_price
            + product.logistics
            + product.marketplace_fee
            + product.advertising
            + product.packaging
            + product.taxes
            + product.other_costs
        )
        contribution = max(product.sale_price - variable_cost, 0)
        if method == "sales_quantity":
            weights[product.id] = max(product.expected_monthly_sales, 0)
        elif method == "margin":
            weights[product.id] = contribution * max(product.expected_monthly_sales, 0)
        else:
            weights[product.id] = product.sale_price * max(product.expected_monthly_sales, 0)

    total_weight = sum(weights.values()) or len(product_list)
    return {
        product.id: round(total_expenses * (weights.get(product.id, 1) / total_weight), 2)
        for product in product_list
    }
