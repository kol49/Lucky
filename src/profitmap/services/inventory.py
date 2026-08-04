from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from profitmap.db.models import Product, ProductSupply
from profitmap.services.unit_economics import UnitEconomicsInput, calculate_unit_economics


@dataclass(slots=True)
class SupplySummary:
    total_quantity: int
    total_cost: float
    remaining_quantity: int
    remaining_cost: float
    total_average_purchase_price: float
    average_purchase_price: float
    minimum_price: float
    recommended_price: float
    aggressive_price: float
    premium_price: float


def calculate_supply_summary(product: Product, supplies: list[ProductSupply] | None = None) -> SupplySummary:
    supply_rows = supplies if supplies is not None else list(product.supplies)
    total_quantity = sum(max(supply.quantity, 0) for supply in supply_rows)
    total_cost = sum(max(supply.quantity, 0) * max(supply.unit_purchase_price, 0) for supply in supply_rows)
    total_average_purchase_price = (total_cost / total_quantity) if total_quantity else product.purchase_price
    remaining_quantity, remaining_cost = _remaining_inventory_cost(product, supply_rows)
    average_purchase_price = (remaining_cost / remaining_quantity) if remaining_quantity else total_average_purchase_price

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
        remaining_quantity=remaining_quantity,
        remaining_cost=round(remaining_cost, 2),
        total_average_purchase_price=round(total_average_purchase_price, 2),
        average_purchase_price=round(average_purchase_price, 2),
        minimum_price=economics.minimum_price,
        recommended_price=economics.recommended_price,
        aggressive_price=economics.aggressive_price,
        premium_price=economics.premium_price,
    )


def _remaining_inventory_cost(product: Product, supplies: list[ProductSupply]) -> tuple[int, float]:
    supply_rows = sorted(supplies, key=lambda supply: (supply.supply_date, supply.id or 0))
    sale_rows = sorted(product.sales, key=lambda sale: (sale.sale_date, sale.id or 0))
    supply_index = 0
    lots: list[list[float]] = []

    for sale in sale_rows:
        while supply_index < len(supply_rows) and supply_rows[supply_index].supply_date <= sale.sale_date:
            supply = supply_rows[supply_index]
            quantity = max(supply.quantity, 0)
            if quantity:
                lots.append([float(quantity), max(supply.unit_purchase_price, 0.0)])
            supply_index += 1

        remaining = max(sale.quantity, 0)
        for lot in lots:
            if remaining <= 0:
                break
            used_quantity = min(remaining, lot[0])
            lot[0] -= used_quantity
            remaining -= used_quantity

    while supply_index < len(supply_rows):
        supply = supply_rows[supply_index]
        quantity = max(supply.quantity, 0)
        if quantity:
            lots.append([float(quantity), max(supply.unit_purchase_price, 0.0)])
        supply_index += 1

    remaining_quantity = int(sum(lot[0] for lot in lots))
    remaining_cost = sum(lot[0] * lot[1] for lot in lots)
    return remaining_quantity, remaining_cost


def refresh_product_from_supplies(session: Session, product: Product, fallback_stock_delta: int = 0) -> SupplySummary:
    supplies = list(
        session.scalars(
            select(ProductSupply).where(ProductSupply.product_id == product.id).order_by(ProductSupply.supply_date)
        )
    )
    summary = calculate_supply_summary(product, supplies)
    if supplies:
        product.stock = summary.remaining_quantity
        product.purchase_price = summary.average_purchase_price
    elif fallback_stock_delta:
        product.stock = max(product.stock + fallback_stock_delta, 0)
    session.flush()
    return summary
