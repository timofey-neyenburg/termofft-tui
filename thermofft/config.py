from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


ForecastModel = Literal["expsmooth", "sarima", "naive"]


class AppConfig(BaseModel):
    """Конфигурация прогона ThermoFFT pipeline."""

    resample_rule: str = Field(default="15min")
    max_interp_gap: str = Field(default="15min")

    forecast_model: ForecastModel = Field(default="expsmooth")
    forecast_horizon: str = Field(default="24h")

    oor_low: float = Field(default=18.0)
    oor_high: float = Field(default=27.0)
    anomaly_rate_thr_per_hour: float = Field(default=1.5)
    lag_search_hours: float = Field(default=24.0)

    attenuation_warn: float = Field(default=0.7)
    attenuation_strong: float = Field(default=0.3)
    oor_pct_warn: float = Field(default=10.0)
    lag_hours_warn: float = Field(default=6.0)
    event_count_warn: int = Field(default=5)

    top_k_cycles: int = Field(default=5)

    db_path: Path = Field(default=Path("thermofft.db"))
    out_dir: Path = Field(default=Path("runs"))
    report_formats: list[str] = Field(default_factory=lambda: ["png", "csv", "xlsx", "pdf"])

    random_seed: int = Field(default=42)

    @field_validator("db_path", "out_dir", mode="before")
    @classmethod
    def _to_path(cls, v: object) -> Path:
        return Path(v) if not isinstance(v, Path) else v

    @field_validator("report_formats", mode="before")
    @classmethod
    def _parse_formats(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [s.strip().lower() for s in v.split(",") if s.strip()]
        return list(v)  # type: ignore[arg-type]
