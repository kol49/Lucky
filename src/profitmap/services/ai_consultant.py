from __future__ import annotations

import os

from profitmap.db.models import Product
from profitmap.services.unit_economics import UnitEconomicsInput, calculate_unit_economics


def analyze_business(products: list[Product], total_fixed_expenses: float) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    summary = _build_summary(products, total_fixed_expenses)
    if api_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            response = client.responses.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                input=[
                    {
                        "role": "system",
                        "content": "You are a senior business consultant for ecommerce unit economics. Answer in Russian with concise, actionable recommendations.",
                    },
                    {"role": "user", "content": summary},
                ],
            )
            return response.output_text
        except Exception as exc:
            return _rule_based_recommendations(products, total_fixed_expenses, error=str(exc))
    return _rule_based_recommendations(products, total_fixed_expenses)


def _build_summary(products: list[Product], total_fixed_expenses: float) -> str:
    rows = [f"Постоянные расходы: ${total_fixed_expenses:,.2f}"]
    for product in products:
        result = calculate_unit_economics(
            UnitEconomicsInput(
                purchase_price=product.purchase_price,
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
        rows.append(
            f"{product.sku} {product.name}: stock={product.stock}, price={product.sale_price}, "
            f"net_profit={result.net_profit_per_unit}, margin={result.margin_percent}%, "
            f"roi={result.roi_percent}%, breakeven={result.break_even_units}"
        )
    return "\n".join(rows)


def _rule_based_recommendations(products: list[Product], total_fixed_expenses: float, error: str | None = None) -> str:
    lines: list[str] = []
    if error:
        lines.append(f"OpenAI API недоступен, применен локальный анализ. Причина: {error}")
        lines.append("")
    else:
        lines.append("Локальный AI-анализ ProfitMap")
        lines.append("")

    for product in products:
        result = calculate_unit_economics(
            UnitEconomicsInput(
                purchase_price=product.purchase_price,
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

        if result.margin_percent < 10:
            action = f"поднять цену минимум до ${result.recommended_price:.2f} или снизить переменные расходы"
        elif product.stock < max(product.expected_monthly_sales // 2, 10):
            action = "увеличить закупку, запас ниже половины ожидаемых месячных продаж"
        elif result.roi_percent > 45 and product.stock > product.expected_monthly_sales * 2:
            action = "усилить рекламу или промо, товар прибыльный, но запас высокий"
        elif result.net_profit_per_unit <= 0:
            action = "остановить закупку до пересмотра цены и расходов"
        else:
            action = "оставить в активном ассортименте и контролировать спрос"

        lines.append(
            f"- {product.name}: маржа {result.margin_percent}%, ROI {result.roi_percent}%, "
            f"точка безубыточности {result.break_even_units or 'недостижима'} шт.; рекомендация: {action}."
        )

    lines.append("")
    lines.append(f"Общие постоянные расходы: ${total_fixed_expenses:,.2f}. Проверьте распределение расходов по выручке и марже перед крупной закупкой.")
    return "\n".join(lines)
