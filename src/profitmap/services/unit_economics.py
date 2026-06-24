from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite


@dataclass(slots=True)
class UnitEconomicsInput:
    purchase_price: float
    sale_price: float
    logistics: float
    marketplace_fee: float
    advertising: float
    packaging: float
    taxes: float
    other_costs: float
    fixed_costs: float
    expected_sales: int
    target_profit: float


@dataclass(slots=True)
class UnitEconomicsResult:
    variable_cost: float
    full_cost_per_unit: float
    gross_profit: float
    net_profit_per_unit: float
    margin_percent: float
    markup_percent: float
    roi_percent: float
    break_even_units: int | None
    target_units: int | None
    minimum_price: float
    recommended_price: float
    aggressive_price: float
    premium_price: float


def calculate_unit_economics(data: UnitEconomicsInput) -> UnitEconomicsResult:
    variable_cost = sum(
        [
            data.purchase_price,
            data.logistics,
            data.marketplace_fee,
            data.advertising,
            data.packaging,
            data.taxes,
            data.other_costs,
        ]
    )
    expected_sales = max(data.expected_sales, 1)
    allocated_fixed_per_unit = data.fixed_costs / expected_sales
    full_cost_per_unit = variable_cost + allocated_fixed_per_unit
    gross_profit = data.sale_price - variable_cost
    net_profit_per_unit = data.sale_price - full_cost_per_unit
    margin_percent = (net_profit_per_unit / data.sale_price * 100) if data.sale_price else 0.0
    markup_percent = (net_profit_per_unit / full_cost_per_unit * 100) if full_cost_per_unit else 0.0
    roi_percent = (net_profit_per_unit / variable_cost * 100) if variable_cost else 0.0

    contribution = data.sale_price - variable_cost
    break_even_units = ceil(data.fixed_costs / contribution) if contribution > 0 else None
    target_units = ceil((data.fixed_costs + data.target_profit) / contribution) if contribution > 0 else None

    minimum_price = full_cost_per_unit
    recommended_price = full_cost_per_unit * 1.25
    aggressive_price = max(variable_cost * 1.08, full_cost_per_unit * 1.08)
    premium_price = full_cost_per_unit * 1.65

    return UnitEconomicsResult(
        variable_cost=round(variable_cost, 2),
        full_cost_per_unit=round(full_cost_per_unit, 2),
        gross_profit=round(gross_profit, 2),
        net_profit_per_unit=round(net_profit_per_unit, 2),
        margin_percent=_clean_percent(margin_percent),
        markup_percent=_clean_percent(markup_percent),
        roi_percent=_clean_percent(roi_percent),
        break_even_units=break_even_units,
        target_units=target_units,
        minimum_price=round(minimum_price, 2),
        recommended_price=round(recommended_price, 2),
        aggressive_price=round(aggressive_price, 2),
        premium_price=round(premium_price, 2),
    )


def _clean_percent(value: float) -> float:
    if not isfinite(value):
        return 0.0
    return round(value, 1)
