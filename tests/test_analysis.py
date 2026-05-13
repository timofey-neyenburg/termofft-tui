from __future__ import annotations

import numpy as np
import pandas as pd

from thermofft.core.analysis import spectrum


def _make_sin_df(days: int = 10, step_seconds: int = 600) -> pd.DataFrame:
    n = int(days * 24 * 3600 / step_seconds)
    idx = pd.date_range("2025-01-01", periods=n, freq=f"{step_seconds}s")
    omega = 2 * np.pi / (24 * 3600)
    secs = np.arange(n) * step_seconds
    df = pd.DataFrame(
        {
            "T_in": 20.0 + 1.0 * np.sin(omega * secs),
            "T_out": 5.0 + 5.0 * np.sin(omega * secs),
        },
        index=idx,
    )
    df.index.name = "noted_date"
    df["dT"] = df["T_in"] - df["T_out"]
    return df


def test_periodogram_finds_24h_peak():
    df = _make_sin_df()
    res = spectrum(df, top_k=3)
    assert res.spectrum.cycles_T_in
    top = res.spectrum.cycles_T_in[0]
    assert abs(top.period_hours - 24.0) < 1.0
