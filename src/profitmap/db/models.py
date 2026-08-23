from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(120), default="")
    product_class: Mapped[str] = mapped_column(String(120), default="")
    subcategory: Mapped[str] = mapped_column(String(120), default="")
    brand: Mapped[str] = mapped_column(String(120), default="")
    stock: Mapped[int] = mapped_column(Integer, default=0)
    image_path: Mapped[str] = mapped_column(String(500), default="")

    purchase_price: Mapped[float] = mapped_column(Float, default=0.0)
    sale_price: Mapped[float] = mapped_column(Float, default=0.0)
    logistics: Mapped[float] = mapped_column(Float, default=0.0)
    marketplace_fee: Mapped[float] = mapped_column(Float, default=0.0)
    advertising: Mapped[float] = mapped_column(Float, default=0.0)
    packaging: Mapped[float] = mapped_column(Float, default=0.0)
    taxes: Mapped[float] = mapped_column(Float, default=0.0)
    other_costs: Mapped[float] = mapped_column(Float, default=0.0)
    fixed_cost_allocation: Mapped[float] = mapped_column(Float, default=0.0)
    expected_monthly_sales: Mapped[int] = mapped_column(Integer, default=100)

    supplier_name: Mapped[str] = mapped_column(String(255), default="")
    supplier_contact: Mapped[str] = mapped_column(String(255), default="")
    supplier_phone: Mapped[str] = mapped_column(String(64), default="")
    supplier_email: Mapped[str] = mapped_column(String(255), default="")
    supplier_site: Mapped[str] = mapped_column(String(255), default="")
    product_url: Mapped[str] = mapped_column(String(500), default="")
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7)
    minimum_order_quantity: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sales: Mapped[list["SaleRecord"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    supplies: Mapped[list["ProductSupply"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    kits: Mapped[list["ProductKit"]] = relationship(back_populates="base_product", cascade="all, delete-orphan")


class ProductSupply(Base):
    __tablename__ = "product_supplies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    supply_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    unit_purchase_price: Mapped[float] = mapped_column(Float, default=0.0)
    supplier_name: Mapped[str] = mapped_column(String(255), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    product: Mapped[Product] = relationship(back_populates="supplies")


class ProductKit(Base):
    __tablename__ = "product_kits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    base_product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    kit_sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kit_name: Mapped[str] = mapped_column(String(255), default="")
    units_per_kit: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    base_product: Mapped[Product] = relationship(back_populates="kits")


class FixedExpense(Base):
    __tablename__ = "fixed_expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expense_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    category: Mapped[str] = mapped_column(String(120), index=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(String(255), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class VariableExpense(Base):
    __tablename__ = "variable_expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expense_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    category: Mapped[str] = mapped_column(String(120), index=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(String(255), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SaleRecord(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    sale_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    revenue: Mapped[float] = mapped_column(Float, default=0.0)
    comment: Mapped[str] = mapped_column(Text, default="")
    external_source: Mapped[str] = mapped_column(String(64), default="", index=True)
    external_id: Mapped[str] = mapped_column(String(128), default="", index=True)

    product: Mapped[Product] = relationship(back_populates="sales")


class ExpenseAllocation(Base):
    __tablename__ = "expense_allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    method: Mapped[str] = mapped_column(String(64), default="revenue")
    allocated_amount: Mapped[float] = mapped_column(Float, default=0.0)
    period: Mapped[str] = mapped_column(String(32), default="monthly")
