from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from thermofft.core.streaming import (
    RingBuffer,
    StreamConfig,
    StreamPoint,
    process_tick,
    run_stream,
)


def _sin_points(n: int = 720, step_seconds: int = 60, start: datetime | None = None):
    """720 точек по минуте = 12 часов синтетики (in + out)."""
    base = start or datetime(2025, 1, 1)
    omega = 2 * np.pi / (24 * 3600)
    batches = []
    for i in range(n):
        ts = base + timedelta(seconds=i * step_seconds)
        secs = i * step_seconds
        out_v = 8.0 + 6.0 * np.sin(omega * secs)
        in_v = 22.0 + 2.0 * np.sin(omega * (secs - 7200))
        batches.append([StreamPoint(ts, in_v, "in"), StreamPoint(ts, out_v, "out")])
    return batches


def test_ringbuffer_evicts_old_points():
    rb = RingBuffer(window=timedelta(hours=1))
    base = datetime(2025, 1, 1)
    for i in range(120):
        ts = base + timedelta(minutes=i)
        rb.push(StreamPoint(ts, 20.0 + i * 0.01, "in"))
        rb.push(StreamPoint(ts, 5.0, "out"))
    n_in, n_out = rb.size
    assert n_in <= 62
    assert n_out <= 62


def test_ringbuffer_builds_clean_df():
    rb = RingBuffer(window=timedelta(hours=6))
    for batch in _sin_points(n=360):
        rb.push_many(batch)
    df = rb.as_clean_df(resample_rule="1min")
    assert {"T_in", "T_out", "dT"} <= set(df.columns)
    assert len(df) > 100


def test_process_tick_produces_plots(tmp_path: Path):
    rb = RingBuffer(window=timedelta(hours=12))
    for batch in _sin_points(n=720):
        rb.push_many(batch)
    result = process_tick(
        tick=1, buffer=rb, out_dir=tmp_path,
        resample_rule="1min", top_k=3, render_plots=True,
    )
    assert result.window_points > 100
    assert any(p.name.startswith("live_") for p in result.plot_paths)
    for p in result.plot_paths:
        assert p.exists()
    assert "amplitude" in result.metrics


def test_run_stream_max_ticks_terminates(tmp_path: Path):
    def gen():
        base = datetime(2025, 1, 1)
        i = 0
        while True:
            ts = base + timedelta(minutes=i)
            yield [StreamPoint(ts, 20.0, "in"), StreamPoint(ts, 5.0, "out")]
            i += 1

    cfg = StreamConfig(
        window="1h", resample_rule="1min",
        tick_interval=0.0, max_ticks=3, out_dir=tmp_path,
    )
    ticks: list[int] = []
    run_stream(gen(), cfg, on_tick=lambda r: ticks.append(r.tick))
    assert ticks == [1, 2, 3]
