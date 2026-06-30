from __future__ import annotations

from dataclasses import dataclass

from profitmap.db.models import Product, SaleRecord


@dataclass(slots=True)
class SalesSummary:
    total_quantity: int
    total_revenue: float
    average_sale_price: float
    discount_percent: float


def calculate_sales_summary(product: Product, sales: list[SaleRecord] | None = None) -> SalesSummary:
    sale_rows = sales if sales is not None else list(product.sales)
    total_quantity = sum(max(sale.quantity, 0) for sale in sale_rows)
    total_revenue = sum(max(sale.revenue, 0) for sale in sale_rows)
    average_sale_price = (total_revenue / total_quantity) if total_quantity else product.sale_price
    discount_percent = 0.0
    if product.sale_price:
        discount_percent = max((product.sale_price - average_sale_price) / product.sale_price * 100, 0)
    return SalesSummary(
        total_quantity=total_quantity,
        total_revenue=round(total_revenue, 2),
        average_sale_price=round(average_sale_price, 2),
        discount_percent=round(discount_percent, 1),
    )
