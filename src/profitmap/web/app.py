from __future__ import annotations

import os
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import func, select

from profitmap.db.models import FixedExpense, Product, SaleRecord
from profitmap.db.session import init_database
from profitmap.services.ai_consultant import analyze_business
from profitmap.services.allocation import allocate_fixed_expenses
from profitmap.services.coefficients import build_profit_coefficients
from profitmap.services.demand import forecast_demand
from profitmap.services.unit_economics import UnitEconomicsInput, calculate_unit_economics

load_dotenv()

WEB_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("PROFITMAP_DB", Path.home() / "profitmap_web.sqlite3"))
SessionFactory = init_database(DB_PATH)

app = FastAPI(title="ProfitMap Web", version="0.1.0")
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")


class ProductPayload(BaseModel):
    sku: str = ""
    name: str = "Новый товар"
    category: str = ""
    subcategory: str = ""
    brand: str = ""
    stock: int = 0
    purchase_price: float = 0.0
    sale_price: float = 0.0
    logistics: float = 0.0
    marketplace_fee: float = 0.0
    advertising: float = 0.0
    packaging: float = 0.0
    taxes: float = 0.0
    other_costs: float = 0.0
    fixed_cost_allocation: float = 0.0
    expected_monthly_sales: int = 100
    supplier_name: str = ""
    supplier_contact: str = ""
    supplier_phone: str = ""
    supplier_email: str = ""
    supplier_site: str = ""
    product_url: str = ""
    lead_time_days: int = 7
    minimum_order_quantity: int = 1


class ExpensePayload(BaseModel):
    expense_date: date
    category: str
    amount: float
    reason: str = ""
    comment: str = ""


class AllocationPayload(BaseModel):
    method: str


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/state")
def state() -> dict[str, Any]:
    with SessionFactory() as session:
        products = list(session.scalars(select(Product).order_by(Product.name)))
        expenses = list(session.scalars(select(FixedExpense).order_by(FixedExpense.expense_date.desc())))
        return {
            "products": [_product_summary(product) for product in products],
            "selectedProduct": _product_detail(products[0]) if products else None,
            "expenses": [_expense_dict(expense) for expense in expenses],
            "analytics": _analytics(session, products),
        }


@app.get("/api/products/{product_id}")
def get_product(product_id: int) -> dict[str, Any]:
    with SessionFactory() as session:
        product = session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        return _product_detail(product)


@app.post("/api/products")
def create_product(payload: ProductPayload) -> dict[str, Any]:
    with SessionFactory() as session:
        product = Product(**payload.model_dump())
        if not product.sku:
            count = session.scalar(select(func.count(Product.id))) or 0
            product.sku = f"WEB-{count + 1:03d}"
        session.add(product)
        session.commit()
        return _product_detail(product)


@app.put("/api/products/{product_id}")
def update_product(product_id: int, payload: ProductPayload) -> dict[str, Any]:
    with SessionFactory() as session:
        product = session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        for key, value in payload.model_dump().items():
            setattr(product, key, value)
        session.commit()
        return _product_detail(product)


@app.get("/api/expenses")
def get_expenses() -> list[dict[str, Any]]:
    with SessionFactory() as session:
        expenses = list(session.scalars(select(FixedExpense).order_by(FixedExpense.expense_date.desc())))
        return [_expense_dict(expense) for expense in expenses]


@app.post("/api/expenses")
def create_expense(payload: ExpensePayload) -> dict[str, Any]:
    with SessionFactory() as session:
        expense = FixedExpense(
            expense_date=payload.expense_date,
            category=payload.category,
            amount=payload.amount,
            reason=payload.reason,
            comment=payload.comment,
        )
        session.add(expense)
        session.commit()
        return _expense_dict(expense)


@app.post("/api/allocate-expenses")
def allocate_expenses(payload: AllocationPayload) -> dict[str, Any]:
    if payload.method == "manual":
        return {"status": "manual", "message": "Ручное распределение задается в карточке товара."}
    with SessionFactory() as session:
        products = list(session.scalars(select(Product)))
        total_expenses = float(session.scalar(select(func.coalesce(func.sum(FixedExpense.amount), 0))) or 0)
        allocations = allocate_fixed_expenses(products, total_expenses, payload.method)
        for product in products:
            product.fixed_cost_allocation = allocations.get(product.id, 0.0)
        session.commit()
        return {"status": "ok", "allocated": allocations}


@app.get("/api/analytics")
def get_analytics() -> dict[str, Any]:
    with SessionFactory() as session:
        products = list(session.scalars(select(Product).order_by(Product.name)))
        return _analytics(session, products)


@app.post("/api/analyze")
def analyze() -> dict[str, str]:
    with SessionFactory() as session:
        products = list(session.scalars(select(Product)))
        total_fixed = float(session.scalar(select(func.coalesce(func.sum(FixedExpense.amount), 0))) or 0)
        return {"text": analyze_business(products, total_fixed)}


def _product_summary(product: Product) -> dict[str, Any]:
    economics = _economics(product)
    return {
        "id": product.id,
        "sku": product.sku,
        "name": product.name,
        "category": product.category,
        "stock": product.stock,
        "purchase_price": product.purchase_price,
        "sale_price": product.sale_price,
        "profit_per_unit": economics.net_profit_per_unit,
        "margin_percent": economics.margin_percent,
        "roi_percent": economics.roi_percent,
        "supplier_name": product.supplier_name,
    }


def _product_detail(product: Product) -> dict[str, Any]:
    payload = _product_summary(product)
    economics = _economics(product)
    payload.update(
        {
            "subcategory": product.subcategory,
            "brand": product.brand,
            "logistics": product.logistics,
            "marketplace_fee": product.marketplace_fee,
            "advertising": product.advertising,
            "packaging": product.packaging,
            "taxes": product.taxes,
            "other_costs": product.other_costs,
            "fixed_cost_allocation": product.fixed_cost_allocation,
            "expected_monthly_sales": product.expected_monthly_sales,
            "supplier_contact": product.supplier_contact,
            "supplier_phone": product.supplier_phone,
            "supplier_email": product.supplier_email,
            "supplier_site": product.supplier_site,
            "product_url": product.product_url,
            "lead_time_days": product.lead_time_days,
            "minimum_order_quantity": product.minimum_order_quantity,
            "economics": asdict(economics),
        }
    )
    return payload


def _economics(product: Product):
    return calculate_unit_economics(
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


def _expense_dict(expense: FixedExpense) -> dict[str, Any]:
    return {
        "id": expense.id,
        "expense_date": expense.expense_date.isoformat(),
        "category": expense.category,
        "amount": expense.amount,
        "reason": expense.reason,
        "comment": expense.comment,
    }


def _analytics(session, products: list[Product]) -> dict[str, Any]:
    total_revenue = float(session.scalar(select(func.coalesce(func.sum(SaleRecord.revenue), 0))) or 0)
    total_fixed = float(session.scalar(select(func.coalesce(func.sum(FixedExpense.amount), 0))) or 0)
    rows = []
    total_profit = 0.0
    for product in products:
        economics = _economics(product)
        revenue = product.sale_price * product.expected_monthly_sales
        profit = economics.net_profit_per_unit * product.expected_monthly_sales
        total_profit += profit
        quantities = list(
            session.scalars(
                select(SaleRecord.quantity).where(SaleRecord.product_id == product.id).order_by(SaleRecord.sale_date)
            )
        )
        forecast = forecast_demand(quantities, 30)
        rows.append(
            {
                "product": product.name,
                "revenue": revenue,
                "profit": profit,
                "forecast_30_days": forecast.forecast_units,
            }
        )
    ranked = sorted(rows, key=lambda row: row["revenue"], reverse=True)
    total_expected_revenue = sum(row["revenue"] for row in ranked) or 1
    running = 0.0
    for row in ranked:
        running += row["revenue"]
        share = running / total_expected_revenue
        row["abc"] = "A" if share <= 0.8 else "B" if share <= 0.95 else "C"

    coefficients = build_profit_coefficients(products, total_fixed)
    return {
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "cash_flow": total_profit - total_fixed,
        "margin_percent": round((total_profit / total_revenue * 100) if total_revenue else 0, 1),
        "profitable_count": len([row for row in rows if row["profit"] > 0]),
        "loss_count": len([row for row in rows if row["profit"] <= 0]),
        "rows": ranked,
        "coefficients": [asdict(coefficient) for coefficient in coefficients],
    }
