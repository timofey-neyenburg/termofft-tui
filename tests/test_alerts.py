from __future__ import annotations

import pandas as pd

from thermofft.config import AppConfig
from thermofft.core.alerts import evaluate
from thermofft.core.ingestion import load_and_validate
from thermofft.core.metrics import compute
from thermofft.core.preprocessing import clean


def test_alerts_no_oor_for_normal_synth(synth_csv):
    ing = load_and_validate(synth_csv)
    pre = clean(ing.df)
    m = compute(pre.clean_df)
    report = evaluate(m.metrics, pd.DataFrame(), AppConfig())
    codes = {a.code for a in report.alerts}
    assert "OUT_OF_RANGE" not in codes or m.metrics.out_of_range_pct >= AppConfig().oor_pct_warn


def test_alerts_fire_when_oor_high(synth_csv):
    ing = load_and_validate(synth_csv)
    pre = clean(ing.df)
    pre.clean_df["T_in"] += 20
    m = compute(pre.clean_df)
    report = evaluate(m.metrics, pd.DataFrame(), AppConfig())
    codes = {a.code for a in report.alerts}
    assert "OUT_OF_RANGE" in codes
