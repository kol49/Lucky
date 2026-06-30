from __future__ import annotations

import argparse
import hashlib
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from profitmap.db.models import Product, SaleRecord, VariableExpense
from profitmap.db.session import init_database

MONTHS = {
    "январь": 1,
    "січень": 1,
    "февраль": 2,
    "лютий": 2,
    "март": 3,
    "березень": 3,
    "квітень": 4,
    "апрель": 4,
    "май": 5,
    "травень": 5,
    "июнь": 6,
    "червень": 6,
    "июль": 7,
    "липень": 7,
    "август": 8,
    "серпень": 8,
    "сентябрь": 9,
    "вересень": 9,
    "октябрь": 10,
    "жовтень": 10,
    "ноябрь": 11,
    "листопад": 11,
    "декабрь": 12,
    "грудень": 12,
}
SOURCE_PREFIX = "Excel import Книга111"


def main() -> int:
    parser = argparse.ArgumentParser(description="Import ProfitMap products, sales, and variable expenses from Excel.")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--db", type=Path, default=Path(os.getenv("PROFITMAP_DB", Path.home() / "profitmap_web.sqlite3")))
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()

    factory = init_database(args.db)
    rows = parse_workbook(args.workbook, args.year)
    with factory() as session:
        result = import_rows(session, rows, args.workbook.name)
        session.commit()
    print(result)
    return 0


def parse_workbook(path: Path, year: int) -> list[dict[str, Any]]:
    frame = pd.read_excel(path, sheet_name="Лист1", header=None)
    rows: list[dict[str, Any]] = []
    current_month = 1
    for index, row in frame.iterrows():
        month = month_from_row(row)
        if month:
            current_month = month
            continue

        category = clean_text(row.get(1))
        name = clean_text(row.get(2))
        quantity = number(row.get(3))
        purchase_price = number(row.get(6))
        sale_price = number(row.get(7))
        profit = number(row.get(9))
        expense_name = name.lower()

        if expense_name in {"пересылка", "доставка"} and purchase_price > 0:
            rows.append(
                {
                    "type": "variable_expense",
                    "date": date(year, current_month, 1),
                    "category": "Доставка",
                    "amount": purchase_price,
                    "reason": name,
                    "source_row": index + 1,
                }
            )
            continue

        if not category or not name or quantity <= 0 or sale_price <= 0:
            continue
        rows.append(
            {
                "type": "sale",
                "date": date(year, current_month, 1),
                "category": category,
                "name": name,
                "quantity": int(round(quantity)),
                "purchase_price": purchase_price,
                "sale_price": sale_price,
                "profit": profit,
                "source_row": index + 1,
            }
        )
    return rows


def import_rows(session, rows: list[dict[str, Any]], workbook_name: str) -> dict[str, int]:
    sale_rows = [row for row in rows if row["type"] == "sale"]
    product_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"qty": 0, "purchase": 0.0, "revenue": 0.0, "category": ""})
    for row in sale_rows:
        stats = product_stats[row["name"]]
        stats["qty"] += row["quantity"]
        stats["purchase"] += row["purchase_price"] * row["quantity"]
        stats["revenue"] += row["sale_price"] * row["quantity"]
        stats["category"] = stats["category"] or row["category"]

    products: dict[str, Product] = {}
    products_created = 0
    products_updated = 0
    for name, stats in product_stats.items():
        product = session.scalar(select(Product).where(Product.name == name))
        if product is None:
            sku = unique_excel_sku(session, name)
            product = Product(
                sku=sku,
                name=name,
                category=stats["category"],
                product_class="Excel",
                stock=0,
                expected_monthly_sales=max(int(round(stats["qty"] / 6)), 1),
            )
            session.add(product)
            products_created += 1
        else:
            products_updated += 1
            if not product.category:
                product.category = stats["category"]
            if not product.product_class:
                product.product_class = "Excel"
        if stats["qty"]:
            product.purchase_price = round(stats["purchase"] / stats["qty"], 2)
            product.sale_price = round(stats["revenue"] / stats["qty"], 2)
        products[name] = product
    session.flush()

    sales_created = 0
    for row in sale_rows:
        comment = source_comment(workbook_name, row)
        exists = session.scalar(select(SaleRecord.id).where(SaleRecord.comment == comment))
        if exists:
            continue
        product = products[row["name"]]
        session.add(
            SaleRecord(
                product_id=product.id,
                sale_date=row["date"],
                quantity=row["quantity"],
                unit_price=row["sale_price"],
                revenue=round(row["quantity"] * row["sale_price"], 2),
                comment=comment,
            )
        )
        sales_created += 1

    variable_expenses_created = 0
    for row in [item for item in rows if item["type"] == "variable_expense"]:
        comment = source_comment(workbook_name, row)
        exists = session.scalar(select(VariableExpense.id).where(VariableExpense.comment == comment))
        if exists:
            continue
        session.add(
            VariableExpense(
                expense_date=row["date"],
                category=row["category"],
                amount=row["amount"],
                reason=row["reason"],
                comment=comment,
            )
        )
        variable_expenses_created += 1

    return {
        "products_created": products_created,
        "products_updated": products_updated,
        "sales_created": sales_created,
        "variable_expenses_created": variable_expenses_created,
    }


def month_from_row(row) -> int | None:
    for value in row.dropna().tolist():
        key = str(value).strip().lower()
        if key in MONTHS:
            return MONTHS[key]
    return None


def clean_text(value) -> str:
    if pd.isna(value):
        return ""
    return " ".join(str(value).strip().split())


def number(value) -> float:
    if pd.isna(value):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def unique_excel_sku(session, name: str) -> str:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8].upper()
    base = f"XLS-{digest}"
    sku = base
    index = 2
    while session.scalar(select(Product.id).where(Product.sku == sku)):
        sku = f"{base}-{index}"
        index += 1
    return sku


def source_comment(workbook_name: str, row: dict[str, Any]) -> str:
    return f"{SOURCE_PREFIX}: {workbook_name}, row {row['source_row']}, month {row['date'].strftime('%Y-%m')}"


if __name__ == "__main__":
    raise SystemExit(main())
