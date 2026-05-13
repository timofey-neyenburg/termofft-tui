"""Прогнозирование температуры: ExponentialSmoothing / SARIMA / naive."""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ForecastResult(BaseModel):
    model: str
    horizon_steps: int
    step_seconds: float


@dataclass(slots=True)
class ForecastBundle:
    forecast_df: pd.DataFrame
    result: ForecastResult


def _horizon_steps(horizon: str, step_seconds: float) -> int:
    horizon_td = pd.to_timedelta(horizon)
    return max(1, int(horizon_td.total_seconds() / step_seconds))


def _seasonal_periods(step_seconds: float) -> int:
    daily = int(round(86400.0 / step_seconds))
    return max(2, daily)


def _future_index(last_ts: pd.Timestamp, step_seconds: float, steps: int) -> pd.DatetimeIndex:
    return pd.date_range(
        start=last_ts + pd.to_timedelta(step_seconds, unit="s"),
        periods=steps,
        freq=pd.to_timedelta(step_seconds, unit="s"),
    )


def _naive(series: pd.Series, steps: int) -> np.ndarray:
    if len(series) == 0:
        raise ValueError("Empty series for naive forecast.")
    seasonal_period = min(steps, len(series))
    tail = series.tail(seasonal_period).to_numpy()
    reps = int(np.ceil(steps / seasonal_period))
    return np.tile(tail, reps)[:steps]


def _expsmooth(series: pd.Series, steps: int, seasonal_periods: int) -> np.ndarray:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = ExponentialSmoothing(
            series.to_numpy(),
            trend=None,
            seasonal="add",
            seasonal_periods=seasonal_periods,
            initialization_method="estimated",
        )
        fitted = model.fit(optimized=True)
        return np.asarray(fitted.forecast(steps))


def _sarima(series: pd.Series, steps: int, seasonal_periods: int) -> np.ndarray:
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = SARIMAX(
            series.to_numpy(),
            order=(1, 0, 1),
            seasonal_order=(1, 0, 1, seasonal_periods),
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        fitted = model.fit(disp=False)
        return np.asarray(fitted.forecast(steps))


def forecast(
    clean_df: pd.DataFrame,
    model: str = "expsmooth",
    horizon: str = "24h",
) -> ForecastBundle:
    """Прогноз T_in на заданный горизонт.

    Падение модели приводит к fallback на naive (логируется).
    """
    if clean_df.empty:
        raise ValueError("clean_df is empty.")

    step_seconds = float(
        np.median(np.diff(clean_df.index.values).astype("timedelta64[s]").astype(np.int64))
    )
    steps = _horizon_steps(horizon, step_seconds)
    series = clean_df["T_in"].astype(float)
    seasonal = _seasonal_periods(step_seconds)
    chosen = model

    try:
        if model == "expsmooth" and len(series) >= 2 * seasonal:
            values = _expsmooth(series, steps, seasonal)
        elif model == "sarima" and len(series) >= 2 * seasonal:
            values = _sarima(series, steps, seasonal)
        else:
            if model not in ("naive",):
                logger.warning(
                    "Series too short for %s (need >= %d points, have %d). Falling back to naive.",
                    model, 2 * seasonal, len(series),
                )
            chosen = "naive"
            values = _naive(series, steps)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Model %s failed (%s). Falling back to naive.", model, exc)
        chosen = "naive"
        values = _naive(series, steps)

    idx = _future_index(clean_df.index[-1], step_seconds, steps)
    forecast_df = pd.DataFrame({"forecast_T_in": values}, index=idx)
    forecast_df.index.name = "noted_date"

    return ForecastBundle(
        forecast_df=forecast_df,
        result=ForecastResult(
            model=chosen, horizon_steps=steps, step_seconds=step_seconds
        ),
    )
