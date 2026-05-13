"""Спектральный анализ временных рядов температуры (FFT/periodogram)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from scipy.signal import find_peaks, periodogram


class SpectralCycle(BaseModel):
    rank: int
    frequency_hz: float
    period_hours: float
    power: float


class SpectralResult(BaseModel):
    fs_hz: float
    cycles_T_in: list[SpectralCycle] = Field(default_factory=list)
    cycles_T_out: list[SpectralCycle] = Field(default_factory=list)


@dataclass(slots=True)
class SpectralAnalysisResult:
    spectrum: SpectralResult
    psd_T_in: tuple[np.ndarray, np.ndarray]
    psd_T_out: tuple[np.ndarray, np.ndarray]


def _detect_fs_hz(index: pd.DatetimeIndex) -> float:
    if len(index) < 2:
        raise ValueError("Need at least 2 timestamps to detect sampling frequency.")
    dt_seconds = np.median(
        np.diff(index.values).astype("timedelta64[s]").astype(np.int64)
    )
    if dt_seconds <= 0:
        raise ValueError("Non-positive sampling interval detected.")
    return 1.0 / float(dt_seconds)


def _top_cycles(
    freqs: np.ndarray, psd: np.ndarray, top_k: int
) -> list[SpectralCycle]:
    pos = freqs > 0
    freqs = freqs[pos]
    psd = psd[pos]
    if freqs.size == 0:
        return []

    peaks, _ = find_peaks(psd)
    if peaks.size == 0:
        return []

    order = np.argsort(psd[peaks])[::-1]
    top = peaks[order[:top_k]]
    cycles: list[SpectralCycle] = []
    for rank, idx in enumerate(top, start=1):
        f = float(freqs[idx])
        cycles.append(
            SpectralCycle(
                rank=rank,
                frequency_hz=f,
                period_hours=(1.0 / f) / 3600.0,
                power=float(psd[idx]),
            )
        )
    return cycles


def spectrum(
    clean_df: pd.DataFrame, top_k: int = 5
) -> SpectralAnalysisResult:
    """Periodogram для T_in и T_out + top-K циклов по мощности."""
    if clean_df.empty:
        raise ValueError("clean_df is empty.")
    fs = _detect_fs_hz(clean_df.index)

    f_in, p_in = periodogram(clean_df["T_in"].to_numpy(), fs=fs)
    f_out, p_out = periodogram(clean_df["T_out"].to_numpy(), fs=fs)

    return SpectralAnalysisResult(
        spectrum=SpectralResult(
            fs_hz=fs,
            cycles_T_in=_top_cycles(f_in, p_in, top_k),
            cycles_T_out=_top_cycles(f_out, p_out, top_k),
        ),
        psd_T_in=(f_in, p_in),
        psd_T_out=(f_out, p_out),
    )
