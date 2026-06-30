from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from profitmap.db.models import Product, ProductSupply, SaleRecord, VariableExpense
from profitmap.db.session import init_database
from profitmap.services.inventory import refresh_product_from_supplies

SOURCE_CLASS = "Bot catalog"


def main() -> int:
    parser = argparse.ArgumentParser(description="Import products from Telegram bot catalog.json files.")
    parser.add_argument("catalogs", nargs="+", type=Path)
    parser.add_argument("--db", type=Path, default=Path(os.getenv("PROFITMAP_DB", Path.home() / "profitmap_web.sqlite3")))
    parser.add_argument("--delete-excel", action="store_true")
    parser.add_argument("--delete-sales", action="store_true")
    args = parser.parse_args()

    factory = init_database(args.db)
    products = load_products(args.catalogs)
    with factory() as session:
        result: dict[str, int] = {}
        if args.delete_excel:
            result.update(delete_excel_import(session))
        if args.delete_sales:
            result.update(delete_sales(session))
        result.update(import_products(session, products))
        session.commit()
    print(result)
    return 0


def load_products(paths: list[Path]) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    seen_articles: set[str] = set()
    for path in paths:
        source = source_name(path)
        with path.open(encoding="utf-8") as handle:
            catalog = json.load(handle)
        for item in catalog:
            article = clean_text(item.get("article"))
            if not article or article in seen_articles:
                continue
            seen_articles.add(article)
            products.append(
                {
                    "source": source,
                    "article": article,
                    "name": clean_text(item.get("name")) or f"Товар {article}",
                    "price": number(item.get("price")),
                    "stock": int(number(item.get("stock"))),
                    "description": clean_text(item.get("description")),
                }
            )
    return products


def delete_excel_import(session) -> dict[str, int]:
    excel_sales = list(session.scalars(select(SaleRecord).where(SaleRecord.comment.like("Excel import%"))))
    excel_expenses = list(
        session.scalars(select(VariableExpense).where(VariableExpense.comment.like("Excel import%")))
    )
    excel_products = list(session.scalars(select(Product).where(Product.product_class == "Excel")))
    counts = {
        "excel_sales_deleted": len(excel_sales),
        "excel_variable_expenses_deleted": len(excel_expenses),
        "excel_products_deleted": len(excel_products),
    }
    for item in excel_sales:
        session.delete(item)
    for item in excel_expenses:
        session.delete(item)
    for item in excel_products:
        session.delete(item)
    session.flush()
    return counts


def delete_sales(session) -> dict[str, int]:
    sales = list(session.scalars(select(SaleRecord)))
    for sale in sales:
        session.delete(sale)
    session.flush()
    return {"sales_deleted": len(sales)}


def import_products(session, products: list[dict[str, Any]]) -> dict[str, int]:
    created = 0
    updated = 0
    supplies_created = 0
    for item in products:
        sku = f"BOT-{item['article']}"
        product = session.scalar(select(Product).where(Product.sku == sku))
        if product is None:
            product = Product(
                sku=sku,
                name=item["name"],
                category=item["source"],
                product_class=SOURCE_CLASS,
                stock=max(item["stock"], 0),
                purchase_price=0.0,
                sale_price=item["price"],
                expected_monthly_sales=max(item["stock"], 1),
                supplier_name=item["source"],
                product_url=f"telegram-catalog:{item['source']}:{item['article']}",
            )
            session.add(product)
            created += 1
        else:
            product.name = item["name"]
            product.category = item["source"]
            product.product_class = SOURCE_CLASS
            product.sale_price = item["price"]
            product.expected_monthly_sales = max(item["stock"], 1)
            product.supplier_name = item["source"]
            product.product_url = f"telegram-catalog:{item['source']}:{item['article']}"
            updated += 1
        session.flush()

        existing_supply = session.scalar(
            select(ProductSupply).where(
                ProductSupply.product_id == product.id,
                ProductSupply.comment == "Bot catalog stock import",
            )
        )
        if existing_supply is None:
            session.add(
                ProductSupply(
                    product_id=product.id,
                    supply_date=date.today(),
                    quantity=max(item["stock"], 0),
                    unit_purchase_price=0.0,
                    supplier_name=item["source"],
                    comment="Bot catalog stock import",
                )
            )
            supplies_created += 1
        else:
            existing_supply.quantity = max(item["stock"], 0)
            existing_supply.supplier_name = item["source"]
        session.flush()
        refresh_product_from_supplies(session, product)
    return {
        "bot_products_created": created,
        "bot_products_updated": updated,
        "bot_supplies_created": supplies_created,
        "bot_sales_imported": 0,
    }


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def source_name(path: Path) -> str:
    name = path.name
    if name.endswith(".catalog.json"):
        return name[: -len(".catalog.json")]
    if name == "catalog.json":
        return path.parent.name
    return path.stem


def number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
