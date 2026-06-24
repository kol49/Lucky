from __future__ import annotations

from dataclasses import dataclass

from profitmap.db.models import Product


@dataclass(slots=True)
class ProfitCoefficient:
    name: str
    formula: str
    calculation: str
    percent: float


def build_profit_coefficients(products: list[Product], fixed_expenses: float, returns_and_discounts: float = 0.0) -> list[ProfitCoefficient]:
    net_sales = sum(product.sale_price * product.expected_monthly_sales for product in products)
    gross_profit = sum((product.sale_price - product.purchase_price) * product.expected_monthly_sales for product in products)
    operating_expenses = fixed_expenses + sum(
        (
            product.logistics
            + product.marketplace_fee
            + product.advertising
            + product.packaging
            + product.taxes
            + product.other_costs
        )
        * product.expected_monthly_sales
        for product in products
    )
    net_profit = gross_profit - operating_expenses

    return [
        ProfitCoefficient(
            name="Доля валовой прибыли",
            formula="Валовая прибыль / Объем продаж-нетто",
            calculation=_calculation(gross_profit, net_sales),
            percent=_ratio_percent(gross_profit, net_sales),
        ),
        ProfitCoefficient(
            name="Доля чистой прибыли",
            formula="Чистая прибыль / Объем продаж-нетто",
            calculation=_calculation(net_profit, net_sales),
            percent=_ratio_percent(net_profit, net_sales),
        ),
        ProfitCoefficient(
            name="Доля эксплуатационных расходов",
            formula="Общая сумма издержек / Объем продаж-нетто",
            calculation=_calculation(operating_expenses, net_sales),
            percent=_ratio_percent(operating_expenses, net_sales),
        ),
        ProfitCoefficient(
            name="Доля возмещений и скидок",
            formula="Возмещения и скидки / Объем продаж-нетто",
            calculation=_calculation(returns_and_discounts, net_sales),
            percent=_ratio_percent(returns_and_discounts, net_sales),
        ),
    ]


def _ratio_percent(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return round(numerator / denominator * 100, 1)


def _calculation(numerator: float, denominator: float) -> str:
    return f"{_money(numerator)} / {_money(denominator)}"


def _money(value: float) -> str:
    return f"${value:,.2f}"
