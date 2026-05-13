"""Реал-тайм обработка: RingBuffer + скользящее окно FFT/метрики/график на каждом тике.

Источники данных:
- ``simulate`` — генератор синтетических точек (sin(24h) + шум, лаг in vs out)
- ``tail``    — наблюдение за дописывающимся CSV-файлом
- ``callable`` — произвольный python-callable, возвращающий list[StreamPoint]
"""
from __future__ import annotations

import csv
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterator

import numpy as np
import pandas as pd

from thermofft.core import analysis, metrics as metrics_mod
from thermofft.reporting import plots as plots_mod

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StreamPoint:
    ts: datetime
    temp: float
    mode: str  # "in" | "out"


@dataclass(slots=True)
class TickResult:
    tick: int
    timestamp: datetime
    window_points: int
    plot_paths: list[Path]
    metrics: dict
    spectrum: dict
    elapsed_seconds: float


class RingBuffer:
    """Скользящее окно точек по времени."""

    def __init__(self, window: timedelta) -> None:
        self.window = window
        self._in: deque[tuple[datetime, float]] = deque()
        self._out: deque[tuple[datetime, float]] = deque()

    def push(self, p: StreamPoint) -> None:
        target = self._in if p.mode == "in" else self._out
        target.append((p.ts, p.temp))
        self._evict(p.ts)

    def push_many(self, points: list[StreamPoint]) -> None:
        if not points:
            return
        for p in points:
            target = self._in if p.mode == "in" else self._out
            target.append((p.ts, p.temp))
        latest = max(p.ts for p in points)
        self._evict(latest)

    def _evict(self, latest: datetime) -> None:
        cutoff = latest - self.window
        while self._in and self._in[0][0] < cutoff:
            self._in.popleft()
        while self._out and self._out[0][0] < cutoff:
            self._out.popleft()

    def as_clean_df(self, resample_rule: str = "1min") -> pd.DataFrame:
        """Собрать выровненный DataFrame для скользящего окна (in/out merge)."""
        def _to_series(buf: deque) -> pd.Series:
            if not buf:
                return pd.Series(dtype=float)
            idx, vals = zip(*buf)
            s = pd.Series(vals, index=pd.DatetimeIndex(idx))
            s = s[~s.index.duplicated(keep="last")].sort_index()
            return s.resample(resample_rule).mean().interpolate(limit=2, limit_direction="both")

        s_in = _to_series(self._in)
        s_out = _to_series(self._out)
        if s_in.empty or s_out.empty:
            return pd.DataFrame(columns=["T_in", "T_out", "dT"])
        df = pd.DataFrame({"T_in": s_in, "T_out": s_out}).dropna(how="any")
        if df.empty:
            return df
        df["dT"] = df["T_in"] - df["T_out"]
        df.index.name = "noted_date"
        return df

    @property
    def size(self) -> tuple[int, int]:
        return len(self._in), len(self._out)


def simulate_source(
    step_seconds: int = 60,
    seed: int = 42,
    *,
    base_in: float = 22.0,
    base_out: float = 8.0,
    out_amp: float = 6.0,
    in_amp: float = 2.0,
    noise_in: float = 0.2,
    noise_out: float = 0.4,
    lag_hours: float = 2.0,
    speedup: float = 60.0,
) -> Iterator[list[StreamPoint]]:
    """Бесконечный генератор пар (in, out) со sin(24h) и шумом.

    ``speedup`` — во сколько раз ускорить «эмулируемое» время относительно
    реального: speedup=60 значит "за 1 секунду — 60 секунд внутреннего времени".
    """
    rng = np.random.default_rng(seed)
    omega = 2 * np.pi / (24 * 3600)
    sim_t = datetime.utcnow().replace(microsecond=0)
    secs = 0
    while True:
        out_v = (
            base_out + out_amp * np.sin(omega * secs)
            + float(rng.normal(0, noise_out))
        )
        in_v = (
            base_in + in_amp * np.sin(omega * (secs - lag_hours * 3600))
            + float(rng.normal(0, noise_in))
        )
        yield [
            StreamPoint(sim_t, in_v, "in"),
            StreamPoint(sim_t, out_v, "out"),
        ]
        sim_t = sim_t + timedelta(seconds=step_seconds)
        secs += step_seconds
        time.sleep(step_seconds / max(speedup, 1e-6))


def tail_csv_source(
    path: Path,
    poll_interval: float = 1.0,
    from_start: bool = True,
) -> Iterator[list[StreamPoint]]:
    """Yield-нуть новые строки CSV по мере их появления.

    Колонки: noted_date, temp, out/in (как в обычном ingestion).
    """
    last_size = 0
    header_seen = False
    columns: list[str] = []
    while True:
        if not path.exists():
            time.sleep(poll_interval)
            continue
        current_size = path.stat().st_size
        if current_size < last_size:
            last_size = 0
            header_seen = False
        if current_size == last_size:
            time.sleep(poll_interval)
            continue

        with path.open("r", encoding="utf-8", newline="") as f:
            f.seek(last_size if header_seen or not from_start else 0)
            reader = csv.reader(f)
            batch: list[StreamPoint] = []
            for row in reader:
                if not header_seen:
                    columns = [c.strip() for c in row]
                    header_seen = True
                    continue
                rec = dict(zip(columns, row))
                try:
                    ts = pd.to_datetime(rec["noted_date"], dayfirst=True)
                    temp = float(rec["temp"])
                    mode = rec["out/in"].strip().lower()
                except Exception:  # noqa: BLE001
                    continue
                if mode not in ("in", "out"):
                    continue
                batch.append(StreamPoint(ts.to_pydatetime(), temp, mode))
            last_size = f.tell()
            if batch:
                yield batch
        time.sleep(poll_interval)


def _render_live_plot(
    df: pd.DataFrame,
    spec: analysis.SpectralAnalysisResult | None,
    out_dir: Path,
) -> list[Path]:
    """Перерисовать timeseries + spectrum, перезаписывая ``live_*.png``."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    if not df.empty:
        fig, ax = plt.subplots(figsize=(12, 5), dpi=150)
        ax.plot(df.index, df["T_out"], label="T_out", linewidth=1.2)
        ax.plot(df.index, df["T_in"], label="T_in", linewidth=1.2)
        ax.set_title("ThermoFFT — live timeseries")
        ax.set_xlabel("Время")
        ax.set_ylabel("°C")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.autofmt_xdate()
        p = out_dir / "live_timeseries.png"
        fig.savefig(p, dpi=plots_mod.DPI, bbox_inches="tight")
        plt.close(fig)
        paths.append(p)

    if spec is not None:
        fig, ax = plt.subplots(figsize=(12, 5), dpi=150)
        for label, (freqs, psd), color in (
            ("T_in", spec.psd_T_in, "tab:orange"),
            ("T_out", spec.psd_T_out, "tab:blue"),
        ):
            mask = freqs > 0
            if not mask.any():
                continue
            periods_h = (1.0 / freqs[mask]) / 3600.0
            ax.semilogy(periods_h, psd[mask], label=label, linewidth=1.0, color=color)
        ax.set_title("ThermoFFT — live spectrum")
        ax.set_xlabel("Период, ч")
        ax.set_ylabel("PSD")
        ax.set_xlim(left=0, right=72)
        ax.legend()
        ax.grid(True, which="both", alpha=0.3)
        p = out_dir / "live_spectrum.png"
        fig.savefig(p, dpi=plots_mod.DPI, bbox_inches="tight")
        plt.close(fig)
        paths.append(p)

    return paths


def process_tick(
    tick: int,
    buffer: RingBuffer,
    out_dir: Path,
    resample_rule: str,
    top_k: int,
    *,
    render_plots: bool = True,
    oor_low: float = 18.0,
    oor_high: float = 27.0,
) -> TickResult:
    """Один тик: собрать окно → spectrum → metrics → перерисовать графики."""
    t0 = time.perf_counter()
    df = buffer.as_clean_df(resample_rule=resample_rule)
    plot_paths: list[Path] = []
    metrics_dict: dict = {}
    spectrum_dict: dict = {}
    spec_result: analysis.SpectralAnalysisResult | None = None

    if len(df) >= 8:
        try:
            spec_result = analysis.spectrum(df, top_k=top_k)
            spectrum_dict = spec_result.spectrum.model_dump()
        except Exception as exc:  # noqa: BLE001
            logger.debug("spectrum skipped: %s", exc)

        try:
            mb = metrics_mod.compute(
                df, oor_low=oor_low, oor_high=oor_high,
            )
            metrics_dict = mb.metrics.model_dump()
        except Exception as exc:  # noqa: BLE001
            logger.debug("metrics skipped: %s", exc)

    if render_plots:
        plot_paths = _render_live_plot(df, spec_result, out_dir)

    return TickResult(
        tick=tick,
        timestamp=datetime.utcnow(),
        window_points=len(df),
        plot_paths=plot_paths,
        metrics=metrics_dict,
        spectrum=spectrum_dict,
        elapsed_seconds=time.perf_counter() - t0,
    )


@dataclass(slots=True)
class StreamConfig:
    window: str = "24h"
    resample_rule: str = "1min"
    tick_interval: float = 1.0
    top_k: int = 5
    out_dir: Path = field(default_factory=lambda: Path("runs/live"))
    max_ticks: int | None = None
    oor_low: float = 18.0
    oor_high: float = 27.0


def run_stream(
    source: Iterator[list[StreamPoint]],
    cfg: StreamConfig,
    on_tick: Callable[[TickResult], None] | None = None,
    stop_flag: Callable[[], bool] | None = None,
) -> None:
    """Главный цикл реал-тайм обработки.

    ``stop_flag`` — функция, возвращающая True для остановки извне (TUI/SIGINT).
    """
    buffer = RingBuffer(window=pd.to_timedelta(cfg.window).to_pytimedelta())
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    tick = 0
    last_tick_at = 0.0
    stop = stop_flag or (lambda: False)

    for batch in source:
        if stop():
            return
        buffer.push_many(batch)
        now = time.perf_counter()
        if now - last_tick_at >= cfg.tick_interval:
            tick += 1
            result = process_tick(
                tick, buffer, cfg.out_dir, cfg.resample_rule, cfg.top_k,
                oor_low=cfg.oor_low, oor_high=cfg.oor_high,
            )
            if on_tick is not None:
                on_tick(result)
            last_tick_at = now
            if cfg.max_ticks is not None and tick >= cfg.max_ticks:
                return
