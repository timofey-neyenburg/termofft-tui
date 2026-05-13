"""Предобработка: resample, интерполяция, разделение in/out, метрики качества."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field


class PreprocessingError(Exception):
    """Ошибки слоя preprocessing."""


class ModeQuality(BaseModel):
    mode: str
    raw_points: int
    resampled_points: int
    duplicates: int
    median_dt_seconds: float | None
    max_gap_minutes: float | None
    interpolated_points: int = Field(default=0)


class QualityReport(BaseModel):
    resample_rule: str
    max_interp_gap: str
    clean_points: int
    modes: list[ModeQuality] = Field(default_factory=list)
    unreliable_intervals: list[dict[str, str]] = Field(default_factory=list)


@dataclass(slots=True)
class PreprocessingResult:
    clean_df: pd.DataFrame
    report: QualityReport


def _series_for_mode(df: pd.DataFrame, mode: str) -> pd.Series:
    sub = df.loc[df["out/in"] == mode, ["noted_date", "temp"]].copy()
    sub = sub.drop_duplicates(subset="noted_date").set_index("noted_date").sort_index()
    return sub["temp"]


def _max_gap_minutes(idx: pd.DatetimeIndex) -> float | None:
    if len(idx) < 2:
        return None
    deltas = np.diff(idx.values).astype("timedelta64[s]").astype(np.int64)
    return float(deltas.max()) / 60.0


def _median_dt_seconds(idx: pd.DatetimeIndex) -> float | None:
    if len(idx) < 2:
        return None
    deltas = np.diff(idx.values).astype("timedelta64[s]").astype(np.int64)
    return float(np.median(deltas))


def _mark_unreliable(series: pd.Series, max_gap: pd.Timedelta) -> list[dict[str, str]]:
    intervals: list[dict[str, str]] = []
    if len(series) < 2:
        return intervals
    diffs = series.index.to_series().diff()
    for i, d in enumerate(diffs):
        if pd.notna(d) and d > max_gap:
            intervals.append(
                {
                    "start": series.index[i - 1].isoformat(),
                    "end": series.index[i].isoformat(),
                    "gap_minutes": f"{d.total_seconds() / 60.0:.1f}",
                }
            )
    return intervals


def clean(
    df: pd.DataFrame,
    resample_rule: str = "15min",
    max_interp_gap: str = "15min",
) -> PreprocessingResult:
    """Resample + интерполяция в пределах max_interp_gap + split in/out.

    Возвращает CleanFrame с колонками ``T_in``, ``T_out``, ``dT = T_in - T_out``.
    """
    if df.empty:
        raise PreprocessingError("Input DataFrame is empty.")

    max_gap_td = pd.to_timedelta(max_interp_gap)
    resample_td = pd.to_timedelta(resample_rule)
    if resample_td.total_seconds() <= 0:
        raise PreprocessingError("resample_rule must be positive.")
    limit_steps = max(1, int(max_gap_td / resample_td))

    modes_quality: list[ModeQuality] = []
    unreliable: list[dict[str, str]] = []
    series_by_mode: dict[str, pd.Series] = {}

    for mode in ("in", "out"):
        raw = _series_for_mode(df, mode)
        if raw.empty:
            raise PreprocessingError(f"No data for mode '{mode}'.")

        unreliable.extend(_mark_unreliable(raw, max_gap_td))

        resampled = raw.resample(resample_rule).mean()
        before_interp_na = int(resampled.isna().sum())
        resampled = resampled.interpolate(limit=limit_steps, limit_direction="both")
        after_interp_na = int(resampled.isna().sum())
        interpolated = max(0, before_interp_na - after_interp_na)
        series_by_mode[mode] = resampled

        modes_quality.append(
            ModeQuality(
                mode=mode,
                raw_points=int(len(raw)),
                resampled_points=int(resampled.notna().sum()),
                duplicates=int(
                    df.loc[df["out/in"] == mode, "noted_date"].duplicated().sum()
                ),
                median_dt_seconds=_median_dt_seconds(raw.index),
                max_gap_minutes=_max_gap_minutes(raw.index),
                interpolated_points=interpolated,
            )
        )

    clean_df = pd.DataFrame(
        {"T_in": series_by_mode["in"], "T_out": series_by_mode["out"]}
    ).dropna(how="any")
    clean_df["dT"] = clean_df["T_in"] - clean_df["T_out"]

    if clean_df.empty:
        raise PreprocessingError(
            "After alignment in/out series have no overlap. Check timestamps."
        )

    report = QualityReport(
        resample_rule=resample_rule,
        max_interp_gap=max_interp_gap,
        clean_points=int(len(clean_df)),
        modes=modes_quality,
        unreliable_intervals=unreliable,
    )
    return PreprocessingResult(clean_df=clean_df, report=report)
