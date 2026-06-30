from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from profitmap.db.models import Product, ProductSupply, SaleRecord
from profitmap.services.unit_economics import UnitEconomicsInput, calculate_unit_economics


@dataclass(slots=True)
class SupplySummary:
    total_quantity: int
    total_cost: float
    average_purchase_price: float
    minimum_price: float
    recommended_price: float
    aggressive_price: float
    premium_price: float


def calculate_supply_summary(product: Product, supplies: list[ProductSupply] | None = None) -> SupplySummary:
    supply_rows = supplies if supplies is not None else list(product.supplies)
    total_quantity = sum(max(supply.quantity, 0) for supply in supply_rows)
    total_cost = sum(max(supply.quantity, 0) * max(supply.unit_purchase_price, 0) for supply in supply_rows)
    average_purchase_price = (total_cost / total_quantity) if total_quantity else product.purchase_price

    economics = calculate_unit_economics(
        UnitEconomicsInput(
            purchase_price=average_purchase_price,
            sale_price=product.sale_price,
            logistics=product.logistics,
            marketplace_fee=product.marketplace_fee,
            advertising=product.advertising,
            packaging=product.packaging,
            taxes=product.taxes,
            other_costs=product.other_costs,
            fixed_costs=product.fixed_cost_allocation,
            expected_sales=product.expected_monthly_sales,
            target_profit=1000,
        )
    )
    return SupplySummary(
        total_quantity=total_quantity,
        total_cost=round(total_cost, 2),
        average_purchase_price=round(average_purchase_price, 2),
        minimum_price=economics.minimum_price,
        recommended_price=economics.recommended_price,
        aggressive_price=economics.aggressive_price,
        premium_price=economics.premium_price,
    )


def refresh_product_from_supplies(session: Session, product: Product, fallback_stock_delta: int = 0) -> SupplySummary:
    supplies = list(
        session.scalars(
            select(ProductSupply).where(ProductSupply.product_id == product.id).order_by(ProductSupply.supply_date)
        )
    )
    summary = calculate_supply_summary(product, supplies)
    if supplies:
        sold_quantity = int(
            session.scalar(
                select(func.coalesce(func.sum(SaleRecord.quantity), 0)).where(SaleRecord.product_id == product.id)
            )
            or 0
        )
        product.stock = max(summary.total_quantity - sold_quantity, 0)
        product.purchase_price = summary.average_purchase_price
    elif fallback_stock_delta:
        product.stock = max(product.stock + fallback_stock_delta, 0)
    session.flush()
    return summary
