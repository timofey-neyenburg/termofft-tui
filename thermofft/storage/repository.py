"""CRUD для прогонов + поиск похожих по 5-feature L2."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from sqlalchemy import select

from thermofft.storage.db import session_scope
from thermofft.storage.models import AlertEvent, AnalysisRun, StageLog


@dataclass(slots=True)
class RunSummary:
    run_uid: str
    created_at: str
    input_path: str
    status: str
    duration_seconds: float
    clean_points: int
    attenuation_robust: float
    pearson: float
    lag_hours: float
    out_of_range_pct: float
    event_count: int


def save_run(db_path: str | Path, payload: dict) -> int:
    """Сохранить готовый run + стадии + алерты. Возвращает PK."""
    with session_scope(db_path) as sess:
        run = AnalysisRun(**{k: v for k, v in payload.items() if k not in ("stages", "alerts")})
        sess.add(run)
        sess.flush()

        for s in payload.get("stages", []):
            sess.add(StageLog(run_id=run.id, **s))
        for a in payload.get("alerts", []):
            sess.add(AlertEvent(run_id=run.id, **a))
        return run.id


def list_runs(db_path: str | Path, limit: int = 50) -> list[RunSummary]:
    with session_scope(db_path) as sess:
        rows = sess.execute(
            select(AnalysisRun).order_by(AnalysisRun.created_at.desc()).limit(limit)
        ).scalars().all()
        return [
            RunSummary(
                run_uid=r.run_uid,
                created_at=r.created_at.isoformat(timespec="seconds"),
                input_path=r.input_path,
                status=r.status,
                duration_seconds=float(r.duration_seconds),
                clean_points=int(r.clean_points),
                attenuation_robust=float(r.attenuation_robust),
                pearson=float(r.pearson),
                lag_hours=float(r.lag_hours),
                out_of_range_pct=float(r.out_of_range_pct),
                event_count=int(r.event_count),
            )
            for r in rows
        ]


def get_run(db_path: str | Path, run_uid: str) -> dict | None:
    with session_scope(db_path) as sess:
        r = sess.execute(
            select(AnalysisRun).where(AnalysisRun.run_uid == run_uid)
        ).scalar_one_or_none()
        if r is None:
            return None
        return {
            "run_uid": r.run_uid,
            "created_at": r.created_at.isoformat(timespec="seconds"),
            "input_path": r.input_path,
            "config": json.loads(r.config_json or "{}"),
            "duration_seconds": float(r.duration_seconds),
            "status": r.status,
            "metrics": json.loads(r.metrics_json or "{}"),
            "spectrum": json.loads(r.spectrum_json or "{}"),
            "quality": json.loads(r.quality_json or "{}"),
            "forecast": json.loads(r.forecast_summary_json or "{}"),
            "interpretation": r.interpretation,
            "artifacts_dir": r.artifacts_dir,
            "alerts": [
                {
                    "code": a.code, "severity": a.severity, "message": a.message,
                    "value": a.value, "threshold": a.threshold,
                }
                for a in r.alerts
            ],
            "stages": [
                {
                    "stage": s.stage,
                    "started_at": s.started_at.isoformat(timespec="seconds"),
                    "duration_seconds": float(s.duration_seconds),
                    "status": s.status, "message": s.message,
                }
                for s in r.stages
            ],
        }


_FEATURES = (
    "attenuation_robust",
    "pearson",
    "lag_hours",
    "out_of_range_pct",
    "amp_in_robust",
)


def _row_vec(run: AnalysisRun) -> np.ndarray:
    return np.array(
        [getattr(run, f) for f in _FEATURES], dtype=float
    )


def similar_runs(
    db_path: str | Path, run_uid: str, top_k: int = 3
) -> list[tuple[RunSummary, float]]:
    """L2-расстояние по 5 нормализованным метрикам. Возвращает топ-K (без самого run-а)."""
    with session_scope(db_path) as sess:
        all_runs: Iterable[AnalysisRun] = sess.execute(
            select(AnalysisRun)
        ).scalars().all()
        target = next((r for r in all_runs if r.run_uid == run_uid), None)
        if target is None:
            return []

        others = [r for r in all_runs if r.run_uid != run_uid]
        if not others:
            return []

        mat = np.stack([_row_vec(r) for r in others])
        scales = np.where(np.std(mat, axis=0) > 1e-9, np.std(mat, axis=0), 1.0)
        target_v = (_row_vec(target) - np.mean(mat, axis=0)) / scales
        normalized = (mat - np.mean(mat, axis=0)) / scales
        dists = np.linalg.norm(normalized - target_v, axis=1)
        order = np.argsort(dists)[:top_k]

        result: list[tuple[RunSummary, float]] = []
        for i in order:
            r = others[int(i)]
            result.append((
                RunSummary(
                    run_uid=r.run_uid,
                    created_at=r.created_at.isoformat(timespec="seconds"),
                    input_path=r.input_path,
                    status=r.status,
                    duration_seconds=float(r.duration_seconds),
                    clean_points=int(r.clean_points),
                    attenuation_robust=float(r.attenuation_robust),
                    pearson=float(r.pearson),
                    lag_hours=float(r.lag_hours),
                    out_of_range_pct=float(r.out_of_range_pct),
                    event_count=int(r.event_count),
                ),
                float(dists[int(i)]),
            ))
        return result
