from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.samples.generate import synth  # noqa: E402


@pytest.fixture
def synth_csv(tmp_path) -> Path:
    df = synth(days=5, step_seconds=60)
    path = tmp_path / "synth.csv"
    df.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%S")
    return path


@pytest.fixture
def big_synth_csv(tmp_path) -> Path:
    """~100k+ строк (in+out) для perf-теста."""
    df = synth(days=35, step_seconds=60)
    path = tmp_path / "big.csv"
    df.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%S")
    return path
