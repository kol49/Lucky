from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from profitmap.db.models import Base, FixedExpense, Product, SaleRecord


def init_database(db_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False, future=True)
    seed_database(factory)
    return factory


def seed_database(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        has_products = session.scalar(select(Product.id).limit(1))
        if has_products:
            return

        products = [
            Product(
                sku="PM-001",
                name="Premium Coffee Beans 1kg",
                category="Food",
                subcategory="Coffee",
                brand="RoastLab",
                stock=320,
                purchase_price=8.40,
                sale_price=18.90,
                logistics=1.10,
                marketplace_fee=1.35,
                advertising=0.85,
                packaging=0.45,
                taxes=0.95,
                other_costs=0.20,
                fixed_cost_allocation=1250,
                expected_monthly_sales=420,
                supplier_name="North Bean Supply",
                supplier_contact="Anna Keller",
                supplier_phone="+48 500 111 222",
                supplier_email="orders@northbean.example",
                supplier_site="https://northbean.example",
                product_url="https://market.example/coffee",
                lead_time_days=10,
                minimum_order_quantity=100,
            ),
            Product(
                sku="PM-002",
                name="Reusable Water Bottle",
                category="Home",
                subcategory="Kitchen",
                brand="ClearFlow",
                stock=180,
                purchase_price=4.20,
                sale_price=12.50,
                logistics=0.90,
                marketplace_fee=1.00,
                advertising=0.70,
                packaging=0.35,
                taxes=0.55,
                other_costs=0.15,
                fixed_cost_allocation=900,
                expected_monthly_sales=260,
                supplier_name="Eco Trade",
                supplier_contact="Mark Stone",
                supplier_email="sales@ecotrade.example",
                lead_time_days=14,
                minimum_order_quantity=200,
            ),
            Product(
                sku="PM-003",
                name="LED Desk Lamp",
                category="Electronics",
                subcategory="Lighting",
                brand="BrightDesk",
                stock=74,
                purchase_price=14.00,
                sale_price=29.90,
                logistics=2.40,
                marketplace_fee=2.20,
                advertising=1.75,
                packaging=0.80,
                taxes=1.40,
                other_costs=0.60,
                fixed_cost_allocation=1650,
                expected_monthly_sales=140,
                supplier_name="Shenzhen Optics",
                supplier_contact="Li Wei",
                supplier_email="export@szoptics.example",
                lead_time_days=28,
                minimum_order_quantity=50,
            ),
        ]
        session.add_all(products)
        session.flush()

        expenses = [
            FixedExpense(expense_date=date.today(), category="Rent", amount=1800, reason="Office and storage"),
            FixedExpense(expense_date=date.today(), category="Salaries", amount=4200, reason="Operations team"),
            FixedExpense(expense_date=date.today(), category="Subscriptions", amount=360, reason="SaaS tools"),
            FixedExpense(expense_date=date.today(), category="Advertising", amount=1250, reason="Brand campaigns"),
        ]
        session.add_all(expenses)

        for product in products:
            for offset in range(120):
                qty = max(0, int(product.expected_monthly_sales / 30 + ((offset % 9) - 4)))
                sale_date = date.today() - timedelta(days=119 - offset)
                session.add(
                    SaleRecord(
                        product_id=product.id,
                        sale_date=sale_date,
                        quantity=qty,
                        unit_price=product.sale_price,
                        revenue=qty * product.sale_price,
                    )
                )

        session.commit()
