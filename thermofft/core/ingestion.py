"""Импорт CSV/JSON логов температурных датчиков + валидация схемы."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, Field


REQUIRED_COLUMNS = ("noted_date", "temp", "out/in")
VALID_MODES = ("in", "out")


class ImportError_(Exception):
    """Ошибки слоя ingestion."""


class ImportReport(BaseModel):
    source_path: str
    source_format: str
    raw_rows: int
    accepted_rows: int
    rejected_rows: int = Field(default=0)
    date_min: str | None = None
    date_max: str | None = None
    modes_seen: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class IngestionResult:
    df: pd.DataFrame
    report: ImportReport


def _detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    raise ImportError_(f"Unsupported file extension: {suffix}. Use .csv or .json.")


def _load_json_records(path: Path) -> pd.DataFrame:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "records" in data:
        data = data["records"]
    if not isinstance(data, list):
        raise ImportError_("JSON must be a list or {'records': [...]} object.")
    return pd.DataFrame(data)


def _load_raw(path: Path, fmt: str) -> pd.DataFrame:
    if fmt == "csv":
        return pd.read_csv(path)
    if fmt == "json":
        return _load_json_records(path)
    raise ImportError_(f"Unknown format: {fmt}")


def load_and_validate(file_path: str | Path) -> IngestionResult:
    """Загрузить CSV/JSON, валидировать колонки, привести типы.

    Возвращает DataFrame с колонками ``noted_date`` (datetime64),
    ``temp`` (float), ``out/in`` (str in {"in","out"}).
    """
    path = Path(file_path)
    if not path.exists():
        raise ImportError_(f"File not found: {path}")
    fmt = _detect_format(path)

    raw_df = _load_raw(path, fmt)
    raw_rows = len(raw_df)
    warnings: list[str] = []

    missing = [c for c in REQUIRED_COLUMNS if c not in raw_df.columns]
    if missing:
        raise ImportError_(
            f"Missing required columns: {missing}. Required: {list(REQUIRED_COLUMNS)}."
        )

    df = raw_df.loc[:, list(REQUIRED_COLUMNS)].copy()

    df["noted_date"] = pd.to_datetime(df["noted_date"], dayfirst=True, errors="coerce")
    df["temp"] = pd.to_numeric(df["temp"], errors="coerce")
    df["out/in"] = df["out/in"].astype(str).str.strip().str.lower()

    bad_date = df["noted_date"].isna().sum()
    bad_temp = df["temp"].isna().sum()
    bad_mode = (~df["out/in"].isin(VALID_MODES)).sum()
    if bad_date:
        warnings.append(f"{bad_date} rows have invalid noted_date and will be dropped.")
    if bad_temp:
        warnings.append(f"{bad_temp} rows have non-numeric temp and will be dropped.")
    if bad_mode:
        warnings.append(f"{bad_mode} rows have unexpected mode and will be dropped.")

    mask = (
        df["noted_date"].notna()
        & df["temp"].notna()
        & df["out/in"].isin(VALID_MODES)
    )
    df = df.loc[mask].sort_values("noted_date").reset_index(drop=True)

    if df.empty:
        raise ImportError_(
            "After validation no rows remain. Check time format / temp values / mode column."
        )

    report = ImportReport(
        source_path=str(path),
        source_format=fmt,
        raw_rows=raw_rows,
        accepted_rows=len(df),
        rejected_rows=raw_rows - len(df),
        date_min=df["noted_date"].min().isoformat(),
        date_max=df["noted_date"].max().isoformat(),
        modes_seen=sorted(df["out/in"].unique().tolist()),
        warnings=warnings,
    )
    return IngestionResult(df=df, report=report)
