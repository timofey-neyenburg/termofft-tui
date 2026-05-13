"""Правила-оповещения по метрикам и прогнозу."""
from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

from thermofft.config import AppConfig
from thermofft.core.metrics import MetricsResult


Severity = Literal["info", "warning", "critical"]


class Alert(BaseModel):
    code: str
    severity: Severity
    message: str
    value: float | None = None
    threshold: float | None = None


class AlertReport(BaseModel):
    alerts: list[Alert] = Field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.alerts)

    @property
    def max_severity(self) -> Severity:
        order = {"info": 0, "warning": 1, "critical": 2}
        if not self.alerts:
            return "info"
        return max((a.severity for a in self.alerts), key=lambda s: order[s])


def evaluate(
    metrics: MetricsResult,
    forecast_df: pd.DataFrame,
    cfg: AppConfig,
) -> AlertReport:
    """Сравнить метрики/прогноз с порогами из config и собрать список Alert."""
    alerts: list[Alert] = []

    att = metrics.amplitude.attenuation_robust
    if pd.notna(att):
        if att >= cfg.attenuation_warn:
            alerts.append(Alert(
                code="ATTENUATION_WEAK",
                severity="warning",
                message=(
                    f"Слабое затухание: внутренние колебания ~{att:.2f}× от внешних. "
                    "Помещение слабо изолировано."
                ),
                value=float(att), threshold=cfg.attenuation_warn,
            ))
        elif att <= cfg.attenuation_strong:
            alerts.append(Alert(
                code="ATTENUATION_STRONG",
                severity="info",
                message=f"Сильное затухание ({att:.2f}). Внутренний режим стабилен.",
                value=float(att), threshold=cfg.attenuation_strong,
            ))

    if metrics.out_of_range_pct >= cfg.oor_pct_warn:
        alerts.append(Alert(
            code="OUT_OF_RANGE",
            severity="warning" if metrics.out_of_range_pct < 30 else "critical",
            message=(
                f"{metrics.out_of_range_pct:.1f}% точек T_in вне коридора "
                f"[{cfg.oor_low};{cfg.oor_high}] °C."
            ),
            value=metrics.out_of_range_pct, threshold=cfg.oor_pct_warn,
        ))

    if abs(metrics.correlation.lag_hours) >= cfg.lag_hours_warn:
        alerts.append(Alert(
            code="LARGE_LAG",
            severity="warning",
            message=(
                f"Большой временной сдвиг между внешней и внутренней температурой: "
                f"{metrics.correlation.lag_hours:.1f} ч."
            ),
            value=float(metrics.correlation.lag_hours),
            threshold=cfg.lag_hours_warn,
        ))

    if metrics.event_count >= cfg.event_count_warn:
        alerts.append(Alert(
            code="EVENT_COUNT",
            severity="warning",
            message=(
                f"Зафиксировано {metrics.event_count} событий резкого изменения "
                f"или OOR (порог {cfg.event_count_warn})."
            ),
            value=float(metrics.event_count), threshold=float(cfg.event_count_warn),
        ))

    if not forecast_df.empty:
        future_oor = (
            (forecast_df["forecast_T_in"] < cfg.oor_low)
            | (forecast_df["forecast_T_in"] > cfg.oor_high)
        ).sum()
        if future_oor > 0:
            alerts.append(Alert(
                code="FORECAST_OOR",
                severity="warning",
                message=(
                    f"Прогноз предсказывает {int(future_oor)} точек вне коридора "
                    f"[{cfg.oor_low};{cfg.oor_high}] °C на горизонте."
                ),
                value=float(future_oor), threshold=0.0,
            ))

    return AlertReport(alerts=alerts)
