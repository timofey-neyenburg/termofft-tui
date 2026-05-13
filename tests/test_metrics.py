from __future__ import annotations

import numpy as np
import pandas as pd

from thermofft.core.metrics import compute


def _shifted_sin(days: int = 5, step_seconds: int = 600, lag_hours: float = 3.0):
    n = int(days * 24 * 3600 / step_seconds)
    idx = pd.date_range("2025-01-01", periods=n, freq=f"{step_seconds}s")
    omega = 2 * np.pi / (24 * 3600)
    secs = np.arange(n) * step_seconds
    df = pd.DataFrame(
        {
            "T_in": 22.0 + 1.5 * np.sin(omega * (secs - lag_hours * 3600)),
            "T_out": 8.0 + 6.0 * np.sin(omega * secs),
        },
        index=idx,
    )
    df.index.name = "noted_date"
    df["dT"] = df["T_in"] - df["T_out"]
    return df


def test_attenuation_below_one():
    df = _shifted_sin()
    res = compute(df)
    assert 0 < res.metrics.amplitude.attenuation_robust < 1.0


def test_lag_close_to_expected():
    df = _shifted_sin(lag_hours=3.0)
    res = compute(df)
    assert abs(abs(res.metrics.correlation.lag_hours) - 3.0) < 1.0


def test_oor_pct_triggers():
    df = _shifted_sin()
    df["T_in"] = 35.0
    res = compute(df, oor_low=18.0, oor_high=27.0)
    assert res.metrics.out_of_range_pct > 50
