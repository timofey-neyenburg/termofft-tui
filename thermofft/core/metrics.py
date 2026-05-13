"""Метрики: амплитуда, затухание, корреляция, лаг, out-of-range, события."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field


def _safe_div(a: float, b: float) -> float:
    if b == 0 or not np.isfinite(b):
        return float("nan")
    return float(a) / float(b)


class AmplitudeBlock(BaseModel):
    amp_in_raw: float
    amp_out_raw: float
    amp_in_robust: float
    amp_out_robust: float
    attenuation_raw: float
    attenuation_robust: float


class CorrelationBlock(BaseModel):
    pearson: float
    lag_steps: int
    lag_hours: float


class AnomalyEvent(BaseModel):
    ts: str
    T_in: float
    rate_per_hour: float
    reason: str


class DailySummaryRow(BaseModel):
    date: str
    T_in_min: float
    T_in_max: float
    T_in_mean: float
    T_out_min: float
    T_out_max: float
    T_out_mean: float
    amp_in: float
    amp_out: float
    attenuation: float


class MetricsResult(BaseModel):
    amplitude: AmplitudeBlock
    correlation: CorrelationBlock
    out_of_range_pct: float
    event_count: int
    events: list[AnomalyEvent] = Field(default_factory=list)
    daily_summary: list[DailySummaryRow] = Field(default_factory=list)


@dataclass(slots=True)
class MetricsBundle:
    metrics: MetricsResult
    daily_df: pd.DataFrame


def _amplitude_pair(series: pd.Series) -> tuple[float, float]:
    raw = float(series.max() - series.min())
    q95, q05 = series.quantile(0.95), series.quantile(0.05)
    return raw, float(q95 - q05)


def _lag_estimate(
    a: pd.Series, b: pd.Series, lag_search_hours: float, step_seconds: float
) -> tuple[int, float]:
    """Cross-correlation: lag at which b best matches a (positive => b leads a)."""
    x = a.to_numpy() - float(a.mean())
    y = b.to_numpy() - float(b.mean())
    n = min(len(x), len(y))
    x, y = x[:n], y[:n]
    if n < 4:
        return 0, 0.0

    full = np.correlate(x, y, mode="full")
    lags = np.arange(-n + 1, n)
    max_lag_steps = int(round(lag_search_hours * 3600.0 / step_seconds))
    max_lag_steps = max(1, min(max_lag_steps, n - 1))
    mask = (lags >= -max_lag_steps) & (lags <= max_lag_steps)
    full_m, lags_m = full[mask], lags[mask]
    if full_m.size == 0:
        return 0, 0.0
    best = int(lags_m[int(np.argmax(full_m))])
    return best, best * step_seconds / 3600.0


def _detect_events(
    clean_df: pd.DataFrame,
    step_seconds: float,
    rate_thr: float,
    oor_low: float,
    oor_high: float,
) -> list[AnomalyEvent]:
    step_hours = step_seconds / 3600.0
    if step_hours == 0:
        return []
    rate = clean_df["T_in"].diff() / step_hours
    rate_mask = rate.abs() >= rate_thr
    oor_mask = (clean_df["T_in"] < oor_low) | (clean_df["T_in"] > oor_high)
    mask = rate_mask | oor_mask

    events: list[AnomalyEvent] = []
    for ts, is_event in mask.items():
        if not is_event:
            continue
        reasons = []
        if bool(rate_mask.loc[ts]):
            reasons.append(f"rate {rate.loc[ts]:.2f}°C/h")
        if bool(oor_mask.loc[ts]):
            reasons.append("out-of-range")
        events.append(
            AnomalyEvent(
                ts=ts.isoformat(),
                T_in=float(clean_df.loc[ts, "T_in"]),
                rate_per_hour=float(rate.loc[ts]) if pd.notna(rate.loc[ts]) else 0.0,
                reason=", ".join(reasons),
            )
        )
    return events


def _daily_summary(clean_df: pd.DataFrame) -> tuple[list[DailySummaryRow], pd.DataFrame]:
    if clean_df.empty:
        return [], pd.DataFrame()
    daily = clean_df.resample("1D").agg(
        T_in_min=("T_in", "min"),
        T_in_max=("T_in", "max"),
        T_in_mean=("T_in", "mean"),
        T_out_min=("T_out", "min"),
        T_out_max=("T_out", "max"),
        T_out_mean=("T_out", "mean"),
    )
    daily["amp_in"] = daily["T_in_max"] - daily["T_in_min"]
    daily["amp_out"] = daily["T_out_max"] - daily["T_out_min"]
    daily["attenuation"] = daily.apply(
        lambda r: _safe_div(r["amp_in"], r["amp_out"]), axis=1
    )

    rows = [
        DailySummaryRow(
            date=idx.date().isoformat(),
            **{c: float(row[c]) if pd.notna(row[c]) else float("nan") for c in (
                "T_in_min", "T_in_max", "T_in_mean",
                "T_out_min", "T_out_max", "T_out_mean",
                "amp_in", "amp_out", "attenuation",
            )},
        )
        for idx, row in daily.iterrows()
    ]
    return rows, daily


def compute(
    clean_df: pd.DataFrame,
    oor_low: float = 18.0,
    oor_high: float = 27.0,
    anomaly_rate_thr_per_hour: float = 1.5,
    lag_search_hours: float = 24.0,
) -> MetricsBundle:
    """Полный набор метрик для очищенного DataFrame."""
    if clean_df.empty:
        raise ValueError("clean_df is empty.")
    if len(clean_df) < 2:
        raise ValueError("Need at least 2 points for metrics.")

    step_seconds = float(
        np.median(np.diff(clean_df.index.values).astype("timedelta64[s]").astype(np.int64))
    )
    if step_seconds <= 0:
        raise ValueError("Non-positive sampling step.")

    amp_in_raw, amp_in_rob = _amplitude_pair(clean_df["T_in"])
    amp_out_raw, amp_out_rob = _amplitude_pair(clean_df["T_out"])

    pearson = float(clean_df["T_out"].corr(clean_df["T_in"]))
    lag_steps, lag_hours = _lag_estimate(
        clean_df["T_in"], clean_df["T_out"], lag_search_hours, step_seconds
    )

    n = len(clean_df)
    oor_mask = (clean_df["T_in"] < oor_low) | (clean_df["T_in"] > oor_high)
    oor_pct = 100.0 * float(oor_mask.sum()) / n

    events = _detect_events(
        clean_df, step_seconds, anomaly_rate_thr_per_hour, oor_low, oor_high
    )
    daily_rows, daily_df = _daily_summary(clean_df)

    metrics = MetricsResult(
        amplitude=AmplitudeBlock(
            amp_in_raw=amp_in_raw,
            amp_out_raw=amp_out_raw,
            amp_in_robust=amp_in_rob,
            amp_out_robust=amp_out_rob,
            attenuation_raw=_safe_div(amp_in_raw, amp_out_raw),
            attenuation_robust=_safe_div(amp_in_rob, amp_out_rob),
        ),
        correlation=CorrelationBlock(
            pearson=pearson, lag_steps=int(lag_steps), lag_hours=float(lag_hours)
        ),
        out_of_range_pct=oor_pct,
        event_count=len(events),
        events=events,
        daily_summary=daily_rows,
    )
    return MetricsBundle(metrics=metrics, daily_df=daily_df)
