from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import func, select

from profitmap.db.models import FixedExpense, Product, ProductSupply, SaleRecord
from profitmap.db.session import init_database
from profitmap.services.ai_consultant import analyze_business
from profitmap.services.allocation import allocate_fixed_expenses
from profitmap.services.coefficients import build_profit_coefficients
from profitmap.services.demand import forecast_demand
from profitmap.services.inventory import calculate_supply_summary, refresh_product_from_supplies
from profitmap.services.sales import calculate_sales_summary
from profitmap.services.unit_economics import UnitEconomicsInput, calculate_unit_economics

load_dotenv()

WEB_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("PROFITMAP_DB", Path.home() / "profitmap_web.sqlite3"))
SessionFactory = init_database(DB_PATH)
AUTH_USERNAME = os.getenv("PROFITMAP_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("PROFITMAP_PASSWORD", "change-me-now")
SECRET_KEY = os.getenv("PROFITMAP_SECRET_KEY", secrets.token_urlsafe(48))
SESSION_COOKIE = "profitmap_session"
SESSION_TTL_SECONDS = int(os.getenv("PROFITMAP_SESSION_TTL_SECONDS", "43200"))
LOGIN_WINDOW_SECONDS = int(os.getenv("PROFITMAP_LOGIN_WINDOW_SECONDS", "900"))
LOGIN_LOCK_SECONDS = int(os.getenv("PROFITMAP_LOGIN_LOCK_SECONDS", "900"))
LOGIN_MAX_ATTEMPTS = int(os.getenv("PROFITMAP_LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_ATTEMPTS: dict[str, dict[str, float]] = {}

app = FastAPI(title="ProfitMap Web", version="0.1.0")
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")


class ProductPayload(BaseModel):
    sku: str = ""
    name: str = "Новый товар"
    category: str = ""
    product_class: str = ""
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


class SupplyPayload(BaseModel):
    supply_date: date
    quantity: int
    unit_purchase_price: float
    supplier_name: str = ""
    comment: str = ""


class SalePayload(BaseModel):
    sale_date: date
    quantity: int
    unit_price: float
    comment: str = ""


class GlobalSalePayload(SalePayload):
    product_id: int


class AllocationPayload(BaseModel):
    method: str


@app.middleware("http")
async def require_authentication(request: Request, call_next):
    if _is_public_path(request.url.path):
        return await call_next(request)
    if _verify_session(request.cookies.get(SESSION_COOKIE)):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if _verify_session(request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": "", "locked_for": 0})


@app.post("/login", response_class=HTMLResponse)
async def login(request: Request):
    client_ip = _client_ip(request)
    locked_for = _locked_for(client_ip)
    if locked_for > 0:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Слишком много попыток. Попробуйте позже.", "locked_for": int(locked_for)},
            status_code=429,
        )

    form = parse_qs((await request.body()).decode("utf-8"))
    username = form.get("username", [""])[0]
    password = form.get("password", [""])[0]
    if hmac.compare_digest(username, AUTH_USERNAME) and hmac.compare_digest(password, AUTH_PASSWORD):
        LOGIN_ATTEMPTS.pop(client_ip, None)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            _create_session(username),
            httponly=True,
            secure=os.getenv("PROFITMAP_COOKIE_SECURE", "0") == "1",
            samesite="lax",
            max_age=SESSION_TTL_SECONDS,
        )
        return response

    locked_for = _record_failed_login(client_ip)
    message = "Неверный логин или пароль."
    if locked_for > 0:
        message = "Слишком много попыток. IP временно заблокирован."
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": message, "locked_for": int(locked_for)},
        status_code=401,
    )


@app.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/api/state")
def state() -> dict[str, Any]:
    with SessionFactory() as session:
        products = list(session.scalars(select(Product).order_by(Product.name)))
        expenses = list(session.scalars(select(FixedExpense).order_by(FixedExpense.expense_date.desc())))
        return {
            "products": [_product_summary(product) for product in products],
            "selectedProduct": _product_detail(products[0]) if products else None,
            "sales": _all_sales(session),
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
        refresh_product_from_supplies(session, product)
        session.commit()
        return _product_detail(product)


@app.delete("/api/products/{product_id}")
def delete_product(product_id: int) -> dict[str, str]:
    with SessionFactory() as session:
        product = session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        session.delete(product)
        session.commit()
        return {"status": "deleted"}


@app.post("/api/products/{product_id}/supplies")
def create_supply(product_id: int, payload: SupplyPayload) -> dict[str, Any]:
    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero")
    if payload.unit_purchase_price < 0:
        raise HTTPException(status_code=400, detail="Purchase price cannot be negative")
    with SessionFactory() as session:
        product = session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        supply = ProductSupply(
            product_id=product.id,
            supply_date=payload.supply_date,
            quantity=payload.quantity,
            unit_purchase_price=payload.unit_purchase_price,
            supplier_name=payload.supplier_name or product.supplier_name,
            comment=payload.comment,
        )
        session.add(supply)
        session.flush()
        refresh_product_from_supplies(session, product)
        session.commit()
        return _product_detail(product)


@app.delete("/api/products/{product_id}/supplies/{supply_id}")
def delete_supply(product_id: int, supply_id: int) -> dict[str, Any]:
    with SessionFactory() as session:
        product = session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        supply = session.get(ProductSupply, supply_id)
        if not supply or supply.product_id != product.id:
            raise HTTPException(status_code=404, detail="Supply not found")
        quantity = supply.quantity
        session.delete(supply)
        session.flush()
        refresh_product_from_supplies(session, product, fallback_stock_delta=-quantity)
        session.commit()
        return _product_detail(product)


@app.post("/api/products/{product_id}/sales")
def create_sale(product_id: int, payload: SalePayload) -> dict[str, Any]:
    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero")
    if payload.unit_price < 0:
        raise HTTPException(status_code=400, detail="Sale price cannot be negative")
    with SessionFactory() as session:
        product = session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        sale = SaleRecord(
            product_id=product.id,
            sale_date=payload.sale_date,
            quantity=payload.quantity,
            unit_price=payload.unit_price,
            revenue=round(payload.quantity * payload.unit_price, 2),
            comment=payload.comment,
        )
        session.add(sale)
        session.flush()
        refresh_product_from_supplies(session, product, fallback_stock_delta=-payload.quantity)
        session.commit()
        return _product_detail(product)


@app.get("/api/sales")
def get_sales() -> list[dict[str, Any]]:
    with SessionFactory() as session:
        return _all_sales(session)


@app.post("/api/sales")
def create_global_sale(payload: GlobalSalePayload) -> dict[str, Any]:
    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero")
    if payload.unit_price < 0:
        raise HTTPException(status_code=400, detail="Sale price cannot be negative")
    with SessionFactory() as session:
        product = session.get(Product, payload.product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        sale = SaleRecord(
            product_id=product.id,
            sale_date=payload.sale_date,
            quantity=payload.quantity,
            unit_price=payload.unit_price,
            revenue=round(payload.quantity * payload.unit_price, 2),
            comment=payload.comment,
        )
        session.add(sale)
        session.flush()
        refresh_product_from_supplies(session, product, fallback_stock_delta=-payload.quantity)
        session.commit()
        return _sale_with_product_dict(sale, product)


@app.delete("/api/sales/{sale_id}")
def delete_global_sale(sale_id: int) -> dict[str, str]:
    with SessionFactory() as session:
        sale = session.get(SaleRecord, sale_id)
        if not sale:
            raise HTTPException(status_code=404, detail="Sale not found")
        product = sale.product
        quantity = sale.quantity
        session.delete(sale)
        session.flush()
        refresh_product_from_supplies(session, product, fallback_stock_delta=quantity)
        session.commit()
        return {"status": "deleted"}


@app.delete("/api/products/{product_id}/sales/{sale_id}")
def delete_sale(product_id: int, sale_id: int) -> dict[str, Any]:
    with SessionFactory() as session:
        product = session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        sale = session.get(SaleRecord, sale_id)
        if not sale or sale.product_id != product.id:
            raise HTTPException(status_code=404, detail="Sale not found")
        quantity = sale.quantity
        session.delete(sale)
        session.flush()
        refresh_product_from_supplies(session, product, fallback_stock_delta=quantity)
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


@app.delete("/api/expenses/{expense_id}")
def delete_expense(expense_id: int) -> dict[str, str]:
    with SessionFactory() as session:
        expense = session.get(FixedExpense, expense_id)
        if not expense:
            raise HTTPException(status_code=404, detail="Expense not found")
        session.delete(expense)
        session.commit()
        return {"status": "deleted"}


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
        "product_class": product.product_class,
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
    supplies = sorted(product.supplies, key=lambda supply: (supply.supply_date, supply.id), reverse=True)
    sales = sorted(product.sales, key=lambda sale: (sale.sale_date, sale.id), reverse=True)
    supply_summary = calculate_supply_summary(product, supplies)
    sales_summary = calculate_sales_summary(product, sales)
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
            "supply_summary": asdict(supply_summary),
            "supplies": [_supply_dict(supply) for supply in supplies],
            "sales_summary": asdict(sales_summary),
            "sales": [_sale_dict(sale, product.sale_price) for sale in sales],
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


def _supply_dict(supply: ProductSupply) -> dict[str, Any]:
    return {
        "id": supply.id,
        "supply_date": supply.supply_date.isoformat(),
        "quantity": supply.quantity,
        "unit_purchase_price": supply.unit_purchase_price,
        "total_cost": round(supply.quantity * supply.unit_purchase_price, 2),
        "supplier_name": supply.supplier_name,
        "comment": supply.comment,
    }


def _sale_dict(sale: SaleRecord, base_sale_price: float) -> dict[str, Any]:
    discount_percent = 0.0
    if base_sale_price:
        discount_percent = max((base_sale_price - sale.unit_price) / base_sale_price * 100, 0)
    return {
        "id": sale.id,
        "sale_date": sale.sale_date.isoformat(),
        "quantity": sale.quantity,
        "unit_price": sale.unit_price,
        "revenue": sale.revenue,
        "discount_percent": round(discount_percent, 1),
        "comment": sale.comment,
    }


def _sale_with_product_dict(sale: SaleRecord, product: Product) -> dict[str, Any]:
    payload = _sale_dict(sale, product.sale_price)
    payload.update(
        {
            "product_id": product.id,
            "product_name": product.name,
            "product_sku": product.sku,
            "base_sale_price": product.sale_price,
        }
    )
    return payload


def _all_sales(session) -> list[dict[str, Any]]:
    rows = session.execute(
        select(SaleRecord, Product)
        .join(Product, SaleRecord.product_id == Product.id)
        .order_by(SaleRecord.sale_date.desc(), SaleRecord.id.desc())
    )
    return [_sale_with_product_dict(sale, product) for sale, product in rows]


def _analytics(session, products: list[Product]) -> dict[str, Any]:
    total_revenue = float(session.scalar(select(func.coalesce(func.sum(SaleRecord.revenue), 0))) or 0)
    total_fixed = float(session.scalar(select(func.coalesce(func.sum(FixedExpense.amount), 0))) or 0)
    rows = []
    total_profit = 0.0
    for product in products:
        economics = _economics(product)
        sales = list(product.sales)
        if sales:
            revenue = sum(sale.revenue for sale in sales)
            quantity = sum(sale.quantity for sale in sales)
            profit = sum((sale.unit_price - economics.full_cost_per_unit) * sale.quantity for sale in sales)
        else:
            revenue = product.sale_price * product.expected_monthly_sales
            quantity = product.expected_monthly_sales
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
                "quantity": quantity,
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


def _is_public_path(path: str) -> bool:
    return path in {"/login", "/favicon.ico"} or path.startswith("/static/")


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _create_session(username: str) -> str:
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    nonce = secrets.token_urlsafe(16)
    payload = f"{username}|{expires_at}|{nonce}"
    signature = hmac.new(SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}|{signature}"


def _verify_session(cookie_value: str | None) -> bool:
    if not cookie_value:
        return False
    parts = cookie_value.split("|")
    if len(parts) != 4:
        return False
    username, expires_at, nonce, signature = parts
    if not nonce:
        return False
    try:
        if int(expires_at) < int(time.time()):
            return False
    except ValueError:
        return False
    payload = f"{username}|{expires_at}|{nonce}"
    expected = hmac.new(SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected) and hmac.compare_digest(username, AUTH_USERNAME)


def _locked_for(client_ip: str) -> float:
    attempt = LOGIN_ATTEMPTS.get(client_ip)
    if not attempt:
        return 0
    locked_until = attempt.get("locked_until", 0)
    remaining = locked_until - time.time()
    if remaining <= 0 and locked_until:
        LOGIN_ATTEMPTS.pop(client_ip, None)
        return 0
    return max(remaining, 0)


def _record_failed_login(client_ip: str) -> float:
    now = time.time()
    attempt = LOGIN_ATTEMPTS.get(client_ip, {"count": 0, "first_attempt": now, "locked_until": 0})
    if now - attempt.get("first_attempt", now) > LOGIN_WINDOW_SECONDS:
        attempt = {"count": 0, "first_attempt": now, "locked_until": 0}
    attempt["count"] = attempt.get("count", 0) + 1
    if attempt["count"] >= LOGIN_MAX_ATTEMPTS:
        attempt["locked_until"] = now + LOGIN_LOCK_SECONDS
    LOGIN_ATTEMPTS[client_ip] = attempt
    return _locked_for(client_ip)
