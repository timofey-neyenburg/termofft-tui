"""experiment_meta.json + validation_summary.json (наследие lab26)."""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any


def file_signature(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"path": str(p), "exists": False}
    data = p.read_bytes()
    return {
        "path": str(p.resolve()),
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "modified": int(p.stat().st_mtime),
    }


def write_experiment_meta(
    out_dir: Path,
    run_uid: str,
    input_path: str | Path,
    config_dict: dict,
    metrics_dict: dict,
    spectrum_dict: dict,
    quality_dict: dict,
    duration_seconds: float,
    seed: int = 42,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_uid": run_uid,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "input_signature": file_signature(input_path),
        "config": config_dict,
        "results": {
            "metrics": metrics_dict,
            "spectrum": spectrum_dict,
            "quality": quality_dict,
            "duration_seconds": duration_seconds,
        },
        "reproducibility": {
            "seed": seed,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
    }
    path = out_dir / "experiment_meta.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return path


def write_validation_summary(out_dir: Path, checks: list[dict]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    overall = "pass" if all(c.get("status") == "pass" for c in checks) else "warning"
    payload = {"overall": overall, "checks": checks}
    path = out_dir / "validation_summary.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return path
