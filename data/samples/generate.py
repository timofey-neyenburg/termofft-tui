"""Генератор синтетического температурного датасета для smoke-теста.

Использование:
    python data/samples/generate.py --out data/samples/sample.csv --days 7 --step 60
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def synth(
    days: int = 7,
    step_seconds: int = 60,
    seed: int = 42,
    base_in: float = 22.0,
    base_out: float = 8.0,
    out_amp: float = 6.0,
    in_amp: float = 2.0,
    noise_in: float = 0.15,
    noise_out: float = 0.4,
    lag_hours: float = 2.0,
) -> pd.DataFrame:
    """Сгенерировать ряд in/out с суточным гармоническим паттерном и шумом."""
    rng = np.random.default_rng(seed)
    n = int(days * 24 * 3600 / step_seconds)
    t = pd.date_range("2025-01-01", periods=n, freq=f"{step_seconds}s")
    omega = 2 * np.pi / (24 * 3600)
    secs = np.arange(n) * step_seconds

    out_signal = base_out + out_amp * np.sin(omega * secs) + rng.normal(0, noise_out, n)
    in_signal = (
        base_in
        + in_amp * np.sin(omega * (secs - lag_hours * 3600))
        + rng.normal(0, noise_in, n)
    )
    if days >= 3:
        spike_idx = n // 2
        in_signal[spike_idx : spike_idx + 30] += 5.0

    df_in = pd.DataFrame({"noted_date": t, "temp": in_signal, "out/in": "in"})
    df_out = pd.DataFrame({"noted_date": t, "temp": out_signal, "out/in": "out"})
    return pd.concat([df_in, df_out], ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("data/samples/sample.csv"))
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--step", type=int, default=60, help="step seconds")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    df = synth(days=args.days, step_seconds=args.step, seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False, date_format="%Y-%m-%dT%H:%M:%S")
    print(f"wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
