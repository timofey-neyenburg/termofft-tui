from __future__ import annotations

from pathlib import Path

from thermofft.config import AppConfig
from thermofft.core.pipeline import run as run_pipeline
from thermofft.storage import db, repository


def test_pipeline_persists_run(tmp_path, synth_csv):
    db_path = tmp_path / "t.db"
    db.init_db(db_path)
    cfg = AppConfig(db_path=db_path, out_dir=tmp_path / "runs", report_formats=["png", "csv"])
    result = run_pipeline(synth_csv, cfg, use_cache=False)
    rows = repository.list_runs(db_path, limit=10)
    assert any(r.run_uid == result.run_uid for r in rows)

    detail = repository.get_run(db_path, result.run_uid)
    assert detail is not None
    assert detail["interpretation"]
    assert Path(detail["artifacts_dir"]).exists()


def test_similar_runs_returns_results(tmp_path, synth_csv):
    db_path = tmp_path / "t.db"
    db.init_db(db_path)
    cfg = AppConfig(db_path=db_path, out_dir=tmp_path / "runs", report_formats=["csv"])
    r1 = run_pipeline(synth_csv, cfg, use_cache=False)
    r2 = run_pipeline(synth_csv, cfg, use_cache=False)
    pairs = repository.similar_runs(db_path, r1.run_uid, top_k=3)
    assert any(p[0].run_uid == r2.run_uid for p in pairs)
