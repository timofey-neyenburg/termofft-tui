"""End-to-end orchestrator: ingestion → preprocessing → spectrum → metrics → forecast → alerts → report → save."""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from thermofft.config import AppConfig
from thermofft.core import (
    alerts as alerts_mod,
    analysis,
    forecasting,
    ingestion,
    interpretation,
    metrics as metrics_mod,
    preprocessing,
)
from thermofft.reporting import exporters, meta as meta_mod, plots
from thermofft.storage import cache as cache_mod, db, repository

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StageRecord:
    stage: str
    started_at: datetime
    duration_seconds: float
    status: str
    message: str = ""


@dataclass(slots=True)
class PipelineResult:
    run_uid: str
    out_dir: Path
    duration_seconds: float
    interpretation: str
    metrics: dict
    spectrum: dict
    quality: dict
    forecast: dict
    alerts: list[dict]
    artifacts: list[Path]
    stages: list[StageRecord] = field(default_factory=list)


ProgressFn = Callable[[str, str], None]  # (stage, status) -> None


def _noop_progress(_stage: str, _status: str) -> None:
    pass


def _stage(records: list[StageRecord], name: str, progress: ProgressFn):
    progress(name, "start")

    class _Ctx:
        def __enter__(self):
            self.t0 = time.perf_counter()
            self.started = datetime.utcnow()
            return self

        def __exit__(self, exc_type, exc, _tb):
            dur = time.perf_counter() - self.t0
            if exc is None:
                records.append(StageRecord(name, self.started, dur, "ok"))
                progress(name, "ok")
            else:
                msg = f"{type(exc).__name__}: {exc}"
                records.append(StageRecord(name, self.started, dur, "error", msg))
                progress(name, "error")
            return False

    return _Ctx()


def run(
    input_path: str | Path,
    config: AppConfig,
    progress: ProgressFn | None = None,
    use_cache: bool = True,
) -> PipelineResult:
    """Полный прогон. Возвращает PipelineResult + пишет в SQLite/файлы."""
    progress = progress or _noop_progress
    t_start = time.perf_counter()
    run_uid = uuid.uuid4().hex[:16]
    stages: list[StageRecord] = []

    np.random.seed(config.random_seed)

    out_dir = config.out_dir / f"{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}_{run_uid}"
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg_dict = json.loads(config.model_dump_json())

    db.init_db(config.db_path)

    cache_key = cache_mod.make_cache_key(input_path, cfg_dict)
    if use_cache:
        cached = cache_mod.get_cached(config.db_path, cache_key)
        if cached is not None:
            logger.info("Cache hit for %s", cache_key[:12])
            cached["from_cache"] = True
            return PipelineResult(
                run_uid=cached.get("run_uid", run_uid),
                out_dir=Path(cached.get("artifacts_dir", out_dir)),
                duration_seconds=cached.get("duration_seconds", 0.0),
                interpretation=cached.get("interpretation", ""),
                metrics=cached.get("metrics", {}),
                spectrum=cached.get("spectrum", {}),
                quality=cached.get("quality", {}),
                forecast=cached.get("forecast", {}),
                alerts=cached.get("alerts", []),
                artifacts=[Path(a) for a in cached.get("artifacts", [])],
                stages=[],
            )

    with _stage(stages, "ingestion", progress):
        ing = ingestion.load_and_validate(input_path)

    with _stage(stages, "preprocessing", progress):
        pre = preprocessing.clean(
            ing.df, resample_rule=config.resample_rule,
            max_interp_gap=config.max_interp_gap,
        )

    with _stage(stages, "spectrum", progress):
        spec = analysis.spectrum(pre.clean_df, top_k=config.top_k_cycles)

    with _stage(stages, "metrics", progress):
        m_bundle = metrics_mod.compute(
            pre.clean_df,
            oor_low=config.oor_low, oor_high=config.oor_high,
            anomaly_rate_thr_per_hour=config.anomaly_rate_thr_per_hour,
            lag_search_hours=config.lag_search_hours,
        )

    with _stage(stages, "forecast", progress):
        fc_bundle = forecasting.forecast(
            pre.clean_df, model=config.forecast_model, horizon=config.forecast_horizon,
        )

    with _stage(stages, "alerts", progress):
        alert_report = alerts_mod.evaluate(m_bundle.metrics, fc_bundle.forecast_df, config)

    with _stage(stages, "interpretation", progress):
        text = interpretation.summarize(m_bundle.metrics, spec.spectrum, alert_report)

    artifacts: list[Path] = []
    with _stage(stages, "reporting", progress):
        plot_dir = out_dir / "plots"
        if "png" in config.report_formats:
            artifacts.append(plots.plot_timeseries(pre.clean_df, plot_dir, fc_bundle.forecast_df))
            artifacts.append(plots.plot_spectrum(spec, plot_dir))
            artifacts.append(plots.plot_heatmap(pre.clean_df, plot_dir))
        if "csv" in config.report_formats:
            artifacts.extend(exporters.export_csv(
                pre.clean_df, m_bundle.daily_df, fc_bundle.forecast_df, out_dir
            ))
        if "xlsx" in config.report_formats:
            artifacts.append(exporters.export_xlsx(
                m_bundle.metrics, spec.spectrum, alert_report, m_bundle.daily_df, out_dir
            ))
        if "pdf" in config.report_formats:
            png_paths = [p for p in artifacts if p.suffix == ".png"]
            artifacts.append(exporters.export_pdf(text, png_paths, out_dir))
        (out_dir / "interpretation.txt").write_text(text, encoding="utf-8")
        artifacts.append(out_dir / "interpretation.txt")

    duration = time.perf_counter() - t_start

    metrics_json = m_bundle.metrics.model_dump()
    spectrum_json = spec.spectrum.model_dump()
    quality_json = pre.report.model_dump()
    forecast_summary = fc_bundle.result.model_dump()

    meta_mod.write_experiment_meta(
        out_dir, run_uid, input_path, cfg_dict,
        metrics_json, spectrum_json, quality_json, duration, config.random_seed,
    )
    meta_mod.write_validation_summary(out_dir, _validation_checks(ing, pre, m_bundle.metrics))

    payload = {
        "run_uid": run_uid,
        "input_path": str(input_path),
        "input_signature": cache_key,
        "config_json": json.dumps(cfg_dict, default=str),
        "duration_seconds": duration,
        "status": "ok" if all(s.status == "ok" for s in stages) else "partial",
        "clean_points": pre.report.clean_points,
        "amp_in_robust": metrics_json["amplitude"]["amp_in_robust"],
        "amp_out_robust": metrics_json["amplitude"]["amp_out_robust"],
        "attenuation_robust": metrics_json["amplitude"]["attenuation_robust"],
        "pearson": metrics_json["correlation"]["pearson"],
        "lag_hours": metrics_json["correlation"]["lag_hours"],
        "out_of_range_pct": metrics_json["out_of_range_pct"],
        "event_count": metrics_json["event_count"],
        "metrics_json": json.dumps(metrics_json, default=str),
        "spectrum_json": json.dumps(spectrum_json, default=str),
        "quality_json": json.dumps(quality_json, default=str),
        "forecast_summary_json": json.dumps(forecast_summary, default=str),
        "interpretation": text,
        "artifacts_dir": str(out_dir),
        "stages": [
            {
                "stage": s.stage, "started_at": s.started_at,
                "duration_seconds": s.duration_seconds,
                "status": s.status, "message": s.message,
            }
            for s in stages
        ],
        "alerts": [
            {
                "code": a.code, "severity": a.severity, "message": a.message,
                "value": float(a.value) if a.value is not None else 0.0,
                "threshold": float(a.threshold) if a.threshold is not None else 0.0,
            }
            for a in alert_report.alerts
        ],
    }
    repository.save_run(config.db_path, payload)

    cache_payload = {
        "run_uid": run_uid,
        "duration_seconds": duration,
        "metrics": metrics_json, "spectrum": spectrum_json, "quality": quality_json,
        "forecast": forecast_summary, "interpretation": text,
        "alerts": [a.model_dump() for a in alert_report.alerts],
        "artifacts": [str(p) for p in artifacts],
        "artifacts_dir": str(out_dir),
    }
    cache_mod.put_cached(config.db_path, cache_key, cache_payload, run_uid=run_uid)

    return PipelineResult(
        run_uid=run_uid,
        out_dir=out_dir,
        duration_seconds=duration,
        interpretation=text,
        metrics=metrics_json,
        spectrum=spectrum_json,
        quality=quality_json,
        forecast=forecast_summary,
        alerts=[a.model_dump() for a in alert_report.alerts],
        artifacts=artifacts,
        stages=stages,
    )


def _validation_checks(
    ing: ingestion.IngestionResult,
    pre: preprocessing.PreprocessingResult,
    m: metrics_mod.MetricsResult,
) -> list[dict]:
    checks: list[dict] = []
    checks.append({
        "name": "schema_columns_present",
        "status": "pass",
        "detail": f"accepted={ing.report.accepted_rows}, rejected={ing.report.rejected_rows}",
    })
    checks.append({
        "name": "non_empty_clean_series",
        "status": "pass" if pre.report.clean_points > 100 else "warning",
        "detail": f"clean_points={pre.report.clean_points}",
    })
    checks.append({
        "name": "correlation_in_range",
        "status": "pass" if -1.0 <= m.correlation.pearson <= 1.0 else "warning",
        "detail": f"pearson={m.correlation.pearson:.4f}",
    })
    checks.append({
        "name": "attenuation_finite",
        "status": "pass" if pd.notna(m.amplitude.attenuation_robust) else "warning",
        "detail": f"attenuation_robust={m.amplitude.attenuation_robust}",
    })
    return checks
