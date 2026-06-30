from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout, QWidget


class BreakEvenChart(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.plot = pg.PlotWidget()
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=0.22)
        self.plot.setLabel("left", "Деньги", units="грн")
        self.plot.setLabel("bottom", "Объем продаж", units="шт.")
        self.plot.addLegend(offset=(15, 15))

        self.revenue_curve = self.plot.plot(pen=pg.mkPen("#111827", width=4), name="Валовые поступления")
        self.cost_curve = self.plot.plot(pen=pg.mkPen("#2563eb", width=4), name="Валовые издержки")
        self.fixed_curve = self.plot.plot(pen=pg.mkPen("#8b5cf6", width=3), name="Постоянные издержки")
        self.break_even_marker = pg.ScatterPlotItem(size=14, brush=pg.mkBrush("#ef4444"), pen=pg.mkPen("#991b1b", width=2))
        self.target_marker = pg.ScatterPlotItem(size=13, brush=pg.mkBrush("#22c55e"), pen=pg.mkPen("#166534", width=2))
        self.plot.addItem(self.break_even_marker)
        self.plot.addItem(self.target_marker)

        self.break_even_label = pg.TextItem("", color="#ef4444", anchor=(0.0, 1.2))
        self.target_label = pg.TextItem("", color="#15803d", anchor=(0.0, -0.4))
        self.plot.addItem(self.break_even_label)
        self.plot.addItem(self.target_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot)

    def set_dark(self, enabled: bool) -> None:
        self.plot.setBackground("#151b24" if enabled else "w")
        axis_color = "#cbd5e1" if enabled else "#374151"
        for axis in ("left", "bottom"):
            self.plot.getAxis(axis).setTextPen(axis_color)
            self.plot.getAxis(axis).setPen(axis_color)

    def update_chart(
        self,
        sale_price: float,
        variable_cost: float,
        fixed_costs: float,
        break_even_units: int | None,
        target_units: int | None,
        target_profit: float,
    ) -> None:
        max_units = max(100, int((target_units or break_even_units or 100) * 1.35), 100)
        x = np.linspace(0, max_units, 220)
        revenue = sale_price * x
        total_cost = variable_cost * x + fixed_costs
        fixed = np.full_like(x, fixed_costs)

        self.revenue_curve.setData(x, revenue)
        self.cost_curve.setData(x, total_cost)
        self.fixed_curve.setData(x, fixed)

        if break_even_units:
            be_y = sale_price * break_even_units
            self.break_even_marker.setData([break_even_units], [be_y])
            self.break_even_label.setText(f"Точка безубыточности: {break_even_units} шт.")
            self.break_even_label.setPos(break_even_units, be_y)
        else:
            self.break_even_marker.setData([], [])
            self.break_even_label.setText("Безубыточность недостижима")
            self.break_even_label.setPos(max_units * 0.08, fixed_costs)

        if target_units:
            target_y = sale_price * target_units
            self.target_marker.setData([target_units], [target_y])
            self.target_label.setText(f"Цель {target_profit:,.0f} грн: {target_units} шт.")
            self.target_label.setPos(target_units, target_y)
        else:
            self.target_marker.setData([], [])
            self.target_label.setText("")

        max_y = max(float(revenue.max()), float(total_cost.max()), fixed_costs, 1.0)
        self.plot.setXRange(0, max_units, padding=0.03)
        self.plot.setYRange(0, max_y * 1.1, padding=0.03)
