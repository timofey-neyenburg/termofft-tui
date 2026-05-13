"""Perf-gate из ТЗ: 100k точек ≤ 10с (без репортинга — чистая аналитика)."""
from __future__ import annotations

import time

import pytest

from thermofft.config import AppConfig
from thermofft.core.analysis import spectrum
from thermofft.core.forecasting import forecast
from thermofft.core.ingestion import load_and_validate
from thermofft.core.metrics import compute
from thermofft.core.preprocessing import clean


@pytest.mark.perf
def test_100k_points_under_10_seconds(big_synth_csv):
    cfg = AppConfig(forecast_model="naive")
    t0 = time.perf_counter()
    ing = load_and_validate(big_synth_csv)
    pre = clean(ing.df, resample_rule=cfg.resample_rule, max_interp_gap=cfg.max_interp_gap)
    _ = spectrum(pre.clean_df)
    _ = compute(pre.clean_df)
    _ = forecast(pre.clean_df, model="naive", horizon="24h")
    elapsed = time.perf_counter() - t0
    assert elapsed < 10.0, f"Pipeline core took {elapsed:.2f}s (>10s)"
