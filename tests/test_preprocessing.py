from __future__ import annotations

import pandas as pd
import pytest

from thermofft.core.ingestion import load_and_validate
from thermofft.core.preprocessing import PreprocessingError, clean


def test_clean_produces_aligned_frame(synth_csv):
    ing = load_and_validate(synth_csv)
    res = clean(ing.df, resample_rule="15min", max_interp_gap="15min")
    assert {"T_in", "T_out", "dT"} <= set(res.clean_df.columns)
    assert res.clean_df.notna().all().all()
    assert res.report.clean_points > 100


def test_clean_marks_long_gaps(tmp_path):
    rows = []
    base = pd.Timestamp("2025-01-01")
    for i in range(120):
        rows.append({"noted_date": base + pd.Timedelta(minutes=i), "temp": 20.0, "out/in": "in"})
        rows.append({"noted_date": base + pd.Timedelta(minutes=i), "temp": 5.0, "out/in": "out"})
    for i in range(120, 240):
        ts = base + pd.Timedelta(hours=4) + pd.Timedelta(minutes=i - 120)
        rows.append({"noted_date": ts, "temp": 20.5, "out/in": "in"})
        rows.append({"noted_date": ts, "temp": 5.5, "out/in": "out"})
    df = pd.DataFrame(rows)
    res = clean(df, resample_rule="15min", max_interp_gap="15min")
    assert len(res.report.unreliable_intervals) >= 1


def test_clean_rejects_empty():
    with pytest.raises(PreprocessingError):
        clean(pd.DataFrame(columns=["noted_date", "temp", "out/in"]))
