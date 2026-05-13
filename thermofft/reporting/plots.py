"""Графики matplotlib (300 dpi): timeseries, spectrum, heatmap."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from thermofft.core.analysis import SpectralAnalysisResult  # noqa: E402

DPI = 300


def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def plot_timeseries(
    clean_df: pd.DataFrame,
    out_dir: Path,
    forecast_df: pd.DataFrame | None = None,
) -> Path:
    """Линейный график T_in / T_out (+ опционально прогноз)."""
    _ensure_dir(out_dir)
    fig, ax = plt.subplots(figsize=(12, 6), dpi=DPI)
    ax.plot(clean_df.index, clean_df["T_out"], label="T_out", linewidth=1.2)
    ax.plot(clean_df.index, clean_df["T_in"], label="T_in", linewidth=1.2)
    if forecast_df is not None and not forecast_df.empty:
        ax.plot(
            forecast_df.index, forecast_df["forecast_T_in"],
            label="forecast T_in", linestyle="--", linewidth=1.2,
        )
    ax.set_title("Температурный ряд")
    ax.set_xlabel("Время")
    ax.set_ylabel("°C")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    path = out_dir / "timeseries.png"
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_spectrum(spec: SpectralAnalysisResult, out_dir: Path) -> Path:
    """semilogy PSD для T_in и T_out по оси «период (часы)»."""
    _ensure_dir(out_dir)
    fig, ax = plt.subplots(figsize=(12, 6), dpi=DPI)

    for label, (freqs, psd), color in (
        ("T_in", spec.psd_T_in, "tab:orange"),
        ("T_out", spec.psd_T_out, "tab:blue"),
    ):
        mask = freqs > 0
        periods_h = (1.0 / freqs[mask]) / 3600.0
        ax.semilogy(periods_h, psd[mask], label=label, linewidth=1.0, color=color)

    ax.set_title("Спектральная плотность")
    ax.set_xlabel("Период, ч")
    ax.set_ylabel("PSD")
    ax.set_xlim(left=0, right=72)
    ax.legend()
    ax.grid(True, which="both", alpha=0.3)
    path = out_dir / "spectrum.png"
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_heatmap(clean_df: pd.DataFrame, out_dir: Path) -> Path:
    """Тепловая карта: строки = дни, колонки = час суток, значения = mean T_in."""
    _ensure_dir(out_dir)
    df = clean_df.copy()
    df["date"] = df.index.date
    df["hour"] = df.index.hour
    pivot = df.pivot_table(index="date", columns="hour", values="T_in", aggfunc="mean")

    fig, ax = plt.subplots(figsize=(12, 6), dpi=DPI)
    if pivot.empty:
        ax.set_title("Нет данных для тепловой карты")
    else:
        im = ax.imshow(
            pivot.to_numpy(),
            aspect="auto",
            cmap="coolwarm",
            interpolation="nearest",
        )
        ax.set_yticks(np.arange(len(pivot.index)))
        ax.set_yticklabels([d.isoformat() for d in pivot.index])
        ax.set_xticks(np.arange(0, 24, 2))
        ax.set_xticklabels([str(h) for h in range(0, 24, 2)])
        ax.set_xlabel("Час суток")
        ax.set_ylabel("Дата")
        ax.set_title("Тепловая карта T_in")
        fig.colorbar(im, ax=ax, label="°C")
    path = out_dir / "heatmap.png"
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return path
