from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from profitmap.db.models import FixedExpense, Product, SaleRecord
from profitmap.services.ai_consultant import analyze_business
from profitmap.services.allocation import allocate_fixed_expenses
from profitmap.services.coefficients import build_profit_coefficients
from profitmap.services.demand import forecast_demand
from profitmap.services.unit_economics import UnitEconomicsInput, UnitEconomicsResult, calculate_unit_economics
from profitmap.ui.breakeven_chart import BreakEvenChart
from profitmap.ui.theme import DARK_THEME, LIGHT_THEME


class MainWindow(QMainWindow):
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        super().__init__()
        self.session_factory = session_factory
        self.dark_mode = False
        self.setWindowTitle("ProfitMap")

        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(210)
        self.sidebar.addItems(["Товары", "Постоянные расходы", "Аналитика", "AI-консультант"])
        self.sidebar.setCurrentRow(0)

        sidebar_frame = QFrame()
        sidebar_frame.setObjectName("Sidebar")
        sidebar_layout = QVBoxLayout(sidebar_frame)
        brand = QLabel("ProfitMap")
        brand.setObjectName("Brand")
        brand.setContentsMargins(12, 14, 12, 8)
        sidebar_layout.addWidget(brand)
        sidebar_layout.addWidget(self.sidebar)

        self.theme_button = QPushButton("Темная тема")
        self.theme_button.setObjectName("SecondaryButton")
        self.theme_button.clicked.connect(self.toggle_theme)
        sidebar_layout.addWidget(self.theme_button)

        self.stack = QStackedWidget()
        self.products_page = ProductsPage(session_factory)
        self.expenses_page = ExpensesPage(session_factory, on_changed=self.refresh_all)
        self.analytics_page = AnalyticsPage(session_factory)
        self.ai_page = AIPage(session_factory)
        self.stack.addWidget(self.products_page)
        self.stack.addWidget(self.expenses_page)
        self.stack.addWidget(self.analytics_page)
        self.stack.addWidget(self.ai_page)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar_frame)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.currentRowChanged.connect(lambda _: self.refresh_all())
        self.apply_theme()

    def toggle_theme(self) -> None:
        self.dark_mode = not self.dark_mode
        self.theme_button.setText("Светлая тема" if self.dark_mode else "Темная тема")
        self.apply_theme()

    def apply_theme(self) -> None:
        QApplication.instance().setStyleSheet(DARK_THEME if self.dark_mode else LIGHT_THEME)
        self.products_page.detail.chart.set_dark(self.dark_mode)

    def refresh_all(self) -> None:
        self.products_page.load_products()
        self.analytics_page.refresh()


class ProductsPage(QWidget):
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        super().__init__()
        self.session_factory = session_factory
        self.products: list[Product] = []

        title = QLabel("Товары")
        title.setObjectName("Brand")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по артикулу, названию, категории или поставщику")
        self.search.textChanged.connect(self.load_products)
        add_button = QPushButton("Добавить товар")
        add_button.clicked.connect(self.add_product)

        top = QHBoxLayout()
        top.addWidget(title)
        top.addStretch()
        top.addWidget(self.search, 2)
        top.addWidget(add_button)

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(
            [
                "Артикул",
                "Название",
                "Категория",
                "Остаток",
                "Закупка",
                "Продажа",
                "Прибыль/ед.",
                "Маржа %",
                "ROI",
                "Поставщик",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self.open_selected_product)

        self.detail = ProductDetailWidget(session_factory, on_saved=self.load_products)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.table)
        splitter.addWidget(left)
        splitter.addWidget(self.detail)
        splitter.setSizes([520, 900])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addLayout(top)
        layout.addWidget(splitter, 1)
        self.load_products()

    def load_products(self) -> None:
        query_text = self.search.text().strip().lower()
        with self.session_factory() as session:
            products = list(session.scalars(select(Product).order_by(Product.name)))
            if query_text:
                products = [
                    product
                    for product in products
                    if query_text
                    in " ".join(
                        [
                            product.sku,
                            product.name,
                            product.category,
                            product.supplier_name,
                        ]
                    ).lower()
                ]
            self.products = products
        self.populate_table()
        if self.products and self.detail.product_id is None:
            self.table.selectRow(0)

    def populate_table(self) -> None:
        self.table.setRowCount(len(self.products))
        for row, product in enumerate(self.products):
            result = calculate_for_product(product)
            values = [
                product.sku,
                product.name,
                product.category,
                product.stock,
                money(product.purchase_price),
                money(product.sale_price),
                money(result.net_profit_per_unit),
                f"{result.margin_percent:.1f}",
                f"{result.roi_percent:.1f}",
                product.supplier_name,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in {3, 4, 5, 6, 7, 8}:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, column, item)

    def open_selected_product(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return
        product = self.products[selected[0].row()]
        self.detail.load_product(product.id)

    def add_product(self) -> None:
        with self.session_factory() as session:
            index = session.scalar(select(func.count(Product.id))) or 0
            product = Product(
                sku=f"NEW-{index + 1:03d}",
                name="Новый товар",
                category="Без категории",
                stock=0,
                purchase_price=0,
                sale_price=0,
                expected_monthly_sales=100,
            )
            session.add(product)
            session.commit()
            product_id = product.id
        self.detail.load_product(product_id)
        self.load_products()


class ProductDetailWidget(QWidget):
    def __init__(self, session_factory: sessionmaker[Session], on_saved) -> None:
        super().__init__()
        self.session_factory = session_factory
        self.on_saved = on_saved
        self.product_id: int | None = None
        self.loading = False

        self.name = QLineEdit()
        self.sku = QLineEdit()
        self.category = QLineEdit()
        self.subcategory = QLineEdit()
        self.brand = QLineEdit()
        self.stock = spin_int(0, 1_000_000)
        self.expected_sales = spin_int(1, 1_000_000)

        self.supplier_name = QLineEdit()
        self.supplier_contact = QLineEdit()
        self.supplier_phone = QLineEdit()
        self.supplier_email = QLineEdit()
        self.supplier_site = QLineEdit()
        self.product_url = QLineEdit()
        self.lead_time = spin_int(0, 365)
        self.minimum_order = spin_int(0, 1_000_000)

        self.purchase_price = money_spin()
        self.sale_price = money_spin()
        self.logistics = money_spin()
        self.marketplace_fee = money_spin()
        self.advertising = money_spin()
        self.packaging = money_spin()
        self.taxes = money_spin()
        self.other_costs = money_spin()
        self.fixed_costs = money_spin(10_000_000)
        self.target_profit = QComboBox()
        for value in [500, 1000, 5000, 10000]:
            self.target_profit.addItem(f"{value:,} грн", value)

        watched = [
            self.purchase_price,
            self.sale_price,
            self.logistics,
            self.marketplace_fee,
            self.advertising,
            self.packaging,
            self.taxes,
            self.other_costs,
            self.fixed_costs,
            self.expected_sales,
        ]
        for widget in watched:
            widget.valueChanged.connect(self.recalculate)
        self.target_profit.currentIndexChanged.connect(self.recalculate)

        self.photo = PhotoDropLabel()

        self.metric_labels = {
            "full_cost": QLabel("0.00 грн"),
            "gross": QLabel("0.00 грн"),
            "net": QLabel("0.00 грн"),
            "margin": QLabel("0%"),
            "markup": QLabel("0%"),
            "roi": QLabel("0%"),
            "breakeven": QLabel("0 шт."),
            "target": QLabel("0 шт."),
        }
        for label in self.metric_labels.values():
            label.setObjectName("MetricValue")

        self.price_labels = {
            "min": QLabel("0.00 грн"),
            "recommended": QLabel("0.00 грн"),
            "aggressive": QLabel("0.00 грн"),
            "premium": QLabel("0.00 грн"),
        }
        for label in self.price_labels.values():
            label.setObjectName("MetricValue")

        self.chart = BreakEvenChart()
        self.save_button = QPushButton("Сохранить")
        self.save_button.clicked.connect(self.save_product)
        photo_button = QPushButton("Фото")
        photo_button.setObjectName("SecondaryButton")
        photo_button.clicked.connect(self.pick_photo)

        header = QHBoxLayout()
        header_title = QLabel("Карточка товара")
        header_title.setObjectName("Brand")
        header.addWidget(header_title)
        header.addStretch()
        header.addWidget(photo_button)
        header.addWidget(self.save_button)

        info_tabs = QTabWidget()
        info_tabs.addTab(self.product_tab(), "Основное")
        info_tabs.addTab(self.supplier_tab(), "Поставщик")
        info_tabs.addTab(self.economics_tab(), "Экономика")

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(self.metrics_grid())
        right_layout.addWidget(self.pricing_grid())
        right_layout.addWidget(self.chart, 1)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(info_tabs)
        splitter.addWidget(right_panel)
        splitter.setSizes([360, 720])

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(splitter, 1)

    def product_tab(self) -> QWidget:
        form = QFormLayout()
        form.addRow("Название", self.name)
        form.addRow("Артикул", self.sku)
        form.addRow("Категория", self.category)
        form.addRow("Подкатегория", self.subcategory)
        form.addRow("Бренд", self.brand)
        form.addRow("Остаток", self.stock)
        form.addRow("Ожидаемые продажи/мес.", self.expected_sales)
        form.addRow("Фото", self.photo)
        return scroll_form(form)

    def supplier_tab(self) -> QWidget:
        form = QFormLayout()
        form.addRow("Название поставщика", self.supplier_name)
        form.addRow("Контактное лицо", self.supplier_contact)
        form.addRow("Телефон", self.supplier_phone)
        form.addRow("Email", self.supplier_email)
        form.addRow("Сайт", self.supplier_site)
        form.addRow("Ссылка на товар", self.product_url)
        form.addRow("Срок поставки, дни", self.lead_time)
        form.addRow("Минимальная партия", self.minimum_order)
        return scroll_form(form)

    def economics_tab(self) -> QWidget:
        form = QFormLayout()
        form.addRow("Закупочная цена", self.purchase_price)
        form.addRow("Цена продажи", self.sale_price)
        form.addRow("Логистика", self.logistics)
        form.addRow("Комиссия маркетплейса", self.marketplace_fee)
        form.addRow("Реклама", self.advertising)
        form.addRow("Упаковка", self.packaging)
        form.addRow("Налоги", self.taxes)
        form.addRow("Прочие расходы", self.other_costs)
        form.addRow("Постоянные расходы", self.fixed_costs)
        form.addRow("Целевая прибыль", self.target_profit)
        return scroll_form(form)

    def metrics_grid(self) -> QWidget:
        widget = QWidget()
        layout = QGridLayout(widget)
        labels = [
            ("Полная себестоимость", "full_cost"),
            ("Валовая прибыль", "gross"),
            ("Чистая прибыль", "net"),
            ("Маржа", "margin"),
            ("Наценка", "markup"),
            ("ROI", "roi"),
            ("Безубыточность", "breakeven"),
            ("Целевой объем", "target"),
        ]
        for index, (title, key) in enumerate(labels):
            layout.addWidget(metric_card(title, self.metric_labels[key]), index // 4, index % 4)
        return widget

    def pricing_grid(self) -> QWidget:
        widget = QWidget()
        layout = QGridLayout(widget)
        labels = [
            ("Минимальная цена", "min"),
            ("Рекомендуемая", "recommended"),
            ("Агрессивная", "aggressive"),
            ("Премиальная", "premium"),
        ]
        for index, (title, key) in enumerate(labels):
            layout.addWidget(metric_card(title, self.price_labels[key]), 0, index)
        return widget

    def load_product(self, product_id: int) -> None:
        self.product_id = product_id
        self.loading = True
        with self.session_factory() as session:
            product = session.get(Product, product_id)
            if not product:
                self.loading = False
                return
            self.name.setText(product.name)
            self.sku.setText(product.sku)
            self.category.setText(product.category)
            self.subcategory.setText(product.subcategory)
            self.brand.setText(product.brand)
            self.stock.setValue(product.stock)
            self.expected_sales.setValue(product.expected_monthly_sales)
            self.photo.set_path(product.image_path)
            self.supplier_name.setText(product.supplier_name)
            self.supplier_contact.setText(product.supplier_contact)
            self.supplier_phone.setText(product.supplier_phone)
            self.supplier_email.setText(product.supplier_email)
            self.supplier_site.setText(product.supplier_site)
            self.product_url.setText(product.product_url)
            self.lead_time.setValue(product.lead_time_days)
            self.minimum_order.setValue(product.minimum_order_quantity)
            self.purchase_price.setValue(product.purchase_price)
            self.sale_price.setValue(product.sale_price)
            self.logistics.setValue(product.logistics)
            self.marketplace_fee.setValue(product.marketplace_fee)
            self.advertising.setValue(product.advertising)
            self.packaging.setValue(product.packaging)
            self.taxes.setValue(product.taxes)
            self.other_costs.setValue(product.other_costs)
            self.fixed_costs.setValue(product.fixed_cost_allocation)
        self.loading = False
        self.recalculate()

    def current_input(self) -> UnitEconomicsInput:
        return UnitEconomicsInput(
            purchase_price=self.purchase_price.value(),
            sale_price=self.sale_price.value(),
            logistics=self.logistics.value(),
            marketplace_fee=self.marketplace_fee.value(),
            advertising=self.advertising.value(),
            packaging=self.packaging.value(),
            taxes=self.taxes.value(),
            other_costs=self.other_costs.value(),
            fixed_costs=self.fixed_costs.value(),
            expected_sales=self.expected_sales.value(),
            target_profit=float(self.target_profit.currentData()),
        )

    def recalculate(self) -> None:
        if self.loading:
            return
        data = self.current_input()
        result = calculate_unit_economics(data)
        self.metric_labels["full_cost"].setText(money(result.full_cost_per_unit))
        self.metric_labels["gross"].setText(money(result.gross_profit))
        self.metric_labels["net"].setText(money(result.net_profit_per_unit))
        self.metric_labels["margin"].setText(f"{result.margin_percent:.1f}%")
        self.metric_labels["markup"].setText(f"{result.markup_percent:.1f}%")
        self.metric_labels["roi"].setText(f"{result.roi_percent:.1f}%")
        self.metric_labels["breakeven"].setText(f"{result.break_even_units or 0} шт.")
        self.metric_labels["target"].setText(f"{result.target_units or 0} шт.")
        self.price_labels["min"].setText(money(result.minimum_price))
        self.price_labels["recommended"].setText(money(result.recommended_price))
        self.price_labels["aggressive"].setText(money(result.aggressive_price))
        self.price_labels["premium"].setText(money(result.premium_price))
        self.chart.update_chart(
            sale_price=data.sale_price,
            variable_cost=result.variable_cost,
            fixed_costs=data.fixed_costs,
            break_even_units=result.break_even_units,
            target_units=result.target_units,
            target_profit=data.target_profit,
        )

    def pick_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Фото товара", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.photo.set_path(path)

    def save_product(self) -> None:
        if self.product_id is None:
            return
        with self.session_factory() as session:
            product = session.get(Product, self.product_id)
            if not product:
                return
            product.name = self.name.text().strip() or "Без названия"
            product.sku = self.sku.text().strip() or f"SKU-{product.id}"
            product.category = self.category.text().strip()
            product.subcategory = self.subcategory.text().strip()
            product.brand = self.brand.text().strip()
            product.stock = self.stock.value()
            product.expected_monthly_sales = self.expected_sales.value()
            product.image_path = self.photo.path
            product.supplier_name = self.supplier_name.text().strip()
            product.supplier_contact = self.supplier_contact.text().strip()
            product.supplier_phone = self.supplier_phone.text().strip()
            product.supplier_email = self.supplier_email.text().strip()
            product.supplier_site = self.supplier_site.text().strip()
            product.product_url = self.product_url.text().strip()
            product.lead_time_days = self.lead_time.value()
            product.minimum_order_quantity = self.minimum_order.value()
            product.purchase_price = self.purchase_price.value()
            product.sale_price = self.sale_price.value()
            product.logistics = self.logistics.value()
            product.marketplace_fee = self.marketplace_fee.value()
            product.advertising = self.advertising.value()
            product.packaging = self.packaging.value()
            product.taxes = self.taxes.value()
            product.other_costs = self.other_costs.value()
            product.fixed_cost_allocation = self.fixed_costs.value()
            try:
                session.commit()
            except Exception as exc:
                session.rollback()
                QMessageBox.warning(self, "Не удалось сохранить", str(exc))
                return
        self.on_saved()
        QMessageBox.information(self, "ProfitMap", "Товар сохранен")


class ExpensesPage(QWidget):
    def __init__(self, session_factory: sessionmaker[Session], on_changed) -> None:
        super().__init__()
        self.session_factory = session_factory
        self.on_changed = on_changed

        title = QLabel("Постоянные расходы")
        title.setObjectName("Brand")
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.category = QComboBox()
        self.category.addItems(["Аренда", "Зарплаты", "Интернет", "Электричество", "Бухгалтерия", "Подписки", "Реклама", "Транспорт", "Прочее"])
        self.amount = money_spin(10_000_000)
        self.reason = QLineEdit()
        self.comment = QLineEdit()
        add_button = QPushButton("Добавить")
        add_button.clicked.connect(self.add_expense)

        form = QHBoxLayout()
        form.addWidget(self.date)
        form.addWidget(self.category)
        form.addWidget(self.amount)
        form.addWidget(self.reason)
        form.addWidget(self.comment)
        form.addWidget(add_button)

        self.method = QComboBox()
        self.method.addItem("По выручке", "revenue")
        self.method.addItem("По количеству продаж", "sales_quantity")
        self.method.addItem("По марже", "margin")
        self.method.addItem("Ручное распределение", "manual")
        allocate_button = QPushButton("Распределить")
        allocate_button.clicked.connect(self.allocate)

        allocation = QHBoxLayout()
        allocation.addWidget(QLabel("Метод распределения"))
        allocation.addWidget(self.method)
        allocation.addWidget(allocate_button)
        allocation.addStretch()

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Дата", "Категория", "Сумма", "Причина", "Комментарий"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addLayout(allocation)
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        with self.session_factory() as session:
            expenses = list(session.scalars(select(FixedExpense).order_by(FixedExpense.expense_date.desc())))
        self.table.setRowCount(len(expenses))
        for row, expense in enumerate(expenses):
            values = [expense.expense_date.isoformat(), expense.category, money(expense.amount), expense.reason, expense.comment]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))

    def add_expense(self) -> None:
        with self.session_factory() as session:
            session.add(
                FixedExpense(
                    expense_date=self.date.date().toPython(),
                    category=self.category.currentText(),
                    amount=self.amount.value(),
                    reason=self.reason.text().strip(),
                    comment=self.comment.text().strip(),
                )
            )
            session.commit()
        self.amount.setValue(0)
        self.reason.clear()
        self.comment.clear()
        self.refresh()
        self.on_changed()

    def allocate(self) -> None:
        method = self.method.currentData()
        if method == "manual":
            QMessageBox.information(self, "ProfitMap", "Ручное распределение выполняется в карточке товара через поле постоянных расходов.")
            return
        with self.session_factory() as session:
            products = list(session.scalars(select(Product)))
            total_expenses = float(session.scalar(select(func.coalesce(func.sum(FixedExpense.amount), 0))) or 0)
            allocations = allocate_fixed_expenses(products, total_expenses, method)
            for product in products:
                product.fixed_cost_allocation = allocations.get(product.id, 0.0)
            session.commit()
        self.on_changed()
        QMessageBox.information(self, "ProfitMap", "Постоянные расходы распределены между товарами")


class AnalyticsPage(QWidget):
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        super().__init__()
        self.session_factory = session_factory
        title = QLabel("Аналитика")
        title.setObjectName("Brand")
        self.metrics = QGridLayout()
        coefficients_title = QLabel("Коэффициенты прибыльности")
        coefficients_title.setObjectName("SectionTitle")
        self.coefficients_table = QTableWidget(0, 4)
        self.coefficients_table.setHorizontalHeaderLabels(["Коэффициент", "Формула расчета", "Расчет по данным ProfitMap", "Итог"])
        self.coefficients_table.verticalHeader().setVisible(False)
        self.coefficients_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.coefficients_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.coefficients_table.setMinimumHeight(185)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Товар", "Выручка", "Прибыль", "ABC", "Прогноз 30 дней"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addWidget(title)
        metric_widget = QWidget()
        metric_widget.setLayout(self.metrics)
        layout.addWidget(metric_widget)
        layout.addWidget(coefficients_title)
        layout.addWidget(self.coefficients_table)
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        clear_layout(self.metrics)
        with self.session_factory() as session:
            products = list(session.scalars(select(Product).order_by(Product.name)))
            total_revenue = float(session.scalar(select(func.coalesce(func.sum(SaleRecord.revenue), 0))) or 0)
            total_fixed = float(session.scalar(select(func.coalesce(func.sum(FixedExpense.amount), 0))) or 0)

        product_rows = []
        total_profit = 0.0
        for product in products:
            result = calculate_for_product(product)
            monthly_profit = result.net_profit_per_unit * product.expected_monthly_sales
            total_profit += monthly_profit
            revenue = product.sale_price * product.expected_monthly_sales
            product_rows.append((product, revenue, monthly_profit))

        cash_flow = total_profit - total_fixed
        margin = (total_profit / total_revenue * 100) if total_revenue else 0
        values = [
            ("Выручка", money(total_revenue)),
            ("Прибыль", money(total_profit)),
            ("Cash Flow", money(cash_flow)),
            ("Маржа", f"{margin:.1f}%"),
            ("Топ товаров", str(len([row for row in product_rows if row[2] > 0]))),
            ("Убыточные", str(len([row for row in product_rows if row[2] <= 0]))),
            ("ABC-анализ", "A/B/C"),
            ("Pareto 80/20", "активен"),
        ]
        for index, (title, value) in enumerate(values):
            label = QLabel(value)
            label.setObjectName("MetricValue")
            self.metrics.addWidget(metric_card(title, label), index // 4, index % 4)

        coefficients = build_profit_coefficients(products, total_fixed)
        self.coefficients_table.setRowCount(len(coefficients))
        for row, coefficient in enumerate(coefficients):
            values = [
                coefficient.name,
                coefficient.formula,
                coefficient.calculation,
                f"{coefficient.percent:.1f}%",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 3:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.coefficients_table.setItem(row, column, item)

        ranked = sorted(product_rows, key=lambda item: item[1], reverse=True)
        total_expected_revenue = sum(row[1] for row in ranked) or 1
        running = 0.0
        self.table.setRowCount(len(ranked))
        with self.session_factory() as session:
            for row, (product, revenue, profit) in enumerate(ranked):
                running += revenue
                share = running / total_expected_revenue
                abc = "A" if share <= 0.8 else "B" if share <= 0.95 else "C"
                quantities = list(
                    session.scalars(
                        select(SaleRecord.quantity)
                        .where(SaleRecord.product_id == product.id)
                        .order_by(SaleRecord.sale_date)
                    )
                )
                forecast = forecast_demand(quantities, 30)
                values = [product.name, money(revenue), money(profit), abc, f"{forecast.forecast_units:.0f} шт."]
                for column, value in enumerate(values):
                    self.table.setItem(row, column, QTableWidgetItem(str(value)))


class AIPage(QWidget):
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        super().__init__()
        self.session_factory = session_factory
        title = QLabel("AI бизнес-консультант")
        title.setObjectName("Brand")
        analyze_button = QPushButton("Анализировать бизнес")
        analyze_button.clicked.connect(self.run_analysis)
        self.output = QTextEdit()
        self.output.setReadOnly(True)

        top = QHBoxLayout()
        top.addWidget(title)
        top.addStretch()
        top.addWidget(analyze_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addLayout(top)
        layout.addWidget(self.output, 1)
        self.run_analysis()

    def run_analysis(self) -> None:
        with self.session_factory() as session:
            products = list(session.scalars(select(Product)))
            total_fixed = float(session.scalar(select(func.coalesce(func.sum(FixedExpense.amount), 0))) or 0)
        self.output.setPlainText(analyze_business(products, total_fixed))


class PhotoDropLabel(QLabel):
    changed = Signal(str)

    def __init__(self) -> None:
        super().__init__("Перетащите фото")
        self.path = ""
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(150)
        self.setAcceptDrops(True)
        self.setStyleSheet("border: 1px dashed #94a3b8; border-radius: 8px;")

    def set_path(self, path: str) -> None:
        self.path = path or ""
        if self.path and Path(self.path).exists():
            pixmap = QPixmap(self.path)
            self.setPixmap(pixmap.scaled(260, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.setPixmap(QPixmap())
            self.setText("Перетащите фото")

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.set_path(path)
            self.changed.emit(path)


def calculate_for_product(product: Product) -> UnitEconomicsResult:
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


def spin_int(minimum: int, maximum: int) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(minimum, maximum)
    spin.setSingleStep(1)
    return spin


def money_spin(maximum: int = 1_000_000) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0, maximum)
    spin.setDecimals(2)
    spin.setSingleStep(1)
    spin.setSuffix(" грн")
    return spin


def money(value: float) -> str:
    return f"{value:,.2f} грн"


def scroll_form(form: QFormLayout) -> QWidget:
    container = QWidget()
    container.setLayout(form)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(container)
    scroll.setFrameShape(QFrame.NoFrame)
    return scroll


def metric_card(title: str, value_label: QLabel) -> QWidget:
    frame = QFrame()
    frame.setFrameShape(QFrame.StyledPanel)
    frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 10)
    caption = QLabel(title)
    caption.setObjectName("SectionTitle")
    layout.addWidget(caption)
    layout.addWidget(value_label)
    return frame


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.deleteLater()
