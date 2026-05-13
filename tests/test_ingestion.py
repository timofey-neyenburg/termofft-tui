from __future__ import annotations

import json

import pandas as pd
import pytest

from thermofft.core.ingestion import ImportError_, load_and_validate


def test_load_csv_ok(synth_csv):
    res = load_and_validate(synth_csv)
    assert res.report.accepted_rows > 0
    assert set(res.df["out/in"].unique()) == {"in", "out"}


def test_load_missing_columns(tmp_path):
    bad = tmp_path / "bad.csv"
    pd.DataFrame({"ts": [1, 2], "v": [3, 4]}).to_csv(bad, index=False)
    with pytest.raises(ImportError_):
        load_and_validate(bad)


def test_load_unknown_extension(tmp_path):
    bad = tmp_path / "data.xyz"
    bad.write_text("noted_date,temp,out/in\n", encoding="utf-8")
    with pytest.raises(ImportError_):
        load_and_validate(bad)


def test_load_json_records(tmp_path):
    p = tmp_path / "data.json"
    records = [
        {"noted_date": "2025-01-01T00:00:00", "temp": 20.0, "out/in": "in"},
        {"noted_date": "2025-01-01T00:00:00", "temp": 5.0, "out/in": "out"},
        {"noted_date": "2025-01-01T00:01:00", "temp": 20.1, "out/in": "in"},
        {"noted_date": "2025-01-01T00:01:00", "temp": 5.1, "out/in": "out"},
    ]
    p.write_text(json.dumps(records), encoding="utf-8")
    res = load_and_validate(p)
    assert res.report.accepted_rows == 4


def test_load_rejects_garbage_rows(tmp_path):
    p = tmp_path / "mix.csv"
    pd.DataFrame({
        "noted_date": ["junk", "also-bad", ""],
        "temp": ["abc", "xx", ""],
        "out/in": ["in", "in", "in"],
    }).to_csv(p, index=False)
    with pytest.raises(ImportError_):
        load_and_validate(p)


def test_load_drops_invalid_rows_but_keeps_valid(tmp_path):
    p = tmp_path / "mix.csv"
    pd.DataFrame({
        "noted_date": [
            "2025-01-01T00:00:00", "junk", "2025-01-01T00:01:00",
            "2025-01-01T00:00:00", "2025-01-01T00:01:00",
        ],
        "temp": ["20.0", "21.0", "abc", "5.0", "5.1"],
        "out/in": ["in", "in", "in", "out", "out"],
    }).to_csv(p, index=False)
    res = load_and_validate(p)
    assert res.report.accepted_rows == 3
    assert res.report.rejected_rows == 2
    assert res.report.warnings
