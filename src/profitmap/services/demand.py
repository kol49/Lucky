from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(slots=True)
class DemandForecast:
    horizon: str
    forecast_units: float
    method: str


def aggregate_sales(records: list[dict], frequency: str) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=["period", "quantity", "revenue"])
    frame = pd.DataFrame(records)
    frame["sale_date"] = pd.to_datetime(frame["sale_date"])
    grouped = (
        frame.set_index("sale_date")
        .resample(frequency)
        .agg({"quantity": "sum", "revenue": "sum"})
        .reset_index()
        .rename(columns={"sale_date": "period"})
    )
    return grouped


def forecast_demand(daily_quantities: list[int], horizon_days: int) -> DemandForecast:
    if not daily_quantities:
        return DemandForecast(horizon=f"{horizon_days} days", forecast_units=0.0, method="no history")

    series = pd.Series(daily_quantities, dtype=float)
    window = min(14, len(series))
    moving_average = float(series.tail(window).mean())

    if len(series) >= 14:
        x = np.arange(len(series))
        slope, intercept = np.polyfit(x, series.to_numpy(), 1)
        future_x = np.arange(len(series), len(series) + horizon_days)
        regression_total = float(np.maximum(slope * future_x + intercept, 0).sum())
        moving_total = moving_average * horizon_days
        forecast = (regression_total * 0.55) + (moving_total * 0.45)
        method = "moving average + linear regression"
    else:
        forecast = moving_average * horizon_days
        method = "moving average"

    return DemandForecast(
        horizon=f"{horizon_days} days",
        forecast_units=round(forecast, 1),
        method=method,
    )
